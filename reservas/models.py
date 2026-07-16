# Definición de entidades: Tarifa, Reserva con lógica tarifaria
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from hotel.models import Habitacion, Hotel, TipoHabitacion
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
    POR_DIA = 'DIA'
    POR_HORA = 'HORA'

    MODALIDAD_CHOICES = [
        (POR_DIA, 'Por dia'),
        (POR_HORA, 'Por horas'),
    ]

    PENDIENTE = 'PENDIENTE'
    CONFIRMADA = 'CONFIRMADA'
    CHECKIN = 'CHECKIN'
    CHECKOUT = 'CHECKOUT'
    CANCELADA = 'CANCELADA'
    REEMBOLSADO = 'REEMBOLSADO'

    ESTADO_CHOICES = [
        (PENDIENTE, 'Pendiente'),
        (CONFIRMADA, 'Confirmada'),
        (CHECKIN, 'Check-In realizado'),
        (CHECKOUT, 'Check-Out realizado'),
        (CANCELADA, 'Cancelada'),
        (REEMBOLSADO, 'Reembolsado'),
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
    fecha_hora_entrada = models.DateTimeField(null=True, blank=True)
    fecha_hora_salida = models.DateTimeField(null=True, blank=True)
    modalidad = models.CharField(max_length=10, choices=MODALIDAD_CHOICES, default=POR_DIA)
    duracion_horas = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tolerancia_minutos = models.PositiveIntegerField(default=10)
    cargo_extra_desde_minutos = models.PositiveIntegerField(default=30)
    num_adultos = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=PENDIENTE)
    precio_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default=DIRECTO)
    observaciones = models.TextField(blank=True, null=True)
    motivo_cancelacion = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Reserva'
        verbose_name_plural = 'Reservas'

    def __str__(self):
        return f"Reserva #{self.id} - {self.huesped} ({self.fecha_entrada} -> {self.fecha_salida})"

    def normalizar_horario(self):
        if not self.fecha_entrada or not self.fecha_salida:
            return

        if self.modalidad == self.POR_HORA:
            if not self.fecha_hora_entrada:
                entrada = datetime.combine(self.fecha_entrada, time(15, 0))
                self.fecha_hora_entrada = timezone.make_aware(entrada)

            horas = float(self.duracion_horas or 3)
            if horas <= 0:
                horas = 3

            self.duracion_horas = horas
            self.fecha_hora_salida = self.fecha_hora_entrada + timedelta(hours=horas)
            self.fecha_entrada = self.fecha_hora_entrada.date()
            self.fecha_salida = self.fecha_hora_salida.date()
            return

        entrada = datetime.combine(self.fecha_entrada, time(15, 0))
        salida = datetime.combine(self.fecha_salida, time(12, 0))
        self.fecha_hora_entrada = timezone.make_aware(entrada)
        self.fecha_hora_salida = timezone.make_aware(salida)
        self.duracion_horas = 0

    def clean(self):
        self.normalizar_horario()
        if self.fecha_hora_entrada and self.fecha_hora_salida and self.fecha_hora_salida <= self.fecha_hora_entrada:
            raise ValidationError('La salida debe ser posterior a la entrada.')

        if self.habitacion:
            if self.habitacion.estado == Habitacion.MANTENIMIENTO:
                raise ValidationError('No se puede reservar una habitación en mantenimiento.')

            if self.num_adultos > self.habitacion.tipo.capacidad:
                raise ValidationError('La cantidad de adultos supera la capacidad de la habitación.')


            estados_activos = [self.PENDIENTE, self.CONFIRMADA, self.CHECKIN]
            solapadas = Reserva.objects.filter(
                habitacion=self.habitacion,
                estado__in=estados_activos,
            ).exclude(pk=self.pk)

            if self.fecha_hora_entrada and self.fecha_hora_salida:
                solapadas = solapadas.filter(
                    fecha_hora_entrada__lt=self.fecha_hora_salida,
                    fecha_hora_salida__gt=self.fecha_hora_entrada,
                )
            else:
                solapadas = solapadas.filter(
                    fecha_entrada__lt=self.fecha_salida,
                    fecha_salida__gt=self.fecha_entrada,
                )

            if solapadas.exists():
                raise ValidationError('Esta habitacion ya tiene una reserva activa en ese horario.')

    def calcular_precio(self):
        if not self.habitacion:
            return 0

        if self.modalidad == self.POR_HORA:
            horas = float(self.duracion_horas or 3)
            bloques = max(1, int((horas + 2.99) // 3))
            tarifa_bloque = self.habitacion.tipo.precio_base * Decimal('0.35')
            return round(tarifa_bloque * bloques, 2)

        tarifa = Tarifa.objects.filter(
            tipo_habitacion=self.habitacion.tipo,
            fecha_inicio__lte=self.fecha_entrada,
            fecha_fin__gte=self.fecha_salida,
        ).first()
        noches = (self.fecha_salida - self.fecha_entrada).days
        if tarifa:
            return tarifa.precio_noche * noches
        return self.habitacion.tipo.precio_base * noches

    @property
    def total_pagado(self):
        return sum(p.monto for p in self.pagos.all())

    @property
    def saldo_pendiente(self):
        return max(Decimal('0.00'), self.precio_total - self.total_pagado)

    def save(self, *args, **kwargs):
        self.normalizar_horario()
        self.full_clean()
        super().save(*args, **kwargs)
