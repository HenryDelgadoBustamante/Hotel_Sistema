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

    class Meta:
        verbose_name = 'Cargo de Estancia'
        verbose_name_plural = 'Cargos de Estancia'

    def __str__(self):
        return f"{self.concepto} - S/.{self.monto}"


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
        cargos = self.estancia.cargos.all()
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

    folio = models.ForeignKey(Folio, on_delete=models.CASCADE, related_name='pagos')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES, default=EFECTIVO)
    fecha = models.DateTimeField(auto_now_add=True)
    transaccion_id = models.CharField(max_length=100, blank=True, null=True, verbose_name='ID Transacción')

    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'

    def __str__(self):
        return f"Pago #{self.id} - Folio #{self.folio.id} - S/.{self.monto} ({self.metodo_pago})"
