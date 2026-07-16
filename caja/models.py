from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal


class Caja(models.Model):
    ABIERTA = 'ABIERTA'
    CERRADA = 'CERRADA'

    ESTADO_CHOICES = [
        (ABIERTA, 'Abierta'),
        (CERRADA, 'Cerrada'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cajas')
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    monto_inicial = models.DecimalField(max_digits=10, decimal_places=2)
    monto_ingresos = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    monto_egresos = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    monto_esperado = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    monto_real = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    diferencia = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ABIERTA)
    observacion_apertura = models.TextField(blank=True, null=True)
    observacion_cierre = models.TextField(blank=True, null=True)
    arqueada = models.BooleanField(default=False)
    fecha_arqueo = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Caja'
        verbose_name_plural = 'Cajas'
        ordering = ['-fecha_apertura']

    def __str__(self):
        return f"Caja {self.id} - {self.usuario.username} ({self.get_estado_display()})"

    def clean(self):
        super().clean()
        if self.monto_inicial < 0:
            raise ValidationError({'monto_inicial': 'El monto inicial no puede ser negativo.'})

    def recalcular_totales(self):
        """Calcula ingresos, egresos y monto esperado de forma atómica en base a movimientos."""
        ingresos = self.movimientos.filter(tipo=MovimientoCaja.INGRESO).aggregate(
            total=models.Sum('monto')
        )['total'] or Decimal('0.00')
        
        egresos = self.movimientos.filter(tipo=MovimientoCaja.EGRESO).aggregate(
            total=models.Sum('monto')
        )['total'] or Decimal('0.00')

        self.monto_ingresos = ingresos
        self.monto_egresos = egresos
        self.monto_esperado = self.monto_inicial + ingresos - egresos
        
        if self.monto_real is not None:
            self.diferencia = self.monto_real - self.monto_esperado
            
        self.save()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MovimientoCaja(models.Model):
    INGRESO = 'INGRESO'
    EGRESO = 'EGRESO'

    TIPO_CHOICES = [
        (INGRESO, 'Ingreso'),
        (EGRESO, 'Egreso'),
    ]

    PAGO_RESERVA = 'PAGO_RESERVA'
    PAGO_HOSPEDAJE = 'PAGO_HOSPEDAJE'
    PAGO_CONSUMOS = 'PAGO_CONSUMOS'
    REEMBOLSO = 'REEMBOLSO'
    AJUSTE_MANUAL = 'AJUSTE_MANUAL'
    OTROS = 'OTROS'

    CONCEPTO_CHOICES = [
        (PAGO_RESERVA, 'Pago Reserva (Anticipo)'),
        (PAGO_HOSPEDAJE, 'Pago Hospedaje'),
        (PAGO_CONSUMOS, 'Pago Consumos'),
        (REEMBOLSO, 'Reembolso'),
        (AJUSTE_MANUAL, 'Ajuste Manual'),
        (OTROS, 'Otros'),
    ]

    EFECTIVO = 'EFECTIVO'
    TARJETA_DEBITO = 'TARJETA_DEBITO'
    TARJETA_CREDITO = 'TARJETA_CREDITO'
    TRANSFERENCIA = 'TRANSFERENCIA'
    YAPE = 'YAPE'
    PLIN = 'PLIN'

    METODO_PAGO_CHOICES = [
        (EFECTIVO, 'Efectivo'),
        (TARJETA_DEBITO, 'Tarjeta de Débito'),
        (TARJETA_CREDITO, 'Tarjeta de Crédito'),
        (TRANSFERENCIA, 'Transferencia Bancaria'),
        (YAPE, 'Yape'),
        (PLIN, 'Plin'),
    ]

    caja = models.ForeignKey(Caja, on_delete=models.CASCADE, related_name='movimientos')
    fecha = models.DateTimeField(auto_now_add=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    concepto = models.CharField(max_length=20, choices=CONCEPTO_CHOICES, default=OTROS)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES, default=EFECTIVO)
    descripcion = models.TextField()
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Vinculación de origen
    pago_origen = models.ForeignKey('estancias.Pago', null=True, blank=True, on_delete=models.SET_NULL, related_name='movimientos_caja')
    reembolso_origen = models.ForeignKey('estancias.Reembolso', null=True, blank=True, on_delete=models.SET_NULL, related_name='movimientos_caja')
    referencia = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = 'Movimiento de Caja'
        verbose_name_plural = 'Movimientos de Caja'
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.get_tipo_display()} - S/.{self.monto} ({self.get_concepto_display()})"

    def clean(self):
        super().clean()
        if self.monto <= 0:
            raise ValidationError({'monto': 'El monto del movimiento debe ser mayor a cero.'})
        if self.caja.estado == Caja.CERRADA:
            raise ValidationError('No se pueden registrar movimientos en una caja cerrada.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        # Recalcular totales de la caja asociada
        self.caja.recalcular_totales()


class AnomaliaCaja(models.Model):
    FALTANTE = 'FALTANTE'
    SOBRANTE = 'SOBRANTE'
    BILLETE_FALSO = 'BILLETE_FALSO'
    COMPROBANTE_DUPLICADO = 'COMPROBANTE_DUPLICADO'
    PAGO_RECHAZADO = 'PAGO_RECHAZADO'
    OTRO = 'OTRO'

    TIPO_ANOMALIA_CHOICES = [
        (FALTANTE, 'Faltante de Efectivo'),
        (SOBRANTE, 'Sobrante de Efectivo'),
        (BILLETE_FALSO, 'Billete Falso'),
        (COMPROBANTE_DUPLICADO, 'Comprobante Duplicado'),
        (PAGO_RECHAZADO, 'Pago Rechazado'),
        (OTRO, 'Otro'),
    ]

    caja = models.ForeignKey(Caja, on_delete=models.CASCADE, related_name='anomalias')
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=25, choices=TIPO_ANOMALIA_CHOICES, default=OTRO)
    monto = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    observacion = models.TextField()
    resuelta = models.BooleanField(default=False)
    resuelta_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='anomalias_caja_resueltas')
    fecha_resolucion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Anomalía de Caja'
        verbose_name_plural = 'Anomalías de Caja'
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.get_tipo_display()} - Caja #{self.caja.id} ({'Resuelta' if self.resuelta else 'Pendiente'})"
