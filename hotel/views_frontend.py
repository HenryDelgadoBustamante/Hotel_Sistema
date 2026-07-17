from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from datetime import date, datetime, timedelta, time
from decimal import Decimal
from django.http import JsonResponse
from hotel.models import Habitacion, Hotel, TipoHabitacion
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia, CargoEstancia, Folio, Pago, Reembolso
from utils.auditoria import log_action
from reportes.models import registrar_auditoria
from config.views_shared import _es_admin, _es_recepcionista, _es_housekeeping, _solo_housekeeping, _acceso_denegado, parse_room_gallery, parse_datetime_local, parse_date_local, calcular_cargo_salida_tardia


@login_required
def api_habitaciones_disponibles(request):
    fecha_entrada_str = request.GET.get('entrada')
    fecha_salida_str = request.GET.get('salida')
    hora_entrada_str = request.GET.get('hora_entrada')
    duracion = float(request.GET.get('duracion', 3))
    modalidad = request.GET.get('modalidad', 'DIA')

    habitaciones = Habitacion.objects.exclude(estado='MANTENIMIENTO').select_related('tipo')
    
    target_entrada = None
    target_salida = None

    try:
        from datetime import time
        if modalidad == 'DIA' and fecha_entrada_str and fecha_salida_str:
            fecha_entrada = parse_date_local(fecha_entrada_str)
            fecha_salida = parse_date_local(fecha_salida_str)
            if fecha_entrada and fecha_salida:
                hotel = Hotel.objects.first()
                hora_in = hotel.hora_checkin_estandar if (hotel and hasattr(hotel, 'hora_checkin_estandar')) else time(15, 0)
                hora_out = hotel.hora_checkout_estandar if (hotel and hasattr(hotel, 'hora_checkout_estandar')) else time(12, 0)
                target_entrada = timezone.make_aware(datetime.combine(fecha_entrada, hora_in))
                target_salida = timezone.make_aware(datetime.combine(fecha_salida, hora_out))
        elif modalidad == 'HORA' and hora_entrada_str:
            fecha_hora_entrada = parse_datetime_local(hora_entrada_str)
            if fecha_hora_entrada:
                target_entrada = fecha_hora_entrada
                target_salida = fecha_hora_entrada + timedelta(hours=duracion)
    except Exception:
        pass

    if target_entrada and target_salida:
        reservas_cruzadas = Reserva.objects.filter(
            estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
            fecha_hora_entrada__lt=target_salida,
            fecha_hora_salida__gt=target_entrada
        ).values_list('habitacion_id', flat=True)
        
        habitaciones = habitaciones.exclude(id__in=reservas_cruzadas)

    data = []
    for h in habitaciones.order_by('piso', 'numero'):
        data.append({
            'id': h.id,
            'numero': h.numero,
            'piso': h.piso,
            'estado_label': h.get_estado_display(),
            'tipo_nombre': h.tipo.nombre,
            'precio_base': str(h.tipo.precio_base)
        })
    return JsonResponse({'habitaciones': data})


