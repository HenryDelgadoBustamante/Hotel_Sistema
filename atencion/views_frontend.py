from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from datetime import date
from decimal import Decimal
from hotel.models import Habitacion
from estancias.models import Estancia, CargoEstancia
from atencion.models import TicketServicio, SeguimientoTicket
from utils.auditoria import log_action
from reportes.models import registrar_auditoria
from config.views_shared import _es_recepcionista, _es_housekeeping, _acceso_denegado


@login_required
def tickets_lista(request):
    if not _es_recepcionista(request.user) and not _es_housekeeping(request.user):
        return _acceso_denegado(request)
        
    tickets = TicketServicio.objects.select_related('estancia__habitacion', 'estancia__reserva__huesped', 'recepcionista').all()
    
    cliente_q = request.GET.get('cliente', '').strip()
    habitacion_q = request.GET.get('habitacion', '').strip()
    estado_q = request.GET.get('estado', '').strip()
    categoria_q = request.GET.get('categoria', '').strip()
    prioridad_q = request.GET.get('prioridad', '').strip()
    responsable_q = request.GET.get('responsable', '').strip()
    fecha_q = request.GET.get('fecha', '').strip()

    if cliente_q:
        tickets = tickets.filter(
            Q(estancia__reserva__huesped__nombres__icontains=cliente_q) |
            Q(estancia__reserva__huesped__apellidos__icontains=cliente_q) |
            Q(estancia__reserva__huesped__num_doc__icontains=cliente_q)
        )
    if habitacion_q:
        tickets = tickets.filter(estancia__habitacion__numero=habitacion_q)
    if estado_q:
        tickets = tickets.filter(estado=estado_q)
    if categoria_q:
        tickets = tickets.filter(categoria=categoria_q)
    if prioridad_q:
        tickets = tickets.filter(prioridad=prioridad_q)
    if responsable_q:
        tickets = tickets.filter(responsable=responsable_q)
    if fecha_q:
        try:
            fecha_d = date.fromisoformat(fecha_q)
            tickets = tickets.filter(fecha=fecha_d)
        except ValueError:
            pass

    return render(request, 'atencion/lista.html', {
        'tickets': tickets,
        'categorias': TicketServicio.CATEGORIAS,
        'prioridades': TicketServicio.PRIORIDADES,
        'estados': TicketServicio.ESTADOS,
        'areas': TicketServicio.AREAS,
        'f_cliente': cliente_q,
        'f_habitacion': habitacion_q,
        'f_estado': estado_q,
        'f_categoria': categoria_q,
        'f_prioridad': prioridad_q,
        'f_responsable': responsable_q,
        'f_fecha': fecha_q,
    })


