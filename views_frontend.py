# Controladores de vistas web encargados de renderizar HTML
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models import Q
from django.core.exceptions import ValidationError
from datetime import date, datetime, timedelta
from decimal import Decimal
from hotel.models import Habitacion, Hotel, TipoHabitacion
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia, CargoEstancia, Folio, Pago
import requests
from config import roles


# ── Helpers de Rol ─────────────────────────────────────────────────────────────
def _es_admin(user):
    return roles.es_admin(user)

def _es_recepcionista(user):
    return roles.es_recepcionista(user)

def _es_housekeeping(user):
    return roles.es_housekeeping(user)

def _solo_housekeeping(user):
    """True si el usuario es SOLO housekeeping (sin admin ni recepcionista)."""
    return roles.solo_housekeeping(user)

def _acceso_denegado(request, msg='No tienes permisos para acceder a esta sección.'):
    return render(request, '403.html', {'mensaje_error': msg}, status=403)


def parse_room_gallery(raw_urls, main_url=''):
    urls = []
    for raw_url in (main_url, *raw_urls.splitlines()):
        url = raw_url.strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def parse_datetime_local(value):
    if not value:
        return None
    parsed = datetime.strptime(value, '%Y-%m-%dT%H:%M')
    return timezone.make_aware(parsed)


def parse_date_local(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f'Fecha inválida: {value}')


def calcular_cargo_salida_tardia(estancia):
    from estancias.services import detectar_late_checkout
    hotel = estancia.habitacion.hotel
    now_local = timezone.localtime(timezone.now())
    es_late, late_monto, minutos_tarde = detectar_late_checkout(estancia, hotel, now_local)
    return late_monto, minutos_tarde


def login_view(request):
    if request.user.is_authenticated:
        if _solo_housekeeping(request.user):
            return redirect('housekeeping')
        return redirect('dashboard')
    if request.method == 'POST':
        user = authenticate(request, username=request.POST['username'], password=request.POST['password'])
        if user:
            login(request, user)
            if _solo_housekeeping(user):
                return redirect('housekeeping')
            return redirect('dashboard')
        messages.error(request, 'Usuario o contraseña incorrectos.')
    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    if _solo_housekeeping(request.user):
        return redirect('housekeeping')

    habitaciones = Habitacion.objects.select_related('tipo', 'hotel').all().order_by('piso', 'numero')
    hoy = timezone.now().date()
    ahora = timezone.now()
    
    total = habitaciones.count()
    ocupadas = habitaciones.filter(estado='OCUPADA').count()
    stats = {
        'disponibles': habitaciones.filter(estado='DISPONIBLE').count(),
        'ocupadas': ocupadas,
        'reservas_hoy': 0, # Calculado más abajo
        'tasa_ocupacion': round(ocupadas / total * 100) if total else 0,
    }
    
    # Lógica de estados visuales para el plano
    from datetime import datetime, time
    checkin_time = timezone.make_aware(datetime.combine(hoy, time(14, 0)))
    reservas_hoy = Reserva.objects.filter(
        fecha_entrada=hoy, estado__in=['PENDIENTE', 'CONFIRMADA']
    ).select_related('habitacion')
    reservas_dict = {r.habitacion_id: r for r in reservas_hoy if r.habitacion_id}
    
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

    stats['reservas_hoy'] = sum(1 for hab in habitaciones if getattr(hab, 'estado_visual', '') in ['RESERVADA', 'RETRASO'])

    llegadas_hoy = Reserva.objects.filter(
        fecha_entrada=hoy,
        estado__in=['PENDIENTE', 'CONFIRMADA']
    ).select_related('huesped', 'habitacion')[:15]

    en_casa = Estancia.objects.filter(
        estado='ACTIVA'
    ).select_related('reserva__huesped', 'habitacion')[:15]

    salidas_hoy = Estancia.objects.filter(
        estado='ACTIVA',
        reserva__fecha_salida=hoy
    ).select_related('reserva__huesped', 'habitacion')[:15]

    return render(request, 'dashboard.html', {
        'habitaciones': habitaciones,
        'stats': stats,
        'llegadas_hoy': llegadas_hoy,
        'en_casa': en_casa,
        'salidas_hoy': salidas_hoy,
    })


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
                observaciones=request.POST.get('observaciones', ''),
            )
            reserva.precio_total = reserva.calcular_precio()
            reserva.save()

            # Registrar auditoria
            from reportes.models import registrar_auditoria
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

    return render(request, 'reservas/nueva.html', {
        'huespedes': Huesped.objects.all().order_by('nombres', 'apellidos'),
        'habitaciones': Habitacion.objects.exclude(estado='MANTENIMIENTO').select_related('tipo').order_by('piso', 'numero'),
        'selected_habitacion_id': selected_habitacion_id,
        'selected_huesped': selected_huesped,
        'hora_actual': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
    })


