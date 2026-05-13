from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from hotel.models import Hotel, Habitacion, TipoHabitacion
from huespedes.models import Huesped


class Tarifa(models.Model):
    tipo_habitacion = models.ForeignKey(TipoHabitacion, on_delete=models.CASCADE, related_name='tarifas')
    nombre = models.CharField(max_length=100)
    precio_noche = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()

    class Meta:
        verbose_name = 'Tarifa'
        verbose_name_plural = 'Tarifas'

    def __str__(self):
        return f"{self.nombre} - S/.{self.precio_noche}/noche"


class Reserva(models.Model):
    PENDIENTE = 'PENDIENTE'
    CONFIRMADA = 'CONFIRMADA'
    CHECKIN = 'CHECKIN'
    CHECKOUT = 'CHECKOUT'
    CANCELADA = 'CANCELADA'

    ESTADO_CHOICES = [
        (PENDIENTE, 'Pendiente'),
        (CONFIRMADA, 'Confirmada'),
        (CHECKIN, 'Check-In realizado'),
        (CHECKOUT, 'Check-Out realizado'),
        (CANCELADA, 'Cancelada'),
    ]

    DIRECTO = 'DIRECTO'
    WEB = 'WEB'
    AGENCIA = 'AGENCIA'

    ORIGEN_CHOICES = [
        (DIRECTO, 'Directo'),
        (WEB, 'Web'),
        (AGENCIA, 'Agencia'),
    ]

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='reservas')
    huesped = models.ForeignKey(Huesped, on_delete=models.CASCADE, related_name='reservas')
    habitacion = models.ForeignKey(Habitacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservas')
    fecha_entrada = models.DateField()
    fecha_salida = models.DateField()
    num_adultos = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=PENDIENTE)
    precio_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default=DIRECTO)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Reserva'
        verbose_name_plural = 'Reservas'

    def __str__(self):
        return f"Reserva #{self.id} - {self.huesped} ({self.fecha_entrada} → {self.fecha_salida})"

    def clean(self):
        if self.habitacion:
            estados_activos = [self.PENDIENTE, self.CONFIRMADA, self.CHECKIN]
            solapadas = Reserva.objects.filter(
                habitacion=self.habitacion,
                estado__in=estados_activos,
                fecha_entrada__lt=self.fecha_salida,
                fecha_salida__gt=self.fecha_entrada,
            ).exclude(pk=self.pk)
            if solapadas.exists():
                raise ValidationError('Esta habitación ya tiene una reserva activa en esas fechas.')

    def calcular_precio(self):
        if not self.habitacion:
            return 0
        tarifa = Tarifa.objects.filter(
            tipo_habitacion=self.habitacion.tipo,
            fecha_inicio__lte=self.fecha_entrada,
            fecha_fin__gte=self.fecha_salida,
        ).first()
        if tarifa:
            noches = (self.fecha_salida - self.fecha_entrada).days
            return tarifa.precio_noche * noches
        noches = (self.fecha_salida - self.fecha_entrada).days
        return self.habitacion.tipo.precio_base * noches

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
