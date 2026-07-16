from django.contrib import admin
from .models import TicketServicio, SeguimientoTicket

@admin.register(TicketServicio)
class TicketServicioAdmin(admin.ModelAdmin):
    list_display = ('numero_atencion', 'estancia', 'categoria', 'prioridad', 'estado', 'responsable', 'fecha')
    list_filter = ('estado', 'categoria', 'prioridad', 'responsable', 'fecha')
    search_fields = ('numero_atencion', 'estancia__habitacion__numero', 'estancia__reserva__huesped__nombres', 'estancia__reserva__huesped__apellidos')

@admin.register(SeguimientoTicket)
class SeguimientoTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'usuario', 'fecha', 'hora', 'estado_ticket')
    list_filter = ('fecha', 'estado_ticket')
    search_fields = ('ticket__numero_atencion', 'comentario')
