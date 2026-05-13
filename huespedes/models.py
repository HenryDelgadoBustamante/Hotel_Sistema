from django.db import models


class Huesped(models.Model):
    DNI = 'DNI'
    PASAPORTE = 'PASAPORTE'
    CE = 'CE'

    TIPO_DOC_CHOICES = [
        (DNI, 'DNI'),
        (PASAPORTE, 'Pasaporte'),
        (CE, 'Carné de Extranjería'),
    ]

    tipo_doc = models.CharField(max_length=10, choices=TIPO_DOC_CHOICES, default=DNI)
    num_doc = models.CharField(max_length=20, unique=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    nacionalidad = models.CharField(max_length=50, default='Peruana')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Huésped'
        verbose_name_plural = 'Huéspedes'

    def __str__(self):
        return f"{self.nombres} {self.apellidos} ({self.tipo_doc}: {self.num_doc})"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}"
