from django.contrib import admin
from .models import Hotel, TipoHabitacion, Habitacion

@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'ruc', 'estrellas', 'telefono', 'created_at']
    search_fields = ['nombre', 'ruc']

@admin.register(TipoHabitacion)
class TipoHabitacionAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'hotel', 'capacidad', 'precio_base']

@admin.register(Habitacion)
class HabitacionAdmin(admin.ModelAdmin):
    list_display = ['numero', 'piso', 'hotel', 'tipo', 'estado']
    list_filter = ['estado', 'hotel', 'piso']