from django.http import JsonResponse

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
                target_entrada = timezone.make_aware(datetime.combine(fecha_entrada, time(15, 0)))
                target_salida = timezone.make_aware(datetime.combine(fecha_salida, time(12, 0)))
        elif modalidad == 'HORA' and hora_entrada_str:
            fecha_hora_entrada = parse_datetime_local(hora_entrada_str)
            if fecha_hora_entrada:
                target_entrada = fecha_hora_entrada
                target_salida = fecha_hora_entrada + timedelta(hours=duracion)
    except Exception:
        pass

    if target_entrada and target_salida:
        # Check overlaps on exact datetime windows:
        # A reservation overlaps if (start1 < end2) AND (end1 > start2)
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
def reserva_checkin(request, reserva_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if reserva.estado not in ['PENDIENTE', 'CONFIRMADA']:
        messages.error(request, 'Esta reserva no puede hacer check-in.')
        return redirect('reservas_lista')

    import estancias.services as estancia_services

    if request.method == 'POST':
        hab_id = request.POST.get('habitacion')
        exonerar_early = request.POST.get('exonerar_early') in ['true', 'on', 'True']
        motivo_early = request.POST.get('motivo_exoneracion_early')

        try:
            estancia = estancia_services.procesar_checkin(
                reserva_id=reserva.id,
                habitacion_id=hab_id,
                usuario=request.user,
                exonerar_early=exonerar_early,
                motivo_exoneracion_early=motivo_early
            )
            messages.success(request, f'Check-in realizado. Estancia #{estancia.id} creada.')
            return redirect('folio', estancia_id=estancia.id)
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, 'message') else str(e))
            return redirect('reserva_checkin', reserva_id=reserva.id)

    habitaciones_disponibles = Habitacion.objects.filter(
        tipo=reserva.habitacion.tipo if reserva.habitacion else None, 
        estado='DISPONIBLE'
    )
    if reserva.habitacion and reserva.habitacion not in habitaciones_disponibles:
        habitaciones_disponibles = list(habitaciones_disponibles) + [reserva.habitacion]

    # Detectar Early Check-In para avisar al recepcionista
    es_early = False
    early_monto = Decimal('0.00')
    try:
        now_local = timezone.localtime(timezone.now())
        es_early, early_monto = estancia_services.detectar_early_checkin(reserva, reserva.hotel, now_local)
    except Exception:
        pass

    return render(request, 'reservas/checkin.html', {
        'reserva': reserva,
        'habitaciones': habitaciones_disponibles,
        'es_early': es_early,
        'early_monto': early_monto,
    })