@login_required
def housekeeping_view(request):
    if not _es_housekeeping(request.user):
        return _acceso_denegado(request)
    piso = request.GET.get('piso', '')
    habitaciones = list(Habitacion.objects.filter(estado='LIMPIEZA').select_related('tipo').order_by('piso', 'numero'))
    
    from datetime import timedelta
    limite = timezone.now() - timedelta(minutes=10)
    
    from estancias.models import Estancia
    estancias_recientes = Estancia.objects.filter(
        estado=Estancia.FINALIZADA,
        habitacion__estado=Habitacion.LIMPIEZA,
        fecha_checkout__gte=limite
    ).select_related('reserva__huesped')
    
    urgentes_map = {e.habitacion_id: e for e in estancias_recientes}
    
    for hab in habitaciones:
        estancia = urgentes_map.get(hab.id)
        if estancia:
            hab.is_urgente = True
            checkout_local = timezone.localtime(estancia.fecha_checkout)
            hab.checkout_hora = checkout_local.strftime('%H:%M')
            hab.minutos_desde_checkout = int((timezone.now() - estancia.fecha_checkout).total_seconds() // 60)
            huesped = estancia.reserva.huesped
            hab.huesped_checkout = f"{huesped.nombres} {huesped.apellidos}"
        else:
            hab.is_urgente = False
            
    if piso:
        habitaciones = [h for h in habitaciones if str(h.piso) == piso]
        
    pisos_disponibles = Habitacion.objects.values_list('piso', flat=True).distinct().order_by('piso')

    return render(request, 'housekeeping.html', {
        'habitaciones': habitaciones,
        'piso_filtro': piso,
        'pisos': pisos_disponibles
    })


@login_required
def housekeeping_estado(request, hab_id):
    if not _es_housekeeping(request.user):
        return _acceso_denegado(request)
    if request.method == 'POST':
        hab = get_object_or_404(Habitacion, id=hab_id)
        nuevo_estado = request.POST.get('estado')
        if nuevo_estado in ['DISPONIBLE', 'LIMPIEZA', 'MANTENIMIENTO']:
            anterior = hab.estado
            hab.estado = nuevo_estado
            hab.save()
            
            observacion = f"Cambio estado de Hab. {hab.numero} de {anterior} a {nuevo_estado}."
            
            detalles = []
            if request.POST.get('check_estado') == 'on':
                detalles.append("Estado general de la habitación verificado")
            if request.POST.get('check_danos') == 'on':
                detalles.append("Verificación de daños completada")
            if request.POST.get('check_objetos') == 'on':
                detalles.append("Búsqueda de objetos olvidados completada")
            if request.POST.get('check_limpieza') == 'on':
                detalles.append("Limpieza y reposición completa realizada")
            
            obs_texto = request.POST.get('observaciones_inspeccion', '').strip()
            if detalles:
                observacion += " Tareas realizadas: " + ", ".join(detalles) + "."
            if obs_texto:
                observacion += f" Observaciones: {obs_texto}"
                
            registrar_auditoria(
                usuario=request.user,
                accion="Housekeeping Estado Modificado",
                registro_id=hab.id,
                tabla_afectada="hotel_habitacion",
                estado_anterior=anterior,
                estado_nuevo=nuevo_estado,
                observacion=observacion
            )
            messages.success(request, f'Habitación {hab.numero} actualizada a {nuevo_estado}.')
    return redirect('housekeeping')


@login_required
def habitaciones_lista(request):
    if not _es_recepcionista(request.user) and not _es_housekeeping(request.user):
        return _acceso_denegado(request)
    from django.utils import timezone
    from datetime import datetime, time
    hoy = timezone.now().date()
    ahora = timezone.now()
    
    estado_filtro = request.GET.get('estado', '')
    vista = request.GET.get('vista', 'grid')
    
    habitaciones = Habitacion.objects.select_related('tipo', 'hotel').prefetch_related('estancias__reserva').all().order_by('piso', 'numero')
    if estado_filtro:
        habitaciones = habitaciones.filter(estado=estado_filtro)
        
    pisos = habitaciones.values_list('piso', flat=True).distinct().order_by('piso')
    
    reservas_hoy = Reserva.objects.filter(
        fecha_entrada=hoy, estado__in=['PENDIENTE', 'CONFIRMADA']
    ).select_related('habitacion')
    reservas_dict = {r.habitacion_id: r for r in reservas_hoy if r.habitacion_id}
    
    checkin_time = timezone.make_aware(datetime.combine(hoy, time(14, 0)))

    for hab in habitaciones:
        hab.estado_visual = hab.estado
        if hab.estado == 'OCUPADA':
            for e in hab.estancias.all():
                if e.estado == 'ACTIVA' and e.reserva.fecha_salida < hoy:
                    hab.estado_visual = 'VENCIDA'
                    break
        elif hab.estado == 'DISPONIBLE':
            r = reservas_dict.get(hab.id)
            if r:
                hab.reserva_hoy = r
                if ahora > checkin_time:
                    hab.estado_visual = 'RETRASO'
                else:
                    hab.estado_visual = 'RESERVADA'
                    
    stats = {
        'disponible': sum(1 for h in habitaciones if h.estado_visual == 'DISPONIBLE'),
        'ocupada': sum(1 for h in habitaciones if h.estado_visual == 'OCUPADA'),
        'limpieza': sum(1 for h in habitaciones if h.estado_visual == 'LIMPIEZA'),
        'mantenimiento': sum(1 for h in habitaciones if h.estado_visual == 'MANTENIMIENTO'),
        'vencida': sum(1 for h in habitaciones if h.estado_visual == 'VENCIDA'),
        'retraso': sum(1 for h in habitaciones if h.estado_visual == 'RETRASO'),
    }
    
    return render(request, 'habitaciones/lista.html', {
        'habitaciones': habitaciones,
        'estado_filtro': estado_filtro,
        'vista': vista,
        'stats': stats,
        'pisos': pisos,
    })


@login_required
def habitacion_nueva(request):
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos para crear habitaciones.')
        return redirect('habitaciones_lista')

    if request.method == 'POST':
        try:
            hotel = Hotel.objects.get(id=request.POST['hotel'])
            tipo = TipoHabitacion.objects.get(id=request.POST['tipo'])
            Habitacion.objects.create(
                hotel=hotel,
                tipo=tipo,
                numero=request.POST['numero'],
                piso=request.POST['piso'],
                estado=request.POST.get('estado', 'DISPONIBLE'),
                imagen_url=request.POST.get('imagen_url') or None,
                imagenes_urls=parse_room_gallery(
                    request.POST.get('imagenes_urls', ''),
                    request.POST.get('imagen_url') or '',
                ),
            )
            messages.success(request, 'Habitación creada correctamente.')
            return redirect('habitaciones_lista')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    
    return render(request, 'habitaciones/form.html', {
        'hoteles': Hotel.objects.all(),
        'tipos': TipoHabitacion.objects.all(),
    })


@login_required
def habitacion_editar(request, hab_id):
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos para editar habitaciones.')
        return redirect('habitaciones_lista')

    hab = get_object_or_404(Habitacion, id=hab_id)
    if request.method == 'POST':
        try:
            hab.hotel = Hotel.objects.get(id=request.POST['hotel'])
            hab.tipo = TipoHabitacion.objects.get(id=request.POST['tipo'])
            hab.numero = request.POST['numero']
            hab.piso = request.POST['piso']
            hab.estado = request.POST.get('estado', hab.estado)
            hab.imagen_url = request.POST.get('imagen_url') or None
            hab.imagenes_urls = parse_room_gallery(
                request.POST.get('imagenes_urls', ''),
                request.POST.get('imagen_url') or '',
            )
            hab.save()
            messages.success(request, 'Habitación actualizada correctamente.')
            return redirect('habitaciones_lista')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    
    return render(request, 'habitaciones/form.html', {
        'habitacion': hab,
        'hoteles': Hotel.objects.all(),
        'tipos': TipoHabitacion.objects.all(),
    })


@login_required
def api_habitaciones_housekeeping_recientes(request):
    """
    Obs. 2: Retorna habitaciones cuyo check-out se realizó hace ≤ 10 minutos.
    Estas deben ser inspeccionadas urgentemente por Housekeeping.
    """
    from django.http import JsonResponse
    from datetime import timedelta

    now = timezone.now()
    limite = now - timedelta(minutes=10)

    estancias_recientes = Estancia.objects.filter(
        estado=Estancia.FINALIZADA,
        habitacion__estado=Habitacion.LIMPIEZA,
        fecha_checkout__gte=limite
    ).select_related('habitacion', 'habitacion__tipo', 'reserva__huesped').order_by('-fecha_checkout')

    data = []
    for e in estancias_recientes:
        checkout_local = timezone.localtime(e.fecha_checkout)
        minutos_desde_checkout = int((now - e.fecha_checkout).total_seconds() // 60)
        huesped = e.reserva.huesped
        data.append({
            'estancia_id': e.id,
            'habitacion': e.habitacion.numero,
            'piso': e.habitacion.piso,
            'tipo': e.habitacion.tipo.nombre,
            'huesped': f"{huesped.nombres} {huesped.apellidos}",
            'checkout_hora': checkout_local.strftime('%H:%M'),
            'minutos_desde_checkout': minutos_desde_checkout,
            'urgente': True,
        })

    return JsonResponse({
        'habitaciones_urgentes': data,
        'total': len(data),
    })


@login_required
def actualizar_estado_habitacion(request, hab_id):
    """
    HOT-HOS-003 – Liberar / Cambiar estado de habitación manualmente.
    Permite a recepcionistas y administradores cambiar el estado físico de una habitación
    (por ejemplo, pasarla de LIMPIEZA o MANTENIMIENTO a DISPONIBLE, o viceversa).
    No permite modificar habitaciones ocupadas de forma directa.
    """
    if not (_es_recepcionista(request.user) or _es_admin(request.user)):
        return _acceso_denegado(request)

    hab = get_object_or_404(Habitacion, id=hab_id)
    
    if request.method == 'POST':
        nuevo_estado = request.POST.get('estado', '').strip().upper()
        estados_validos = [Habitacion.DISPONIBLE, Habitacion.LIMPIEZA, Habitacion.MANTENIMIENTO]

        if nuevo_estado not in estados_validos:
            messages.error(request, f'Estado inválido. Los estados permitidos son: {", ".join(estados_validos)}')
            return redirect('dashboard')

        if hab.estado == Habitacion.OCUPADA:
            messages.error(request, 'No se puede cambiar el estado de una habitación ocupada de forma directa. Debe realizar un check-out o un traslado de habitación.')
            return redirect('dashboard')

        anterior = hab.estado
        hab.estado = nuevo_estado
        hab.save()

        registrar_auditoria(
            usuario=request.user,
            accion="Habitación Estado Modificado",
            registro_id=hab.id,
            tabla_afectada="hotel_habitacion",
            estado_anterior=anterior,
            estado_nuevo=nuevo_estado,
            observacion=f"Cambio manual de estado de Hab. {hab.numero} de {anterior} a {nuevo_estado} (Asignar/Liberar Habitación)"
        )

        messages.success(request, f'La Habitación {hab.numero} se actualizó correctamente a {hab.get_estado_display()}.')

    return redirect('dashboard')


@login_required
def hotel_configuracion(request):
    if not (_es_admin(request.user) or _es_recepcionista(request.user) or _es_housekeeping(request.user)):
        return _acceso_denegado(request)

    from hotel.models import Hotel
    from reportes.models import Auditoria
    
    hotel = Hotel.objects.first()
    if not hotel:
        hotel = Hotel.objects.create(
            nombre="Florida",
            ruc="20548732032",
            direccion="La Victoria, Lima",
            estrellas=4,
            telefono="947327362",
            correo="contacto@hotelflorida.com",
            razon_social="Hotel Florida S.A.C.",
            hora_checkin_estandar=time(15, 0),
            hora_checkout_estandar=time(12, 0),
            permitir_early_checkin=True,
            cobrar_early_checkin=False,
            early_checkin_tipo_cargo='FIJO',
            early_checkin_monto_porcentaje=Decimal('0.00'),
            permitir_late_checkout=True,
            late_checkout_tipo_cargo='FIJO',
            late_checkout_monto_porcentaje=Decimal('50.00'),
            late_checkout_hora_maxima=time(16, 0)
        )

    es_admin_user = _es_admin(request.user)
    es_recep_user = _es_recepcionista(request.user)
    es_house_user = _solo_housekeeping(request.user)

    mostrar_costos = not es_house_user
    mostrar_historial = not es_house_user

    historial = []
    if mostrar_historial:
        historial = Auditoria.objects.filter(tabla_afectada="hotel_hotel", accion="Cambio de Configuración").order_by('-fecha')[:50]

    if request.method == 'POST':
        if not es_admin_user:
            return _acceso_denegado(request)

        try:
            nombre = request.POST.get('nombre', '').strip()
            razon_social = request.POST.get('razon_social', '').strip() or None
            ruc = request.POST.get('ruc', '').strip()
            direccion = request.POST.get('direccion', '').strip()
            telefono = request.POST.get('telefono', '').strip()
            correo = request.POST.get('correo', '').strip() or None

            hora_in_str = request.POST.get('hora_checkin_estandar', '').strip()
            hora_out_str = request.POST.get('hora_checkout_estandar', '').strip()

            permitir_early = request.POST.get('permitir_early_checkin') in ['true', 'on', 'True']
            costo_early_str = request.POST.get('costo_early_checkin', '0.00').strip()

            permitir_late = request.POST.get('permitir_late_checkout') in ['true', 'on', 'True']
            costo_late_str = request.POST.get('costo_late_checkout', '0.00').strip()
            late_max_str = request.POST.get('late_checkout_hora_maxima', '').strip() or None

            if not nombre:
                raise ValidationError("El nombre comercial del hotel es obligatorio.")
            if not ruc:
                raise ValidationError("El RUC o documento fiscal es obligatorio.")
            if not hora_in_str:
                raise ValidationError("La hora oficial de Check-In es obligatoria.")
            if not hora_out_str:
                raise ValidationError("La hora oficial de Check-Out es obligatoria.")

            def parse_time(t_str):
                parts = t_str.split(':')
                return time(int(parts[0]), int(parts[1]))

            hora_in = parse_time(hora_in_str)
            hora_out = parse_time(hora_out_str)

            late_max = None
            if permitir_late:
                if not late_max_str:
                    raise ValidationError("La hora máxima de Late Check-Out es obligatoria si el servicio está habilitado.")
                late_max = parse_time(late_max_str)
                if late_max <= hora_out:
                    raise ValidationError("La hora máxima de Late Check-Out debe ser posterior a la hora oficial de Check-Out.")

            costo_early = Decimal(costo_early_str)
            costo_late = Decimal(costo_late_str)

            if costo_early < 0:
                raise ValidationError("El costo de Early Check-In no puede ser negativo.")
            if costo_late < 0:
                raise ValidationError("El costo de Late Check-Out no puede ser negativo.")

            cambios = []
            
            def check_change(field, old, new, label):
                if old != new:
                    cambios.append((field, old, new, label))

            check_change('nombre', hotel.nombre, nombre, 'Nombre Comercial')
            check_change('razon_social', hotel.razon_social, razon_social, 'Razón Social')
            check_change('ruc', hotel.ruc, ruc, 'RUC')
            check_change('direccion', hotel.direccion, direccion, 'Dirección')
            check_change('telefono', hotel.telefono, telefono, 'Teléfono')
            check_change('correo', hotel.correo, correo, 'Correo Electrónico')
            check_change('hora_checkin_estandar', hotel.hora_checkin_estandar, hora_in, 'Hora Oficial Check-In')
            check_change('hora_checkout_estandar', hotel.hora_checkout_estandar, hora_out, 'Hora Oficial Check-Out')
            check_change('permitir_early_checkin', hotel.permitir_early_checkin, permitir_early, 'Permitir Early Check-In')
            
            cobrar_early = costo_early > 0
            check_change('cobrar_early_checkin', hotel.cobrar_early_checkin, cobrar_early, 'Cobrar Early Check-In')
            check_change('early_checkin_monto_porcentaje', hotel.early_checkin_monto_porcentaje, costo_early, 'Costo Early Check-In')
            
            check_change('permitir_late_checkout', hotel.permitir_late_checkout, permitir_late, 'Permitir Late Check-Out')
            check_change('late_checkout_monto_porcentaje', hotel.late_checkout_monto_porcentaje, costo_late, 'Costo Late Check-Out')
            check_change('late_checkout_hora_maxima', hotel.late_checkout_hora_maxima, late_max, 'Hora Máxima Late Check-Out')

            if cambios:
                with transaction.atomic():
                    hotel.nombre = nombre
                    hotel.razon_social = razon_social
                    hotel.ruc = ruc
                    hotel.direccion = direccion
                    hotel.telefono = telefono
                    hotel.correo = correo
                    hotel.hora_checkin_estandar = hora_in
                    hotel.hora_checkout_estandar = hora_out
                    hotel.permitir_early_checkin = permitir_early
                    hotel.cobrar_early_checkin = cobrar_early
                    hotel.early_checkin_tipo_cargo = 'FIJO'
                    hotel.early_checkin_monto_porcentaje = costo_early
                    hotel.permitir_late_checkout = permitir_late
                    hotel.late_checkout_tipo_cargo = 'FIJO'
                    hotel.late_checkout_monto_porcentaje = costo_late
                    hotel.late_checkout_hora_maxima = late_max
                    hotel.save()

                    for field, old, new, label in cambios:
                        registrar_auditoria(
                            usuario=request.user,
                            accion="Cambio de Configuración",
                            registro_id=hotel.id,
                            tabla_afectada="hotel_hotel",
                            estado_anterior=str(old) if old is not None else "",
                            estado_nuevo=str(new) if new is not None else "",
                            observacion=f"Modificó el parámetro: {label}"
                        )
                messages.success(request, "Configuración guardada y auditada correctamente.")
            else:
                messages.info(request, "No se detectaron cambios en la configuración.")

            return redirect('configuracion_hotel')
        except Exception as e:
            messages.error(request, str(e))

    return render(request, 'hotel/configuracion.html', {
        'hotel': hotel,
        'mostrar_costos': mostrar_costos,
        'mostrar_historial': mostrar_historial,
        'historial': historial,
        'es_admin': es_admin_user
    })
