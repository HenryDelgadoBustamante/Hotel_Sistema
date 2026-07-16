from django.db import models
from django.contrib.auth.models import User
from estancias.models import Estancia

class TicketServicio(models.Model):
    CATEGORIAS = [
        ('INFORMACION', 'Información'),
        ('LIMPIEZA', 'Limpieza'),
        ('MANTENIMIENTO', 'Mantenimiento'),
        ('SERVICIO_HABITACION', 'Servicio a la habitación'),
        ('RECLAMO', 'Reclamo'),
        ('EMERGENCIA', 'Emergencia'),
        ('CONSULTA', 'Consulta'),
        ('OTRO', 'Otro'),
    ]

    PRIORIDADES = [
        ('BAJA', 'Baja'),
        ('MEDIA', 'Media'),
        ('ALTA', 'Alta'),
        ('URGENTE', 'Urgente'),
    ]

    ESTADOS = [
        ('ABIERTA', 'Abierta'),
        ('PROCESO', 'En Proceso'),
        ('PENDIENTE', 'Pendiente'),
        ('RESUELTA', 'Resuelta'),
        ('CERRADA', 'Cerrada'),
    ]

    AREAS = [
        ('RECEPCION', 'Recepción'),
        ('HOUSEKEEPING', 'Housekeeping'),
        ('MANTENIMIENTO', 'Mantenimiento'),
        ('ADMINISTRACION', 'Administración'),
    ]

    numero_atencion = models.CharField(max_length=20, unique=True, blank=True)
    estancia = models.ForeignKey(Estancia, on_delete=models.CASCADE, related_name='tickets')
    categoria = models.CharField(max_length=30, choices=CATEGORIAS)
    prioridad = models.CharField(max_length=15, choices=PRIORIDADES, default='MEDIA')
    estado = models.CharField(max_length=15, choices=ESTADOS, default='ABIERTA')
    descripcion = models.TextField()
    responsable = models.CharField(max_length=20, choices=AREAS, default='RECEPCION')
    recepcionista = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tickets_registrados')
    fecha = models.DateField(auto_now_add=True)
    hora = models.TimeField(auto_now_add=True)
    
    solucion = models.TextField(blank=True, null=True)
    observacion_resolucion = models.TextField(blank=True, null=True)
    motivo_reapertura = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = 'Ticket de Servicio'
        verbose_name_plural = 'Tickets de Servicio'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        is_new = not self.pk
        if is_new and not self.fecha:
            from django.utils import timezone
            self.fecha = timezone.localtime(timezone.now()).date()
        super().save(*args, **kwargs)
        if is_new:
            self.numero_atencion = f"TKT-{self.fecha.year}-{self.id:05d}"
            super().save(update_fields=['numero_atencion'])

    def __str__(self):
        return f"Ticket {self.numero_atencion} - Hab. {self.estancia.habitacion.numero} ({self.estado})"

    @property
    def tiempo_resolucion_minutos(self):
        if self.resolved_at:
            delta = self.resolved_at - self.created_at
            return int(delta.total_seconds() // 60)
        return None


class SeguimientoTicket(models.Model):
    ticket = models.ForeignKey(TicketServicio, on_delete=models.CASCADE, related_name='seguimientos')
    fecha = models.DateField(auto_now_add=True)
    hora = models.TimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    comentario = models.TextField()
    estado_ticket = models.CharField(max_length=20)

    class Meta:
        verbose_name = 'Seguimiento de Ticket'
        verbose_name_plural = 'Seguimientos de Tickets'
        ordering = ['fecha', 'hora']

    def __str__(self):
        return f"Seguimiento {self.ticket.numero_atencion} - {self.fecha} {self.hora}"
