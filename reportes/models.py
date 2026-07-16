from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import uuid


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


class LoginIntento(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='intentos_login')
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    exitoso = models.BooleanField(default=False)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Intento de Login'
        verbose_name_plural = 'Intentos de Login'
        ordering = ['-fecha']

    def __str__(self):
        user_str = self.usuario.username if self.usuario else 'Desconocido'
        return f"Intento {user_str} - {'Exitoso' if self.exitoso else 'Fallido'} - {self.fecha}"

    @classmethod
    def contar_fallidos_recientes(cls, usuario, minutos=15):
        limite = timezone.now() - timedelta(minutes=minutos)
        return cls.objects.filter(
            usuario=usuario,
            exitoso=False,
            fecha__gte=limite
        ).count()

    @classmethod
    def registrar(cls, usuario, ip=None, user_agent='', exitoso=False):
        return cls.objects.create(
            usuario=usuario,
            ip=ip,
            user_agent=user_agent[:300],
            exitoso=exitoso
        )


class PasswordResetToken(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_tokens')
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    creado = models.DateTimeField(auto_now_add=True)
    usado = models.BooleanField(default=False)
    expiracion = models.DateTimeField()

    class Meta:
        verbose_name = 'Token de Recuperación'
        verbose_name_plural = 'Tokens de Recuperación'

    def __str__(self):
        return f"Token para {self.usuario.username} - {'Usado' if self.usado else 'Válido'}"

    def save(self, *args, **kwargs):
        if not self.expiracion:
            self.expiracion = timezone.now() + timedelta(hours=1)
        super().save(*args, **kwargs)

    def esta_valido(self):
        return not self.usado and timezone.now() < self.expiracion
