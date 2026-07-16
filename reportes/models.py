from django.db import models
from django.contrib.auth.models import User

class Auditoria(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='auditorias')
    accion = models.CharField(max_length=150)
    fecha = models.DateTimeField(auto_now_add=True)
    registro_id = models.PositiveIntegerField(null=True, blank=True)
    tabla_afectada = models.CharField(max_length=100, null=True, blank=True)
    estado_anterior = models.TextField(null=True, blank=True)
    estado_nuevo = models.TextField(null=True, blank=True)
    observacion = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = 'Auditoria'
        verbose_name_plural = 'Auditorias'
        ordering = ['-fecha']

    def __str__(self):
        user_str = self.usuario.username if self.usuario else "Sistema"
        return f"{self.fecha.strftime('%d/%m/%Y %H:%M:%S')} - {user_str}: {self.accion}"


def registrar_auditoria(usuario, accion, registro_id, tabla_afectada, estado_anterior=None, estado_nuevo=None, observacion=None):
    user_instance = usuario if (usuario and usuario.is_authenticated) else None
    return Auditoria.objects.create(
        usuario=user_instance,
        accion=accion,
        registro_id=registro_id,
        tabla_afectada=tabla_afectada,
        estado_anterior=str(estado_anterior) if estado_anterior is not None else None,
        estado_nuevo=str(estado_nuevo) if estado_nuevo is not None else None,
        observacion=observacion
    )
