from django.contrib import admin
from .models import Estancia, CargoEstancia, Folio

@admin.register(Estancia)
class EstanciaAdmin(admin.ModelAdmin):
    list_display = ['id', 'reserva', 'habitacion', 'fecha_checkin', 'fecha_checkout', 'estado']
    list_filter = ['estado']

@admin.register(CargoEstancia)
class CargoEstanciaAdmin(admin.ModelAdmin):
    list_display = ['concepto', 'estancia', 'monto', 'tipo', 'fecha']

@admin.register(Folio)
class FolioAdmin(admin.ModelAdmin):
    list_display = ['id', 'estancia', 'subtotal', 'igv', 'total', 'estado']
