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
