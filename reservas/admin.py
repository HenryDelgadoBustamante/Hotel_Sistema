from django.contrib import admin
from .models import Tarifa, Reserva

@admin.register(Tarifa)
class TarifaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'tipo_habitacion', 'precio_noche', 'fecha_inicio', 'fecha_fin']

@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ['id', 'huesped', 'habitacion', 'fecha_entrada', 'fecha_salida', 'estado', 'precio_total']
    list_filter = ['estado', 'origen']
    search_fields = ['huesped__nombres', 'huesped__apellidos']
