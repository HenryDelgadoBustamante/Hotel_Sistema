from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Sum
from django.core.exceptions import ValidationError
from datetime import date, datetime, timedelta
from decimal import Decimal
from hotel.models import Habitacion, Hotel, TipoHabitacion
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia, CargoEstancia, Folio, Pago, Reembolso
from utils.auditoria import log_action
from reportes.models import registrar_auditoria
from caja.services import obtener_caja_abierta, registrar_movimiento_pago
from config.views_shared import _es_recepcionista, _acceso_denegado, parse_datetime_local, parse_date_local


@login_required
def reservas_lista(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    estado = request.GET.get('estado')
    query = request.GET.get('q', '').strip()
    reservas = Reserva.objects.select_related('huesped', 'habitacion').all().order_by('-created_at')
    if estado:
        reservas = reservas.filter(estado=estado)
    if query:
        if query.isdigit():
            reservas = reservas.filter(id=query)
        else:
            reservas = reservas.filter(
                Q(huesped__nombres__icontains=query) |
                Q(huesped__apellidos__icontains=query) |
                Q(huesped__num_doc__icontains=query)
            )

    hoy = timezone.now().date()
    llegadas_hoy = Reserva.objects.filter(fecha_entrada=hoy, estado__in=['PENDIENTE', 'CONFIRMADA'])
    en_casa = Estancia.objects.filter(estado='ACTIVA')
    salidas_hoy = Estancia.objects.filter(estado='ACTIVA', reserva__fecha_salida=hoy)

    return render(request, 'reservas/lista.html', {
        'reservas': reservas, 
        'query': query, 
        'estado': estado,
        'llegadas_hoy': llegadas_hoy,
        'en_casa': en_casa,
        'salidas_hoy': salidas_hoy
    })


@login_required
def reserva_detalle(request, reserva_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    reserva = get_object_or_404(
        Reserva.objects.select_related('huesped', 'habitacion__tipo', 'hotel'),
        id=reserva_id,
    )
    estancia = getattr(reserva, 'estancia', None)
    return render(request, 'reservas/detalle.html', {
        'reserva': reserva,
        'estancia': estancia,
    })


@login_required
def reserva_nueva(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    if request.method == 'POST':
        from django.db import transaction
        try:
            huesped_id = request.POST.get('huesped_id')
            if huesped_id:
                huesped = Huesped.objects.get(id=huesped_id)
            else:
                huesped = Huesped.objects.get(num_doc=request.POST['huesped_doc'])
            habitacion = Habitacion.objects.get(id=request.POST['habitacion'])
            modalidad = request.POST.get('modalidad', Reserva.POR_DIA)
            fecha_hora_entrada = None
            duracion_horas = request.POST.get('duracion_horas') or 0

            if modalidad == Reserva.POR_HORA:
                fecha_hora_entrada = parse_datetime_local(request.POST.get('fecha_hora_entrada'))
                if not fecha_hora_entrada:
                    raise ValidationError('Debes indicar la fecha y hora de ingreso.')
                fecha_entrada = fecha_hora_entrada.date()
                fecha_salida = (fecha_hora_entrada + timedelta(hours=float(duracion_horas or 3))).date()
            else:
                fecha_entrada = parse_date_local(request.POST.get('fecha_entrada'))
                fecha_salida = parse_date_local(
                    request.POST.get('fecha_salida') or request.POST.get('fecha_entrada')
                )
                if not fecha_entrada or not fecha_salida:
                    raise ValidationError('Debes indicar las fechas de entrada y salida.')
            import json
            productos_json = request.POST.get('productos_json', '[]')
            productos_data = []
            if productos_json:
                try:
                    productos_data = json.loads(productos_json)
                except Exception:
                    pass

            original_obs = request.POST.get('observaciones', '')
            if productos_data:
                productos_desc = "\n\n--- Insumos Adicionales Solicitados ---\n"
                for item in productos_data:
                    productos_desc += f"- {item['nombre']} x {item['cantidad']} (S/. {Decimal(str(item['precio'])) * int(item['cantidad']):.2f})\n"
                productos_desc += f"\n__JSON_PRODUCTOS_START__{json.dumps(productos_data)}__JSON_PRODUCTOS_END__"
                reserva_obs = original_obs + productos_desc
            else:
                reserva_obs = original_obs

            with transaction.atomic():
                reserva = Reserva.objects.create(
                    hotel=habitacion.hotel,
                    huesped=huesped,
                    habitacion=habitacion,
                    fecha_entrada=fecha_entrada,
                    fecha_salida=fecha_salida,
                    fecha_hora_entrada=fecha_hora_entrada,
                    modalidad=modalidad,
                    duracion_horas=duracion_horas,
                    num_adultos=int(request.POST.get('num_adultos', 1)),
                    origen=request.POST.get('origen', 'DIRECTO'),
                    observaciones=reserva_obs,
                )
                
                base_price = reserva.calcular_precio()
                prod_price = Decimal('0.00')
                for item in productos_data:
                    prod_price += Decimal(str(item['precio'])) * int(item['cantidad'])
                
                reserva.precio_total = base_price + prod_price
                reserva.save()

                registrar_pago = request.POST.get('registrar_pago') == 'on'
                if registrar_pago:
                    monto = request.POST.get('pago_monto')
                    metodo_pago = request.POST.get('pago_metodo_pago', Pago.EFECTIVO)
                    transaccion_id = request.POST.get('pago_transaccion_id') or None

                    if not monto:
                        raise ValidationError('Debes especificar un monto para el pago anticipado.')
                    
                    monto_decimal = Decimal(monto)
                    if monto_decimal <= 0:
                        raise ValidationError('El monto del pago debe ser mayor a cero.')
                    if monto_decimal > reserva.precio_total:
                        raise ValidationError(f'El monto del pago no puede ser mayor que el total de la reserva (S/. {reserva.precio_total:.2f}).')
                    if metodo_pago != Pago.EFECTIVO and not transaccion_id:
                        raise ValidationError('Debes ingresar el ID de transacción para pagos electrónicos/bancarios.')
                    
                    from caja.services import obtener_caja_abierta, registrar_movimiento_pago
                    caja = obtener_caja_abierta(request.user)
                    if not caja:
                        raise ValidationError('No tienes una caja abierta. Es obligatorio aperturar tu caja antes de registrar un pago.')
                    
                    pago = Pago.objects.create(
                        reserva=reserva,
                        monto=monto_decimal,
                        metodo_pago=metodo_pago,
                        transaccion_id=transaccion_id
                    )
                    registrar_movimiento_pago(pago, request.user)

                    registrar_auditoria(
                        usuario=request.user,
                        accion="Registrar Pago Anticipado",
                        registro_id=pago.id,
                        tabla_afectada="estancias_pago",
                        estado_nuevo=f"ID: {pago.id}, Reserva: {reserva.id}, Monto: S/. {monto_decimal}, Metodo: {metodo_pago}"
                    )

                registrar_auditoria(
                    usuario=request.user,
                    accion="Crear Reserva",
                    registro_id=reserva.id,
                    tabla_afectada="reservas_reserva",
                    estado_nuevo=f"ID: {reserva.id}, Huesped: {reserva.huesped.nombres} {reserva.huesped.apellidos}, Hab: {reserva.habitacion.numero}, Total: S/. {reserva.precio_total}"
                )

                messages.success(request, f'Reserva #{reserva.id} creada correctamente.')
                if request.POST.get('accion') == 'checkin':
                    return redirect('reserva_checkin', reserva_id=reserva.id)
                return redirect('reservas_lista')
        except Exception as e:
            messages.error(request, f'Error al crear la reserva: {str(e)}')

    selected_habitacion_id = request.GET.get('habitacion', '')
    selected_huesped = None
    huesped_id = request.GET.get('huesped')
    if huesped_id:
        selected_huesped = Huesped.objects.filter(id=huesped_id).first()

    from inventario.models import Producto
    productos_inventario = Producto.objects.filter(estado='ACTIVO', es_vendible=True).select_related('categoria').order_by('nombre')

    return render(request, 'reservas/nueva.html', {
        'huespedes': Huesped.objects.all().order_by('nombres', 'apellidos'),
        'habitaciones': Habitacion.objects.filter(estado=Habitacion.DISPONIBLE).select_related('tipo').order_by('piso', 'numero'),
        'selected_habitacion_id': selected_habitacion_id,
        'selected_huesped': selected_huesped,
        'productos_inventario': productos_inventario,
        'hora_actual': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
    })


@login_required
def reservas_calendario(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    from datetime import timedelta
    from django.utils import timezone
    
    hoy = timezone.now().date()
    fecha_inicio_str = request.GET.get('fecha_inicio')
    if fecha_inicio_str:
        try:
            from datetime import datetime
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        except:
            fecha_inicio = hoy
    else:
        fecha_inicio = hoy

    dias = [fecha_inicio + timedelta(days=i) for i in range(30)]
    fecha_fin = dias[-1]
    
    habitaciones = Habitacion.objects.select_related('tipo').all().order_by('piso', 'numero')
    
    tipo_id = request.GET.get('tipo')
    if tipo_id:
        habitaciones = habitaciones.filter(tipo_id=tipo_id)
        
    reservas = Reserva.objects.filter(
        fecha_entrada__lte=fecha_fin,
        fecha_salida__gte=fecha_inicio,
        estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN']
    ).select_related('huesped', 'habitacion')
    
    eventos = []
    for r in reservas:
        if r.habitacion:
            inicio = max(r.fecha_entrada, fecha_inicio)
            fin = min(r.fecha_salida, fecha_fin)
            dias_reserva = (fin - inicio).days
            offset = (inicio - fecha_inicio).days
            
            color = '#f59e0b' if r.estado == 'PENDIENTE' else '#3b82f6' if r.estado == 'CONFIRMADA' else '#10b981'
            
            eventos.append({
                'id': r.id,
                'habitacion_id': r.habitacion.id,
                'huesped': f"{r.huesped.nombres} {r.huesped.apellidos}",
                'offset': offset,
                'width': dias_reserva or 1,
                'color': color,
                'estado': r.estado
            })
            
    tipos = TipoHabitacion.objects.all()
    
    return render(request, 'reservas/calendario.html', {
        'dias': dias,
        'habitaciones': habitaciones,
        'eventos': eventos,
        'tipos': tipos,
        'fecha_inicio': fecha_inicio,
        'tipo_id': int(tipo_id) if tipo_id else ''
    })


@login_required
def consultar_disponibilidad(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    
    fecha_entrada_str = request.GET.get('fecha_entrada')
    fecha_salida_str = request.GET.get('fecha_salida')
    tipo_hab = request.GET.get('tipo_habitacion')
    capacidad = request.GET.get('capacidad')
    
    habitaciones = Habitacion.objects.exclude(estado='MANTENIMIENTO').select_related('tipo')
    
    if tipo_hab:
        habitaciones = habitaciones.filter(tipo_id=tipo_hab)
    if capacidad:
        habitaciones = habitaciones.filter(tipo__capacidad__gte=int(capacidad))
    
    if fecha_entrada_str and fecha_salida_str:
        try:
            from datetime import datetime, time
            fecha_entrada = parse_date_local(fecha_entrada_str)
            fecha_salida = parse_date_local(fecha_salida_str)
            
            hotel = Hotel.objects.first()
            hora_in = hotel.hora_checkin_estandar if (hotel and hasattr(hotel, 'hora_checkin_estandar')) else time(15, 0)
            hora_out = hotel.hora_checkout_estandar if (hotel and hasattr(hotel, 'hora_checkout_estandar')) else time(12, 0)
            target_entrada = timezone.make_aware(datetime.combine(fecha_entrada, hora_in))
            target_salida = timezone.make_aware(datetime.combine(fecha_salida, hora_out))
            
            reservados = Reserva.objects.filter(
                estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
                fecha_hora_entrada__lt=target_salida,
                fecha_hora_salida__gt=target_entrada
            ).values_list('habitacion_id', flat=True)
            
            habitaciones = habitaciones.exclude(id__in=reservados)
        except:
            pass
    
    tipos = TipoHabitacion.objects.all()
    
    return render(request, 'reservas/disponibilidad.html', {
        'habitaciones': habitaciones,
        'tipos': tipos,
        'fecha_entrada': fecha_entrada_str,
        'fecha_salida': fecha_salida_str,
        'tipo_hab': int(tipo_hab) if tipo_hab else '',
        'capacidad': capacidad,
    })


@login_required
def reserva_imprimir_ficha(request, reserva_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    reserva = get_object_or_404(Reserva.objects.select_related('huesped', 'habitacion__tipo', 'hotel'), id=reserva_id)
    return render(request, 'reservas/imprimir_ficha.html', {'reserva': reserva})


@login_required
def reserva_editar(request, reserva_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if reserva.estado in ['CHECKIN', 'CHECKOUT', 'CANCELADA']:
        messages.error(request, 'No se puede modificar una reserva en estado check-in, check-out o cancelada.')
        return redirect('reserva_detalle', reserva_id=reserva.id)

    if request.method == 'POST':
        try:
            huesped_id = request.POST.get('huesped_id')
            if huesped_id:
                reserva.huesped = Huesped.objects.get(id=huesped_id)
            else:
                reserva.huesped = Huesped.objects.get(num_doc=request.POST['huesped_doc'])

            reserva.habitacion = Habitacion.objects.get(id=request.POST['habitacion'])
            reserva.modalidad = request.POST.get('modalidad', Reserva.POR_DIA)
            reserva.num_adultos = int(request.POST.get('num_adultos', 1))
            reserva.origen = request.POST.get('origen', 'DIRECTO')
            reserva.observaciones = request.POST.get('observaciones', '')

            if reserva.modalidad == Reserva.POR_HORA:
                reserva.fecha_hora_entrada = parse_datetime_local(request.POST.get('fecha_hora_entrada'))
                if not reserva.fecha_hora_entrada:
                    raise ValidationError('Debes indicar la fecha y hora de ingreso.')
                reserva.duracion_horas = request.POST.get('duracion_horas') or 0
                reserva.fecha_entrada = reserva.fecha_hora_entrada.date()
                reserva.fecha_salida = (reserva.fecha_hora_entrada + timedelta(hours=float(reserva.duracion_horas or 3))).date()
            else:
                reserva.fecha_entrada = parse_date_local(request.POST.get('fecha_entrada'))
                reserva.fecha_salida = parse_date_local(
                    request.POST.get('fecha_salida') or request.POST.get('fecha_entrada')
                )
                if not reserva.fecha_entrada or not reserva.fecha_salida:
                    raise ValidationError('Debes indicar las fechas de entrada y salida.')
                reserva.fecha_hora_entrada = None
                reserva.duracion_horas = 0

            reserva.precio_total = reserva.calcular_precio()
            reserva.save()

            registrar_auditoria(
                usuario=request.user,
                accion="Modificar Reserva",
                registro_id=reserva.id,
                tabla_afectada="reservas_reserva",
                estado_nuevo=f"ID: {reserva.id}, Huesped: {reserva.huesped.nombres} {reserva.huesped.apellidos}, Hab: {reserva.habitacion.numero}, Total: S/. {reserva.precio_total}"
            )

            messages.success(request, f'Reserva #{reserva.id} modificada correctamente.')
            return redirect('reserva_detalle', reserva_id=reserva.id)
        except Exception as e:
            messages.error(request, f'Error al modificar la reserva: {str(e)}')

    selected_habitacion_id = reserva.habitacion.id if reserva.habitacion else ''
    selected_huesped = reserva.huesped

    # Mostrar solo disponibles, pero incluir la habitación actual de la reserva si existe
    habitaciones_qs = Habitacion.objects.filter(estado=Habitacion.DISPONIBLE)
    if reserva.habitacion:
        habitaciones_qs = habitaciones_qs | Habitacion.objects.filter(id=reserva.habitacion.id)
    habitaciones_qs = habitaciones_qs.select_related('tipo').order_by('piso', 'numero')

    return render(request, 'reservas/editar.html', {
        'reserva': reserva,
        'huespedes': Huesped.objects.all().order_by('nombres', 'apellidos'),
        'habitaciones': habitaciones_qs,
        'selected_habitacion_id': selected_habitacion_id,
        'selected_huesped': selected_huesped,
        'hora_actual': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
    })


@login_required
def reserva_cancelar(request, reserva_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if reserva.estado in ['CHECKIN', 'CHECKOUT', 'CANCELADA']:
        messages.error(request, 'No se puede cancelar una reserva en estado check-in, check-out o cancelada.')
        return redirect('reserva_detalle', reserva_id=reserva.id)

    if request.method == 'POST':
        motivo = request.POST.get('motivo_cancelacion', '').strip()
        if not motivo:
            messages.error(request, 'Debes ingresar un motivo de cancelación.')
            return redirect('reserva_detalle', reserva_id=reserva.id)

        pagos_anticipados = Pago.objects.filter(reserva=reserva, folio__isnull=True)
        total_reembolsado = Decimal('0.00')
        for pago in pagos_anticipados:
            from estancias.models import Reembolso
            Reembolso.objects.create(
                pago=pago,
                monto=pago.monto,
                motivo=f"Cancelación de reserva #{reserva.id}. {motivo}",
                estado=Reembolso.APROBADO,
                solicitado_por=request.user,
                aprobado_por=request.user,
                fecha_resolucion=timezone.now(),
                observacion="Reembolso automático por cancelación de reserva"
            )
            total_reembolsado += pago.monto

        if total_reembolsado > 0:
            reserva.estado = Reserva.REEMBOLSADO
            reserva.motivo_cancelacion = f"{motivo} (Reembolsado: S/. {total_reembolsado})"
        else:
            reserva.estado = Reserva.CANCELADA
            reserva.motivo_cancelacion = motivo
        reserva.save()

        if reserva.habitacion:
            reserva.habitacion.estado = Habitacion.DISPONIBLE
            reserva.habitacion.save()

        obs_extra = f" Reembolsado: S/. {total_reembolsado}" if total_reembolsado > 0 else ""
        registrar_auditoria(
            usuario=request.user,
            accion="Cancelar Reserva",
            registro_id=reserva.id,
            tabla_afectada="reservas_reserva",
            estado_nuevo=f"Estado: CANCELADA, Motivo: {motivo}{obs_extra}"
        )

        if total_reembolsado > 0:
            messages.success(request, f'Reserva #{reserva.id} cancelada. Se reembolsaron S/. {total_reembolsado} automáticamente.')
        else:
            messages.success(request, f'Reserva #{reserva.id} cancelada correctamente.')
        return redirect('reservas_lista')

    return redirect('reserva_detalle', reserva_id=reserva.id)


@login_required
def registrar_pago_anticipo(request, reserva_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if request.method == 'POST':
        monto = request.POST.get('monto')
        metodo_pago = request.POST.get('metodo_pago', Pago.EFECTIVO)
        transaccion_id = request.POST.get('transaccion_id') or None

        if monto:
            try:
                monto_decimal = Decimal(monto)
                if monto_decimal <= 0:
                    messages.error(request, 'El monto debe ser mayor a cero.')
                elif monto_decimal > reserva.saldo_pendiente:
                    messages.error(request, f'No se puede pagar más del saldo pendiente (S/. {reserva.saldo_pendiente:.2f}).')
                elif metodo_pago != Pago.EFECTIVO and not transaccion_id:
                    messages.error(request, 'Debes ingresar el ID de transacción para pagos electrónicos/bancarios.')
                else:
                    from caja.services import obtener_caja_abierta, registrar_movimiento_pago
                    caja = obtener_caja_abierta(request.user)
                    if not caja:
                        messages.error(request, 'No tienes una caja abierta. Es obligatorio aperturar tu caja antes de registrar un pago.')
                        return redirect('reserva_detalle', reserva_id=reserva_id)

                    with transaction.atomic():
                        pago = Pago.objects.create(
                            reserva=reserva,
                            monto=monto_decimal,
                            metodo_pago=metodo_pago,
                            transaccion_id=transaccion_id
                        )
                        registrar_movimiento_pago(pago, request.user)
                    
                    registrar_auditoria(
                        usuario=request.user,
                        accion="Registrar Pago Anticipado",
                        registro_id=pago.id,
                        tabla_afectada="estancias_pago",
                        estado_nuevo=f"ID: {pago.id}, Reserva: {reserva.id}, Monto: S/. {monto_decimal}, Metodo: {metodo_pago}"
                    )
                    
                    messages.success(request, 'Pago anticipado registrado correctamente.')
            except Exception as e:
                messages.error(request, f'Error al registrar pago: {str(e)}')
        else:
            messages.error(request, 'Monto inválido para el pago.')
            
    return redirect('reserva_detalle', reserva_id=reserva_id)
