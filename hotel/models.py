# Definición de entidades: Hotel, TipoHabitacion, Habitacion
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Hotel(models.Model):
    nombre = models.CharField(max_length=200)
    ruc = models.CharField(max_length=11, unique=True)
    direccion = models.TextField()
    estrellas = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    telefono = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    # Configuraciones de Early Check-In
    permitir_early_checkin = models.BooleanField(default=True)
    cobrar_early_checkin = models.BooleanField(default=False)
    early_checkin_tipo_cargo = models.CharField(max_length=20, choices=[('FIJO', 'Monto Fijo'), ('PORCENTAJE', 'Porcentaje')], default='FIJO')
    early_checkin_monto_porcentaje = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    early_checkin_tolerancia_minutos = models.PositiveIntegerField(default=30)
    early_checkin_rol_exonerar = models.CharField(max_length=50, default='administrador')

    # Configuraciones de Late Check-Out
    permitir_late_checkout = models.BooleanField(default=True)
    late_checkout_hora_maxima = models.TimeField(default='18:00')
    late_checkout_tolerancia_minutos = models.PositiveIntegerField(default=10)
    late_checkout_tipo_cargo = models.CharField(max_length=20, choices=[('FIJO', 'Monto Fijo'), ('PORCENTAJE', 'Porcentaje')], default='PORCENTAJE')
    late_checkout_monto_porcentaje = models.DecimalField(max_digits=10, decimal_places=2, default=0.35)
    late_checkout_horas_bloque = models.PositiveIntegerField(default=3)
    late_checkout_rol_exonerar = models.CharField(max_length=50, default='administrador')

    # Configuración de Alertas de Check-Out
    alerta_checkout_minutos = models.PositiveIntegerField(
        default=30,
        choices=[(15, '15 minutos antes'), (30, '30 minutos antes'), (60, '60 minutos antes')],
        help_text="Minutos antes del checkout para mostrar alerta al recepcionista."
    )

    class Meta:
        verbose_name = 'Hotel'
        verbose_name_plural = 'Hoteles'

    def __str__(self):
        return f"{self.nombre} ({self.estrellas}★)"


class TipoHabitacion(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='tipos_habitacion')
    nombre = models.CharField(max_length=100)
    capacidad = models.IntegerField(validators=[MinValueValidator(1)])
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    amenidades = models.JSONField(default=list)

    class Meta:
        verbose_name = 'Tipo de Habitación'
        verbose_name_plural = 'Tipos de Habitación'

    def __str__(self):
        return f"{self.nombre} - {self.hotel.nombre}"


class Habitacion(models.Model):
    DISPONIBLE = 'DISPONIBLE'
    OCUPADA = 'OCUPADA'
    LIMPIEZA = 'LIMPIEZA'
    MANTENIMIENTO = 'MANTENIMIENTO'

    ESTADO_CHOICES = [
        (DISPONIBLE, 'Disponible'),
        (OCUPADA, 'Ocupada'),
        (LIMPIEZA, 'En Limpieza'),
        (MANTENIMIENTO, 'En Mantenimiento'),
    ]

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='habitaciones')
    tipo = models.ForeignKey(TipoHabitacion, on_delete=models.CASCADE, related_name='habitaciones')
    numero = models.CharField(max_length=10)
    piso = models.IntegerField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=DISPONIBLE)
    imagen_url = models.URLField(blank=True, null=True)
    imagenes_urls = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = 'Habitación'
        verbose_name_plural = 'Habitaciones'
        unique_together = ['hotel', 'numero']

    def __str__(self):
        return f"Hab. {self.numero} - Piso {self.piso} ({self.estado})"