@login_required
def folio_view(request, estancia_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    estancia = get_object_or_404(Estancia, id=estancia_id)
    folio, _ = Folio.objects.get_or_create(estancia=estancia)

    # Auto-seed room charge for estancias that existed before the auto-charge logic.
    # If the folio has no cargos but there IS a precio_final, create the cargo now.
    if not estancia.cargos.exists() and estancia.precio_final and estancia.precio_final > 0:
        reserva = estancia.reserva
        if reserva.modalidad == 'HORA':
            horas = int(reserva.duracion_horas or 3)
            concepto = f'Alquiler por horas \u2013 Hab. {estancia.habitacion.numero} ({horas}h)'
        else:
            noches = (reserva.fecha_salida - reserva.fecha_entrada).days or 1
            concepto = f'Alquiler por {noches} noche{"s" if noches != 1 else ""} \u2013 Hab. {estancia.habitacion.numero}'
        CargoEstancia.objects.create(
            estancia=estancia,
            concepto=concepto,
            monto=estancia.precio_final,
            tipo='HABITACION',
        )

    folio.calcular_totales()
    cargo_tardanza, minutos_tarde = calcular_cargo_salida_tardia(estancia)
    return render(request, 'estancias/folio.html', {
        'estancia': estancia,
        'folio': folio,
        'cargo_tardanza': cargo_tardanza,
        'minutos_tarde': minutos_tarde,
    })


@login_required
def agregar_cargo(request, estancia_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    if request.method == 'POST':
        try:
            import estancias.services as estancia_services
            estancia_services.registrar_consumo(
                estancia_id=estancia_id,
                concepto=request.POST['concepto'],
                monto=Decimal(request.POST['monto']),
                tipo=request.POST.get('tipo', 'OTRO'),
                usuario=request.user
            )
            messages.success(request, 'Cargo agregado correctamente.')
        except Exception as e:
            messages.error(request, str(e))
    return redirect('folio', estancia_id=estancia_id)


@login_required
def registrar_pago(request, estancia_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    if request.method == 'POST':
        estancia = get_object_or_404(Estancia, id=estancia_id)
        folio, _ = Folio.objects.get_or_create(estancia=estancia)
        monto = request.POST.get('monto')
        metodo_pago = request.POST.get('metodo_pago', Pago.EFECTIVO)
        transaccion_id = request.POST.get('transaccion_id') or None

        if monto:
            try:
                import estancias.services as estancia_services
                monto_decimal = Decimal(monto)
                estancia_services.registrar_pago_folio(
                    folio_id=folio.id,
                    monto=monto_decimal,
                    metodo=metodo_pago,
                    transaccion_id=transaccion_id,
                    usuario=request.user
                )
                messages.success(request, 'Pago registrado correctamente.')
            except Exception as e:
                messages.error(request, str(e))
        else:
            messages.error(request, 'Monto inválido para el pago.')
    return redirect('folio', estancia_id=estancia_id)


@login_required
def checkout_view(request, estancia_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    estancia = get_object_or_404(Estancia, id=estancia_id)
    exonerar_late = request.POST.get('exonerar_late_checkout') in ['true', 'on', 'True'] or request.GET.get('exonerar_late_checkout') in ['true', 'on', 'True']
    motivo_late = request.POST.get('motivo_exoneracion_late') or request.GET.get('motivo_exoneracion_late')
    try:
        import estancias.services as estancia_services
        estancia_services.procesar_checkout(
            estancia_id=estancia_id,
            usuario=request.user,
            exonerar_late_checkout=exonerar_late,
            motivo_exoneracion_late=motivo_late
        )
        messages.success(request, 'Check-out realizado correctamente.')
        return redirect('folio_imprimir', estancia_id=estancia.id)
    except Exception as e:
        messages.error(request, str(e))
        return redirect('folio', estancia_id=estancia_id)


@login_required
def housekeeping_view(request):
    if not _es_housekeeping(request.user):
        return _acceso_denegado(request)
    piso = request.GET.get('piso', '')
    habitaciones = Habitacion.objects.filter(estado='LIMPIEZA').select_related('tipo').order_by('piso', 'numero')
    
    if piso:
        habitaciones = habitaciones.filter(piso=piso)
        
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
            
            # Registrar auditoría única
            from reportes.models import registrar_auditoria
            registrar_auditoria(
                usuario=request.user,
                accion="Housekeeping Estado Modificado",
                registro_id=hab.id,
                tabla_afectada="hotel_habitacion",
                estado_anterior=anterior,
                estado_nuevo=nuevo_estado,
                observacion=f"Cambio estado de Hab. {hab.numero} de {anterior} a {nuevo_estado}"
            )
            messages.success(request, f'Habitación {hab.numero} actualizada a {nuevo_estado}.')
    return redirect('housekeeping')


@login_required
def reportes_view(request):
    if not _es_admin(request.user):
        return _acceso_denegado(request, 'Solo los administradores pueden ver reportes.')
    
    import json
    from datetime import timedelta, datetime
    from django.utils import timezone
    from django.db import models
    from django.db.models.functions import TruncMonth
    from estancias.models import Estancia, CargoEstancia
    from reservas.models import Reserva
    from hotel.models import Habitacion
    
    hoy = timezone.now().date()
    periodo = request.GET.get('periodo', 'mes')
    
    # Rango de fechas actual
    if periodo == 'hoy':
        start_date = hoy
        end_date = hoy
        dias = 1
        prev_start = start_date - timedelta(days=1)
        prev_end = prev_start
    elif periodo == 'semana':
        start_date = hoy - timedelta(days=hoy.weekday())
        end_date = start_date + timedelta(days=6)
        dias = 7
        prev_start = start_date - timedelta(days=7)
        prev_end = end_date - timedelta(days=7)
    elif periodo == 'anio':
        start_date = hoy.replace(month=1, day=1)
        end_date = hoy.replace(month=12, day=31)
        dias = 365
        prev_start = start_date.replace(year=start_date.year - 1)
        prev_end = end_date.replace(year=end_date.year - 1)
    else: # mes (default)
        start_date = hoy.replace(day=1)
        next_month = start_date.replace(day=28) + timedelta(days=4)
        end_date = next_month - timedelta(days=next_month.day)
        dias = (end_date - start_date).days + 1
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
    
    total_habitaciones = Habitacion.objects.count()
    habitaciones_disponibles_periodo = total_habitaciones * dias
    habitaciones_disponibles_prev = total_habitaciones * ((prev_end - prev_start).days + 1)
    
    # 1. KPIs del periodo actual
    estancias_qs = Estancia.objects.filter(fecha_checkin__date__gte=start_date, fecha_checkin__date__lte=end_date)
    estancias_activas_count = Estancia.objects.filter(estado='ACTIVA').count()
    hab_ocupadas_actual = estancias_qs.values('habitacion').distinct().count()
    
    ocupacion_actual = round((hab_ocupadas_actual / total_habitaciones * 100), 1) if total_habitaciones > 0 else 0
    
    cargos_hab = CargoEstancia.objects.filter(
        tipo='HABITACION', fecha__date__gte=start_date, fecha__date__lte=end_date
    ).aggregate(total=models.Sum('monto'))['total'] or 0.0
    
    revenue_total = CargoEstancia.objects.filter(
        fecha__date__gte=start_date, fecha__date__lte=end_date
    ).aggregate(total=models.Sum('monto'))['total'] or 0.0
    
    adr_actual = float(cargos_hab) / hab_ocupadas_actual if hab_ocupadas_actual > 0 else 0.0
    revpar_actual = float(cargos_hab) / habitaciones_disponibles_periodo if habitaciones_disponibles_periodo > 0 else 0.0
    
    # 2. KPIs del periodo anterior (para comparativa)
    estancias_prev_qs = Estancia.objects.filter(fecha_checkin__date__gte=prev_start, fecha_checkin__date__lte=prev_end)
    hab_ocupadas_prev = estancias_prev_qs.values('habitacion').distinct().count()
    ocupacion_prev = round((hab_ocupadas_prev / total_habitaciones * 100), 1) if total_habitaciones > 0 else 0
    
    cargos_hab_prev = CargoEstancia.objects.filter(
        tipo='HABITACION', fecha__date__gte=prev_start, fecha__date__lte=prev_end
    ).aggregate(total=models.Sum('monto'))['total'] or 0.0
    revenue_total_prev = CargoEstancia.objects.filter(
        fecha__date__gte=prev_start, fecha__date__lte=prev_end
    ).aggregate(total=models.Sum('monto'))['total'] or 0.0
    
    adr_prev = float(cargos_hab_prev) / hab_ocupadas_prev if hab_ocupadas_prev > 0 else 0.0
    revpar_prev = float(cargos_hab_prev) / habitaciones_disponibles_prev if habitaciones_disponibles_prev > 0 else 0.0
    
    def calc_var(actual, prev):
        if prev == 0: return 100 if actual > 0 else 0
        return round(((actual - prev) / prev) * 100, 1)
        
    variaciones = {
        'ocupacion': calc_var(ocupacion_actual, ocupacion_prev),
        'revenue': calc_var(float(revenue_total), float(revenue_total_prev)),
        'adr': calc_var(adr_actual, adr_prev),
        'revpar': calc_var(revpar_actual, revpar_prev)
    }

    # 3. Gráficos - Ocupación por tipo (activas)
    estancias_activas_qs = Estancia.objects.filter(estado='ACTIVA').select_related('habitacion__tipo')
    ocupacion_por_tipo = {}
    for e in estancias_activas_qs:
        tipo = e.habitacion.tipo.nombre
        ocupacion_por_tipo[tipo] = ocupacion_por_tipo.get(tipo, 0) + 1

    # 4. Gráficos - Ingresos mensuales (12 meses)
    doce_meses_atras = hoy.replace(day=1) - timedelta(days=365)
    ingresos_mensuales = CargoEstancia.objects.filter(fecha__date__gte=doce_meses_atras) \
        .annotate(mes=TruncMonth('fecha')) \
        .values('mes') \
        .annotate(total=models.Sum('monto')) \
        .order_by('mes')
    
    meses_labels = [i['mes'].strftime('%b %Y') for i in ingresos_mensuales]
    meses_data = [float(i['total']) for i in ingresos_mensuales]

    # 5. Gráficos - Ingresos por origen (periodo actual)
    ingresos_origen = Reserva.objects.filter(
        fecha_entrada__gte=start_date, fecha_entrada__lte=end_date, estado__in=['CHECKIN', 'CHECKOUT']
    ).values('origen').annotate(total=models.Sum('precio_total'))
    
    origen_labels = [i['origen'] for i in ingresos_origen]
    origen_data = [float(i['total']) for i in ingresos_origen]

    ultimas_estancias = Estancia.objects.all().select_related('reserva__huesped', 'habitacion__tipo').order_by('-fecha_checkin')[:8]
    reservas_pendientes = Reserva.objects.filter(estado__in=['PENDIENTE', 'CONFIRMADA'], fecha_entrada__gte=hoy).order_by('fecha_entrada')[:5]

    context = {
        'periodo': periodo,
        'start_date': start_date,
        'end_date': end_date,
        
        'ocupacion_actual': ocupacion_actual,
        'hab_ocupadas_actual': hab_ocupadas_actual,
        'estancias_activas': estancias_activas_count,
        'revenue_total': revenue_total,
        'adr_actual': adr_actual,
        'revpar_actual': revpar_actual,
        'total_habitaciones': total_habitaciones,
        'variaciones': variaciones,
        
        'ultimas_estancias': ultimas_estancias,
        'reservas_pendientes': reservas_pendientes,
        
        'tipos_labels_json': json.dumps(list(ocupacion_por_tipo.keys())),
        'tipos_data_json': json.dumps(list(ocupacion_por_tipo.values())),
        'meses_labels_json': json.dumps(meses_labels),
        'meses_data_json': json.dumps(meses_data),
        'origen_labels_json': json.dumps(origen_labels),
        'origen_data_json': json.dumps(origen_data),
    }
    
    return render(request, 'reportes/dashboard.html', context)


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
            
            target_entrada = timezone.make_aware(datetime.combine(fecha_entrada, time(15, 0)))
            target_salida = timezone.make_aware(datetime.combine(fecha_salida, time(12, 0)))
            
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
def huespedes_lista(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    query = request.GET.get('q', '')
    huespedes = Huesped.objects.all().order_by('-created_at')
    if query:
        huespedes = huespedes.filter(
            Q(nombres__icontains=query) |
            Q(apellidos__icontains=query) |
            Q(num_doc__icontains=query)
        )
    return render(request, 'huespedes/lista.html', {'huespedes': huespedes, 'query': query})


@login_required
def huesped_nuevo(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    next_url = request.GET.get('next') or request.POST.get('next') or ''
    if request.method == 'POST':
        try:
            huesped = Huesped.objects.create(
                tipo_doc=request.POST['tipo_doc'],
                num_doc=request.POST['num_doc'],
                nombres=request.POST['nombres'],
                apellidos=request.POST['apellidos'],
                email=request.POST.get('email') or None,
                telefono=request.POST.get('telefono') or None,
                nacionalidad=request.POST.get('nacionalidad', 'Peruana'),
            )
            messages.success(request, 'Huésped registrado correctamente.')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                separator = '&' if '?' in next_url else '?'
                return redirect(f'{next_url}{separator}huesped={huesped.id}')
            return redirect('huespedes_lista')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    return render(request, 'huespedes/form.html', {
        'next': next_url,
        'initial_query': request.GET.get('q', ''),
    })


@login_required
def huesped_editar(request, huesped_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    huesped = get_object_or_404(Huesped, id=huesped_id)
    if request.method == 'POST':
        try:
            huesped.tipo_doc = request.POST['tipo_doc']
            huesped.num_doc = request.POST['num_doc']
            huesped.nombres = request.POST['nombres']
            huesped.apellidos = request.POST['apellidos']
            huesped.email = request.POST.get('email') or None
            huesped.telefono = request.POST.get('telefono') or None
            huesped.nacionalidad = request.POST.get('nacionalidad', 'Peruana')
            huesped.save()
            messages.success(request, 'Huésped actualizado correctamente.')
            return redirect('huespedes_lista')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    return render(request, 'huespedes/form.html', {
        'huesped': huesped,
        'initial_query': '',
        'next': '',
    })


@login_required
def exportar_huespedes_excel(request):
    if not _es_admin(request.user):
        return _acceso_denegado(request, 'Solo los administradores pueden exportar datos.')
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse
    from huespedes.models import Huesped
    from django.db.models import Count, Sum
    
    huespedes = Huesped.objects.annotate(
        total_estancias=Count('reservas__estancia', distinct=True),
        total_pagado=Sum('reservas__estancia__folio__pagos__monto')
    ).order_by('id')
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Huéspedes"
    
    headers = ["#", "Nombre completo", "DNI", "Teléfono", "Email", "Fecha de registro", "Total estancias", "Total pagado"]
    ws.append(headers)
    
    header_font = Font(color="FFFFFF", bold=True)
    header_fill = PatternFill(start_color="1E2433", end_color="1E2433", fill_type="solid")
    
    for col_num, cell in enumerate(ws[1], 1):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    for h in huespedes:
        fecha_reg = h.created_at.strftime('%Y-%m-%d') if hasattr(h, 'created_at') and h.created_at else "N/A"
        total_p = h.total_pagado or 0.0
        ws.append([
            h.id,
            f"{h.nombres} {h.apellidos}",
            h.num_doc,
            h.telefono or "-",
            h.email or "-",
            fecha_reg,
            h.total_estancias,
            float(total_p)
        ])
        
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws.column_dimensions[col_letter].width = (max_length + 2)
        
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="huespedes_hotelsystem.xlsx"'
    wb.save(response)
    return response


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
    
    # Reservas de hoy para calculos
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
def estancias_lista(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    from django.utils import timezone
    from django.db.models import Q
    
    estado = request.GET.get('estado', 'ACTIVA')
    q = request.GET.get('q', '').strip()
    
    estancias = Estancia.objects.select_related(
        'reserva__huesped', 'habitacion__tipo'
    ).order_by('-fecha_checkin')
    
    if estado != 'TODAS':
        estancias = estancias.filter(estado=estado)
        
    if q:
        estancias = estancias.filter(
            Q(reserva__huesped__nombres__icontains=q) | 
            Q(reserva__huesped__apellidos__icontains=q) |
            Q(reserva__huesped__num_doc__icontains=q)
        )

    for e in estancias:
        if e.fecha_checkout:
            e.dias_estancia = (e.fecha_checkout.date() - e.fecha_checkin.date()).days
        else:
            e.dias_estancia = (timezone.now().date() - e.fecha_checkin.date()).days or 1

    return render(request, 'estancias/lista.html', {'estancias': estancias})


@login_required
def usuarios_lista(request):
    from django.contrib.auth.models import User, Group
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos para acceder a la gestión de usuarios.')
        return redirect('dashboard')
    
    query = request.GET.get('q', '')
    usuarios = User.objects.prefetch_related('groups').all().order_by('-date_joined')
    if query:
        usuarios = usuarios.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )
    
    return render(request, 'usuarios/lista.html', {'usuarios': usuarios, 'query': query})

def error_403(request, exception=None):
    return render(request, '403.html', {'mensaje_error': 'La página denegó el acceso por falta de permisos.'}, status=403)

def error_404(request, exception=None):
    return render(request, '404.html', status=404)

@login_required
def reserva_imprimir_ficha(request, reserva_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    reserva = get_object_or_404(Reserva.objects.select_related('huesped', 'habitacion__tipo', 'hotel'), id=reserva_id)
    return render(request, 'reservas/imprimir_ficha.html', {'reserva': reserva})

@login_required
def folio_imprimir(request, estancia_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    estancia = get_object_or_404(Estancia, id=estancia_id)
    folio, _ = Folio.objects.get_or_create(estancia=estancia)
    folio.calcular_totales()
    return render(request, 'estancias/imprimir_folio.html', {'estancia': estancia, 'folio': folio})


@login_required
def usuario_editar(request, user_id):
    from django.contrib.auth.models import User, Group
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos para editar usuarios.')
        return redirect('dashboard')
        
    usuario_edit = get_object_or_404(User, id=user_id)
    grupos_disponibles = Group.objects.all()
    
    if request.method == 'POST':
        try:
            usuario_edit.first_name = request.POST.get('nombres', usuario_edit.first_name)
            usuario_edit.last_name = request.POST.get('apellidos', usuario_edit.last_name)
            usuario_edit.email = request.POST.get('email', usuario_edit.email)
            usuario_edit.is_active = request.POST.get('is_active') == 'on'
            
            # Gestión de roles
            rol_id = request.POST.get('rol')
            usuario_edit.groups.clear()
            if rol_id:
                grupo = Group.objects.get(id=rol_id)
                usuario_edit.groups.add(grupo)
                
            usuario_edit.save()
            messages.success(request, f'Usuario {usuario_edit.username} actualizado correctamente.')
            return redirect('usuarios_lista')
        except Exception as e:
            messages.error(request, f'Error al actualizar: {str(e)}')
            
    # Obtener el rol actual
    rol_actual = usuario_edit.groups.first()
    
    return render(request, 'usuarios/form.html', {
        'usuario_edit': usuario_edit,
        'grupos_disponibles': grupos_disponibles,
        'rol_actual': rol_actual,
    })


@login_required
def usuario_nuevo(request):
    from django.contrib.auth.models import User, Group
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos para crear usuarios.')
        return redirect('dashboard')
        
    grupos_disponibles = Group.objects.all()
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username')
            password = request.POST.get('password')
            
            if User.objects.filter(username=username).exists():
                raise Exception('Ese nombre de usuario ya está en uso.')
                
            nuevo_user = User.objects.create_user(
                username=username,
                password=password,
                first_name=request.POST.get('nombres', ''),
                last_name=request.POST.get('apellidos', ''),
                email=request.POST.get('email', ''),
            )
            nuevo_user.is_active = request.POST.get('is_active') == 'on'
            
            rol_id = request.POST.get('rol')
            if rol_id:
                grupo = Group.objects.get(id=rol_id)
                nuevo_user.groups.add(grupo)
                
            nuevo_user.save()
            messages.success(request, f'Usuario {nuevo_user.username} creado correctamente.')
            return redirect('usuarios_lista')
        except Exception as e:
            messages.error(request, f'Error al crear: {str(e)}')
            
    return render(request, 'usuarios/nuevo.html', {
        'grupos_disponibles': grupos_disponibles,
    })


@login_required
def usuario_eliminar(request, user_id):
    from django.contrib.auth.models import User
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos para eliminar usuarios.')
        return redirect('dashboard')
        
    usuario = get_object_or_404(User, id=user_id)
    if usuario == request.user:
        messages.error(request, 'No puedes eliminar tu propia cuenta.')
        return redirect('usuarios_lista')
        
    if request.method == 'POST':
        try:
            username = usuario.username
            usuario.delete()
            messages.success(request, f'Usuario {username} eliminado.')
        except Exception as e:
            messages.error(request, f'Error al eliminar: {str(e)}')
            
    return redirect('usuarios_lista')

@login_required
def api_consulta_dni(request):
    from django.http import JsonResponse
    numero = request.GET.get('numero')
    if not numero or len(numero) != 8:
        return JsonResponse({'error': 'DNI inválido'}, status=400)
    
    try:
        import urllib.request, json
        req = urllib.request.Request(f'https://api.apis.net.pe/v1/dni?numero={numero}', headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode('utf-8'))
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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

            # Validar y salvar
            reserva.precio_total = reserva.calcular_precio()
            reserva.save()

            # Registrar auditoria
            from reportes.models import registrar_auditoria
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

    return render(request, 'reservas/editar.html', {
        'reserva': reserva,
        'huespedes': Huesped.objects.all().order_by('nombres', 'apellidos'),
        'habitaciones': Habitacion.objects.exclude(estado='MANTENIMIENTO').select_related('tipo').order_by('piso', 'numero'),
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

        # Reembolsar anticipos automáticamente si existen
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

        # Registrar auditoria
        from reportes.models import registrar_auditoria
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
                    pago = Pago.objects.create(
                        reserva=reserva,
                        monto=monto_decimal,
                        metodo_pago=metodo_pago,
                        transaccion_id=transaccion_id
                    )
                    
                    # Registrar auditoria
                    from reportes.models import registrar_auditoria
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


@login_required
def solicitar_reembolso(request, pago_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    pago = get_object_or_404(Pago, id=pago_id)
    
    redirect_url = redirect('dashboard')
    if pago.folio:
        redirect_url = redirect('folio', estancia_id=pago.folio.estancia.id)
    elif pago.reserva:
        redirect_url = redirect('reserva_detalle', reserva_id=pago.reserva.id)

    if request.method == 'POST':
        monto_str = request.POST.get('monto')
        motivo = request.POST.get('motivo', '').strip()
        
        if not monto_str or not motivo:
            messages.error(request, 'Debes ingresar monto y motivo del reembolso.')
            return redirect_url

        try:
            monto_decimal = Decimal(monto_str)
            if monto_decimal <= 0:
                messages.error(request, 'El monto del reembolso debe ser mayor a cero.')
                return redirect_url

            from estancias.models import Reembolso
            reembolsos_previos = Reembolso.objects.filter(
                pago=pago,
                estado__in=[Reembolso.SOLICITADO, Reembolso.APROBADO]
            )
            total_reembolsado = sum(r.monto for r in reembolsos_previos)
            monto_disponible = pago.monto - total_reembolsado
            
            if monto_disponible <= 0:
                messages.error(request, 'Este pago ya fue completamente reembolsado.')
                return redirect_url
                
            if monto_decimal > monto_disponible:
                messages.error(request, f'Monto disponible para reembolsar: S/. {monto_disponible:.2f}')
                return redirect_url
                
            reembolso = Reembolso.objects.create(
                pago=pago,
                monto=monto_decimal,
                motivo=motivo,
                estado=Reembolso.SOLICITADO,
                solicitado_por=request.user
            )
            
            # Registrar auditoria
            from reportes.models import registrar_auditoria
            registrar_auditoria(
                usuario=request.user,
                accion="Solicitar Reembolso",
                registro_id=reembolso.id,
                tabla_afectada="estancias_reembolso",
                estado_nuevo=f"ID: {reembolso.id}, Pago: {pago.id}, Monto: S/. {monto_decimal}"
            )
            
            messages.success(request, 'Solicitud de reembolso registrada correctamente.')
        except Exception as e:
            messages.error(request, f'Error al registrar la solicitud: {str(e)}')
            
    return redirect_url


@login_required
def cambiar_habitacion(request, estancia_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    estancia = get_object_or_404(Estancia, id=estancia_id)
    
    if request.method == 'POST':
        nueva_hab_id = request.POST.get('nueva_habitacion_id')
        motivo = request.POST.get('motivo', '').strip()
        
        if not nueva_hab_id or not motivo:
            messages.error(request, 'Nueva habitación y motivo son requeridos.')
            return redirect('folio', estancia_id=estancia_id)
        
        try:
            import estancias.services as estancia_services
            estancia_services.cambiar_habitacion_activo(
                estancia_id=estancia_id,
                nueva_habitacion_id=nueva_hab_id,
                motivo=motivo,
                usuario=request.user
            )
            messages.success(request, 'Cambio de habitación completado correctamente.')
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, 'message') else str(e))
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    
    return redirect('folio', estancia_id=estancia_id)


@login_required
def aprobar_reembolso(request, reembolso_id):
    if not _es_admin(request.user):
        return _acceso_denegado(request, 'Solo los administradores pueden resolver reembolsos.')
        
    from estancias.models import Reembolso
    reembolso = get_object_or_404(Reembolso, id=reembolso_id)
    
    redirect_url = redirect('dashboard')
    if reembolso.pago.folio:
        redirect_url = redirect('folio', estancia_id=reembolso.pago.folio.estancia.id)
    elif reembolso.pago.reserva:
        redirect_url = redirect('reserva_detalle', reserva_id=reembolso.pago.reserva.id)

    if request.method == 'POST':
        accion = request.POST.get('accion')
        observacion = request.POST.get('observacion', '').strip()
        
        if reembolso.estado != Reembolso.SOLICITADO:
            messages.error(request, 'Este reembolso ya ha sido resuelto.')
            return redirect_url

        if accion in ['APROBAR', 'aprobar']:
            reembolso.estado = Reembolso.APROBADO
            reembolso.aprobado_por = request.user
            reembolso.fecha_resolucion = timezone.now()
            reembolso.observacion = observacion
            reembolso.save()

            pago = reembolso.pago
            estancia = pago.folio.estancia if pago.folio else None
            reserva = pago.reserva if pago.reserva else (estancia.reserva if estancia else None)
            
            if estancia and estancia.estado == Estancia.ACTIVA:
                folio = estancia.folio
                folio.calcular_totales()
                
                # Cerrar folio y perdonar saldo pendiente
                folio.estado = Folio.CERRADO
                folio.save()
                
                estancia.habitacion.estado = Habitacion.LIMPIEZA
                estancia.habitacion.save()
                estancia.fecha_checkout = timezone.now()
                estancia.estado = Estancia.FINALIZADA
                estancia.save()
                
                if reserva:
                    reserva.estado = Reserva.REEMBOLSADO
                    reserva.motivo_cancelacion = f"Reembolso #{reembolso.id} aprobado. {observacion}"
                    reserva.save()
                
                messages.success(request, f'Reembolso aprobado. Estancia finalizada, habitación en limpieza y reserva reembolsada.')
            elif reserva and reserva.estado in [Reserva.PENDIENTE, Reserva.CONFIRMADA]:
                if reserva.habitacion:
                    reserva.habitacion.estado = Habitacion.DISPONIBLE
                    reserva.habitacion.save()
                reserva.estado = Reserva.REEMBOLSADO
                reserva.motivo_cancelacion = f"Reembolso anticipo #{reembolso.id} aprobado. {observacion}"
                reserva.save()
                messages.success(request, f'Reembolso aprobado. Reserva reembolsada y habitación liberada.')
            else:
                messages.success(request, f'Reembolso #{reembolso.id} aprobado correctamente.')
        elif accion in ['RECHAZAR', 'rechazar']:
            reembolso.estado = Reembolso.RECHAZADO
        else:
            messages.error(request, 'Acción no válida.')
            return redirect_url
            
        reembolso.aprobado_por = request.user
        reembolso.fecha_resolucion = timezone.now()
        reembolso.observacion = observacion
        reembolso.save()
        
        # Registrar auditoria
        from reportes.models import registrar_auditoria
        registrar_auditoria(
            usuario=request.user,
            accion="Resolver Reembolso",
            registro_id=reembolso.id,
            tabla_afectada="estancias_reembolso",
            estado_nuevo=f"ID: {reembolso.id}, Estado: {reembolso.estado}, Observacion: {observacion}"
        )
        
        messages.success(request, f'Reembolso #{reembolso.id} resuelto: {reembolso.get_estado_display()}.')
        
    return redirect_url



