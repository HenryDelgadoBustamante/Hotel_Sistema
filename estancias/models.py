# Definición de entidades: Estancia, CargoEstancia, Folio, Pago

import django
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from reservas.models import Reserva
from hotel.models import Habitacion


class Estancia(models.Model):
    ACTIVA = 'ACTIVA'
    FINALIZADA = 'FINALIZADA'

    ESTADO_CHOICES = [
        (ACTIVA, 'Activa'),
        (FINALIZADA, 'Finalizada'),
    ]

    reserva = models.OneToOneField(Reserva, on_delete=models.CASCADE, related_name='estancia')
    habitacion = models.ForeignKey(Habitacion, on_delete=models.CASCADE, related_name='estancias')
    fecha_checkin = models.DateTimeField(auto_now_add=True)
    fecha_checkout = models.DateTimeField(null=True, blank=True)
    precio_final = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ACTIVA)

    class Meta:
        verbose_name = 'Estancia'
        verbose_name_plural = 'Estancias'

    def __str__(self):
        return f"Estancia #{self.id} - Hab.{self.habitacion.numero} ({self.estado})"

    def hacer_checkout(self):
        folio = getattr(self, 'folio', None)
        if folio:
            folio.calcular_totales()
            if folio.saldo_pendiente > 0 and folio.estado == Folio.ABIERTO:
                raise ValidationError('No se puede hacer checkout: el folio tiene saldo pendiente.')
            folio.estado = Folio.CERRADO
            folio.save()
        self.fecha_checkout = timezone.now()
        self.estado = self.FINALIZADA
        self.habitacion.estado = Habitacion.LIMPIEZA
        self.habitacion.save()
        self.reserva.estado = 'CHECKOUT'
        self.reserva.save()
        self.save()


class CargoEstancia(models.Model):
    HABITACION = 'HABITACION'
    RESTAURANTE = 'RESTAURANTE'
    LAVANDERIA = 'LAVANDERIA'
    OTRO = 'OTRO'

    TIPO_CHOICES = [
        (HABITACION, 'Habitación'),
        (RESTAURANTE, 'Restaurante'),
        (LAVANDERIA, 'Lavandería'),
        (OTRO, 'Otro'),
    ]

    estancia = models.ForeignKey(Estancia, on_delete=models.CASCADE, related_name='cargos')
    concepto = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=OTRO)

    # Campos de Exoneracion
    exonerado = models.BooleanField(default=False)
    motivo_exoneracion = models.TextField(null=True, blank=True)
    exonerado_por = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='cargos_exonerados')

    class Meta:
        verbose_name = 'Cargo de Estancia'
        verbose_name_plural = 'Cargos de Estancia'
        constraints = [
            models.CheckConstraint(
                **{("condition" if django.VERSION >= (5, 1) else "check"): models.Q(monto__gt=0)},
                name='monto_cargo_positivo'
            )
        ]

    def __str__(self):
        status = " (Exonerado)" if self.exonerado else ""
        return f"{self.concepto} - S/.{self.monto}{status}"


class Folio(models.Model):
    ABIERTO = 'ABIERTO'
    CERRADO = 'CERRADO'

    ESTADO_CHOICES = [
        (ABIERTO, 'Abierto'),
        (CERRADO, 'Cerrado'),
    ]

    estancia = models.OneToOneField(Estancia, on_delete=models.CASCADE, related_name='folio')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igv = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ABIERTO)

    class Meta:
        verbose_name = 'Folio'
        verbose_name_plural = 'Folios'

    def __str__(self):
        return f"Folio #{self.id} - Estancia #{self.estancia.id} - S/.{self.total}"

    def calcular_totales(self):
        cargos = self.estancia.cargos.filter(exonerado=False)
        self.total = sum(c.monto for c in cargos)
        self.subtotal = round(self.total / Decimal('1.18'), 2)
        self.igv = self.total - self.subtotal
        self.save()

    @property
    def total_pagado(self):
        return sum(p.monto for p in self.pagos.all())

    @property
    def saldo_pendiente(self):
        return max(Decimal('0.00'), self.total - self.total_pagado)


from django.contrib.auth.models import User

class Pago(models.Model):
    EFECTIVO = 'EFECTIVO'
    TARJETA = 'TARJETA'
    TRANSFERENCIA = 'TRANSFERENCIA'
    YAPE_PLIN = 'YAPE_PLIN'

    METODO_PAGO_CHOICES = [
        (EFECTIVO, 'Efectivo'),
        (TARJETA, 'Tarjeta de Crédito/Débito'),
        (TRANSFERENCIA, 'Transferencia Bancaria'),
        (YAPE_PLIN, 'Yape / Plin'),
    ]

    folio = models.ForeignKey(Folio, on_delete=models.CASCADE, related_name='pagos', null=True, blank=True)
    reserva = models.ForeignKey(Reserva, on_delete=models.SET_NULL, null=True, blank=True, related_name='pagos')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES, default=EFECTIVO)
    fecha = models.DateTimeField(auto_now_add=True)
    transaccion_id = models.CharField(max_length=100, blank=True, null=True, verbose_name='ID Transacción')

    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'

    def __str__(self):
        folio_part = f"Folio #{self.folio.id}" if self.folio else f"Reserva #{self.reserva.id} (Anticipo)"
        return f"Pago #{self.id} - {folio_part} - S/.{self.monto} ({self.metodo_pago})"

    @property
    def reembolsado(self):
        from django.db.models import Sum
        total = self.reembolsos.filter(estado='APROBADO').aggregate(total=Sum('monto'))['total'] or 0
        return total >= self.monto


class Reembolso(models.Model):
    SOLICITADO = 'SOLICITADO'
    APROBADO = 'APROBADO'
    RECHAZADO = 'RECHAZADO'

    ESTADO_CHOICES = [
        (SOLICITADO, 'Solicitado'),
        (APROBADO, 'Aprobado'),
        (RECHAZADO, 'Rechazado'),
    ]

    pago = models.ForeignKey(Pago, on_delete=models.CASCADE, related_name='reembolsos')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    motivo = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=SOLICITADO)
    solicitado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reembolsos_solicitados')
    aprobado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reembolsos_aprobados')
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)
    observacion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Reembolso'
        verbose_name_plural = 'Reembolsos'

    def __str__(self):
        return f"Reembolso #{self.id} - Pago #{self.pago.id} - S/.{self.monto} ({self.estado})"


class HistorialHabitacionEstancia(models.Model):
    estancia = models.ForeignKey(Estancia, on_delete=models.CASCADE, related_name='historial_habitaciones')
    habitacion_anterior = models.ForeignKey(Habitacion, on_delete=models.CASCADE, related_name='habitaciones_salida_historial')
    habitacion_nueva = models.ForeignKey(Habitacion, on_delete=models.CASCADE, related_name='habitaciones_entrada_historial')
    motivo = models.TextField()
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cambios_habitacion_realizados')
    diferencia_tarifaria = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Historial de Cambio de Habitación'
        verbose_name_plural = 'Historiales de Cambios de Habitación'
        ordering = ['-fecha']

    def __str__(self):
        return f"Estancia #{self.estancia.id} - Hab. {self.habitacion_anterior.numero} -> {self.habitacion_nueva.numero} ({self.fecha})"

