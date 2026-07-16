# Definición de entidades: Hotel, TipoHabitacion, Habitacion
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from datetime import time


class Hotel(models.Model):
    nombre = models.CharField(max_length=200)
    razon_social = models.CharField(max_length=200, blank=True, null=True)
    ruc = models.CharField(max_length=11, unique=True)
    direccion = models.TextField()
    estrellas = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    telefono = models.CharField(max_length=20)
    correo = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Horarios estándar
    hora_checkin_estandar = models.TimeField(default='15:00')
    hora_checkout_estandar = models.TimeField(default='12:00')

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

    def clean(self):
        super().clean()
        
        def to_time(val):
            if isinstance(val, str):
                try:
                    parts = val.split(':')
                    return time(int(parts[0]), int(parts[1]))
                except:
                    return None
            return val

        h_in = to_time(self.hora_checkin_estandar)
        h_out = to_time(self.hora_checkout_estandar)
        h_late_max = to_time(self.late_checkout_hora_maxima)

        if h_in is None:
            raise ValidationError({'hora_checkin_estandar': 'La hora de Check-In es obligatoria.'})
        if h_out is None:
            raise ValidationError({'hora_checkout_estandar': 'La hora de Check-Out es obligatoria.'})
        if self.permitir_late_checkout and h_late_max:
            if h_late_max <= h_out:
                raise ValidationError({'late_checkout_hora_maxima': 'La hora máxima de Late Check-Out debe ser posterior a la hora oficial de Check-Out.'})

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