@login_required
def ticket_nuevo(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
        
    estancias_activas = Estancia.objects.filter(estado=Estancia.ACTIVA).select_related('habitacion', 'reserva__huesped')
    
    if request.method == 'POST':
        estancia_id = request.POST.get('estancia')
        categoria = request.POST.get('categoria')
        prioridad = request.POST.get('prioridad', 'MEDIA')
        responsable = request.POST.get('responsable', 'RECEPCION')
        descripcion = request.POST.get('descripcion', '').strip()
        
        if not estancia_id or not categoria or not descripcion:
            messages.error(request, 'Todos los campos marcados como obligatorios son requeridos.')
            return redirect('ticket_nuevo')
            
        try:
            estancia = Estancia.objects.get(id=estancia_id)
            if estancia.estado != Estancia.ACTIVA:
                messages.error(request, 'La habitación seleccionada no tiene un hospedaje activo.')
                return redirect('ticket_nuevo')
                
            with transaction.atomic():
                ticket = TicketServicio.objects.create(
                    estancia=estancia,
                    categoria=categoria,
                    prioridad=prioridad,
                    responsable=responsable,
                    descripcion=descripcion,
                    recepcionista=request.user
                )
                
                SeguimientoTicket.objects.create(
                    ticket=ticket,
                    usuario=request.user,
                    comentario=f"Se abre el ticket de atención en estado Abierta. Descripción inicial: {descripcion}",
                    estado_ticket=ticket.estado
                )
                
                if categoria == 'LIMPIEZA':
                    habitacion = estancia.habitacion
                    habitacion.estado = Habitacion.LIMPIEZA
                    habitacion.save()
                    
                    registrar_auditoria(
                        usuario=request.user,
                        accion="Housekeeping Estado Modificado (Aut.)",
                        registro_id=habitacion.id,
                        tabla_afectada="hotel_habitacion",
                        estado_nuevo=Habitacion.LIMPIEZA,
                        observacion=f"Ticket {ticket.numero_atencion} de limpieza abrió orden automática para Hab. {habitacion.numero}"
                    )
                elif categoria == 'MANTENIMIENTO':
                    habitacion = estancia.habitacion
                    habitacion.estado = Habitacion.MANTENIMIENTO
                    habitacion.save()
                    
                    registrar_auditoria(
                        usuario=request.user,
                        accion="Habitación puesta en Mantenimiento (Aut.)",
                        registro_id=habitacion.id,
                        tabla_afectada="hotel_habitacion",
                        estado_nuevo=Habitacion.MANTENIMIENTO,
                        observacion=f"Ticket {ticket.numero_atencion} de mantenimiento bloqueó Hab. {habitacion.numero}"
                    )
                
                registrar_auditoria(
                    usuario=request.user,
                    accion="Crear Ticket de Servicio",
                    registro_id=ticket.id,
                    tabla_afectada="atencion_ticketservicio",
                    estado_nuevo=f"Ticket {ticket.numero_atencion} creado para Hab. {estancia.habitacion.numero}"
                )
                
                messages.success(request, f'Ticket {ticket.numero_atencion} registrado correctamente.')
                return redirect('ticket_detalle', ticket_id=ticket.id)
        except Exception as e:
            messages.error(request, f'Error al registrar el ticket: {str(e)}')
            
    return render(request, 'atencion/nueva.html', {
        'estancias': estancias_activas,
        'categorias': TicketServicio.CATEGORIAS,
        'prioridades': TicketServicio.PRIORIDADES,
        'areas': TicketServicio.AREAS,
    })


@login_required
def ticket_detalle(request, ticket_id):
    if not _es_recepcionista(request.user) and not _es_housekeeping(request.user):
        return _acceso_denegado(request)
        
    ticket = get_object_or_404(TicketServicio.objects.select_related('estancia__habitacion', 'estancia__reserva__huesped', 'recepcionista'), id=ticket_id)
    seguimientos = ticket.seguimientos.select_related('usuario').all()
    
    return render(request, 'atencion/detalle.html', {
        'ticket': ticket,
        'seguimientos': seguimientos,
        'estados': TicketServicio.ESTADOS,
        'areas': TicketServicio.AREAS,
    })


@login_required
def ticket_iniciar(request, ticket_id):
    if not _es_recepcionista(request.user) and not _es_housekeeping(request.user):
        return _acceso_denegado(request)
        
    ticket = get_object_or_404(TicketServicio, id=ticket_id)
    if request.method == 'POST':
        if ticket.estado != 'ABIERTA':
            messages.error(request, 'El ticket ya fue iniciado o resuelto.')
            return redirect('ticket_detalle', ticket_id=ticket.id)
            
        with transaction.atomic():
            ticket.estado = 'PROCESO'
            ticket.save()
            
            SeguimientoTicket.objects.create(
                ticket=ticket,
                usuario=request.user,
                comentario="Se inicia el trabajo sobre la solicitud. Estado cambiado a En Proceso.",
                estado_ticket=ticket.estado
            )
            messages.success(request, 'Trabajo iniciado.')
            
    return redirect('ticket_detalle', ticket_id=ticket.id)


@login_required
def ticket_resolver(request, ticket_id):
    if not _es_recepcionista(request.user) and not _es_housekeeping(request.user):
        return _acceso_denegado(request)
        
    ticket = get_object_or_404(TicketServicio, id=ticket_id)
    if request.method == 'POST':
        solucion = request.POST.get('solucion', '').strip()
        observacion = request.POST.get('observacion_resolucion', '').strip()
        
        if not solucion:
            messages.error(request, 'Debes detallar la solución implementada.')
            return redirect('ticket_detalle', ticket_id=ticket.id)
            
        with transaction.atomic():
            ticket.estado = 'RESUELTA'
            ticket.solucion = solucion
            ticket.observacion_resolucion = observacion
            ticket.resolved_at = timezone.now()
            ticket.save()
            
            SeguimientoTicket.objects.create(
                ticket=ticket,
                usuario=request.user,
                comentario=f"Solicitud resuelta. Solución: {solucion}. Observaciones: {observacion}",
                estado_ticket=ticket.estado
            )
            
            if ticket.categoria == 'LIMPIEZA' and ticket.estancia.habitacion.estado == Habitacion.LIMPIEZA:
                habitacion = ticket.estancia.habitacion
                habitacion.estado = Habitacion.OCUPADA if ticket.estancia.estado == Estancia.ACTIVA else Habitacion.DISPONIBLE
                habitacion.save()
                
                registrar_auditoria(
                    usuario=request.user,
                    accion="Housekeeping Completado (Ticket)",
                    registro_id=habitacion.id,
                    tabla_afectada="hotel_habitacion",
                    estado_nuevo=habitacion.estado,
                    observacion=f"Habitación {habitacion.numero} marcada como {habitacion.estado} al resolverse ticket {ticket.numero_atencion}"
                )
                
            messages.success(request, 'Solicitud marcada como Resuelta.')
            
    return redirect('ticket_detalle', ticket_id=ticket.id)


@login_required
def ticket_cerrar(request, ticket_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
        
    ticket = get_object_or_404(TicketServicio, id=ticket_id)
    if request.method == 'POST':
        if ticket.estado != 'RESUELTA':
            messages.error(request, 'Solo se pueden cerrar tickets previamente resueltos.')
            return redirect('ticket_detalle', ticket_id=ticket.id)
            
        with transaction.atomic():
            ticket.estado = 'CERRADA'
            ticket.closed_at = timezone.now()
            ticket.save()
            
            SeguimientoTicket.objects.create(
                ticket=ticket,
                usuario=request.user,
                comentario="Atención cerrada definitivamente.",
                estado_ticket=ticket.estado
            )
            messages.success(request, 'Ticket cerrado definitivamente.')
            
    return redirect('ticket_detalle', ticket_id=ticket.id)


@login_required
def ticket_reabrir(request, ticket_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
        
    ticket = get_object_or_404(TicketServicio, id=ticket_id)
    if request.method == 'POST':
        motivo = request.POST.get('motivo_reapertura', '').strip()
        if not motivo:
            messages.error(request, 'Debes indicar el motivo de la reapertura.')
            return redirect('ticket_detalle', ticket_id=ticket.id)
            
        with transaction.atomic():
            ticket.estado = 'PROCESO'
            ticket.motivo_reapertura = motivo
            ticket.solucion = None
            ticket.observacion_resolucion = None
            ticket.resolved_at = None
            ticket.closed_at = None
            ticket.save()
            
            SeguimientoTicket.objects.create(
                ticket=ticket,
                usuario=request.user,
                comentario=f"Ticket reabierto. Motivo: {motivo}",
                estado_ticket=ticket.estado
            )
            messages.success(request, 'Ticket reabierto y asignado en proceso.')
            
    return redirect('ticket_detalle', ticket_id=ticket.id)


@login_required
def ticket_seguimiento(request, ticket_id):
    if not _es_recepcionista(request.user) and not _es_housekeeping(request.user):
        return _acceso_denegado(request)
        
    ticket = get_object_or_404(TicketServicio, id=ticket_id)
    if request.method == 'POST':
        comentario = request.POST.get('comentario', '').strip()
        nuevo_estado = request.POST.get('estado')
        
        if not comentario:
            messages.error(request, 'Debes ingresar un comentario.')
            return redirect('ticket_detalle', ticket_id=ticket.id)
            
        with transaction.atomic():
            if nuevo_estado and nuevo_estado in dict(TicketServicio.ESTADOS):
                ticket.estado = nuevo_estado
                ticket.save()
                
            SeguimientoTicket.objects.create(
                ticket=ticket,
                usuario=request.user,
                comentario=comentario,
                estado_ticket=ticket.estado
            )
            messages.success(request, 'Seguimiento registrado.')
            
    return redirect('ticket_detalle', ticket_id=ticket.id)


@login_required
def ticket_agregar_cargo(request, ticket_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
        
    ticket = get_object_or_404(TicketServicio, id=ticket_id)
    if request.method == 'POST':
        concepto = request.POST.get('concepto', '').strip()
        monto = request.POST.get('monto')
        tipo_cargo = request.POST.get('tipo', CargoEstancia.OTRO)
        
        if not concepto or not monto:
            messages.error(request, 'Concepto y monto son obligatorios.')
            return redirect('ticket_detalle', ticket_id=ticket.id)
            
        try:
            monto_decimal = Decimal(monto)
            if monto_decimal <= 0:
                messages.error(request, 'El monto debe ser mayor a cero.')
                return redirect('ticket_detalle', ticket_id=ticket.id)
                
            estancia = ticket.estancia
            with transaction.atomic():
                cargo = CargoEstancia.objects.create(
                    estancia=estancia,
                    concepto=f"{concepto} (Ticket: {ticket.numero_atencion})",
                    monto=monto_decimal,
                    tipo=tipo_cargo
                )
                
                if hasattr(estancia, 'folio'):
                    estancia.folio.calcular_totales()
                    
                SeguimientoTicket.objects.create(
                    ticket=ticket,
                    usuario=request.user,
                    comentario=f"Se asoció cargo extra al folio del hospedaje: {concepto} por S/. {monto_decimal}",
                    estado_ticket=ticket.estado
                )
                
                registrar_auditoria(
                    usuario=request.user,
                    accion="Cargo Extra de Ticket Registrado",
                    registro_id=cargo.id,
                    tabla_afectada="estancias_cargoestancia",
                    estado_nuevo=f"ID: {cargo.id}, Ticket: {ticket.numero_atencion}, Monto: S/. {monto_decimal}"
                )
                
                messages.success(request, 'Cargo asociado al folio de la estancia correctamente.')
        except Exception as e:
            messages.error(request, f'Error al registrar cargo: {str(e)}')
            
    return redirect('ticket_detalle', ticket_id=ticket.id)
