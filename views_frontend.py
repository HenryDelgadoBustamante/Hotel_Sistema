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
    reserva = estancia.reserva
    if not reserva.fecha_hora_salida:
        return 0, 0

    ahora = timezone.now()
    limite_cobro = reserva.fecha_hora_salida + timedelta(minutes=reserva.cargo_extra_desde_minutos)
    if ahora < limite_cobro:
        return 0, 0

    minutos_tarde = int((ahora - reserva.fecha_hora_salida).total_seconds() // 60)
    bloques = max(1, int(((minutos_tarde / 60) + 2.99) // 3))
    tarifa_bloque = reserva.habitacion.tipo.precio_base * Decimal('0.35')
    return round(tarifa_bloque * bloques, 2), minutos_tarde


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        user = authenticate(request, username=request.POST['username'], password=request.POST['password'])
        if user:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Usuario o contraseña incorrectos.')
    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    habitaciones = Habitacion.objects.select_related('tipo', 'hotel').all().order_by('piso', 'numero')
    hoy = timezone.now().date()
    total = habitaciones.count()
    ocupadas = habitaciones.filter(estado='OCUPADA').count()
    stats = {
        'disponibles': habitaciones.filter(estado='DISPONIBLE').count(),
        'ocupadas': ocupadas,
        'reservas_hoy': Reserva.objects.filter(fecha_entrada=hoy).count(),
        'tasa_ocupacion': round(ocupadas / total * 100) if total else 0,
    }
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
    estado = request.GET.get('estado')
    reservas = Reserva.objects.select_related('huesped', 'habitacion').all().order_by('-created_at')
    if estado:
        reservas = reservas.filter(estado=estado)
    return render(request, 'reservas/lista.html', {'reservas': reservas})


@login_required
def reserva_detalle(request, reserva_id):
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
            )
            reserva.precio_total = reserva.calcular_precio()
            reserva.save()
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



@login_required
def reserva_checkin(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if reserva.estado not in ['PENDIENTE', 'CONFIRMADA']:
        messages.error(request, 'Esta reserva no puede hacer check-in.')
        return redirect('reservas_lista')

    if request.method == 'POST':
        ahora = timezone.now()
        es_reserva_futura = reserva.fecha_entrada and reserva.fecha_entrada > timezone.localdate()
        if es_reserva_futura and reserva.fecha_hora_entrada and ahora < reserva.fecha_hora_entrada - timedelta(minutes=30):
            messages.error(request, 'Esta reserva todavÃ­a no estÃ¡ dentro de la ventana de check-in.')
            return redirect('reserva_checkin', reserva_id=reserva.id)

        hab_id = request.POST.get('habitacion')
        if hab_id:
            reserva.habitacion = Habitacion.objects.get(id=hab_id)

        habitacion = reserva.habitacion
        habitacion.estado = 'OCUPADA'
        habitacion.save()

        reserva.estado = 'CHECKIN'
        reserva.save()
        estancia = Estancia.objects.create(
            reserva=reserva, habitacion=habitacion, precio_final=reserva.precio_total
        )
        folio = Folio.objects.create(estancia=estancia)

        # Agregar automáticamente el cargo base de habitación al folio
        if reserva.precio_total and reserva.precio_total > 0:
            if reserva.modalidad == 'HORA':
                horas = int(reserva.duracion_horas or 3)
                concepto = f'Alquiler por horas – Hab. {habitacion.numero} ({horas}h)'
            else:
                from datetime import date as date_cls
                noches = (reserva.fecha_salida - reserva.fecha_entrada).days or 1
                concepto = f'Alquiler por {noches} noche{"s" if noches != 1 else ""} – Hab. {habitacion.numero}'
            CargoEstancia.objects.create(
                estancia=estancia,
                concepto=concepto,
                monto=reserva.precio_total,
                tipo='HABITACION',
            )
            folio.calcular_totales()
        messages.success(request, f'Check-in realizado. Estancia #{estancia.id} creada.')
        return redirect('folio', estancia_id=estancia.id)

    habitaciones_disponibles = Habitacion.objects.filter(
        tipo=reserva.habitacion.tipo if reserva.habitacion else None, 
        estado='DISPONIBLE'
    )
    if reserva.habitacion and reserva.habitacion not in habitaciones_disponibles:
        habitaciones_disponibles = list(habitaciones_disponibles) + [reserva.habitacion]

    return render(request, 'reservas/checkin.html', {
        'reserva': reserva,
        'habitaciones': habitaciones_disponibles
    })


@login_required
def folio_view(request, estancia_id):
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
    if request.method == 'POST':
        estancia = get_object_or_404(Estancia, id=estancia_id)
        CargoEstancia.objects.create(
            estancia=estancia,
            concepto=request.POST['concepto'],
            monto=request.POST['monto'],
            tipo=request.POST.get('tipo', 'OTRO'),
        )
        folio, _ = Folio.objects.get_or_create(estancia=estancia)
        folio.calcular_totales()
        messages.success(request, 'Cargo agregado correctamente.')
    return redirect('folio', estancia_id=estancia_id)


@login_required
def registrar_pago(request, estancia_id):
    if request.method == 'POST':
        estancia = get_object_or_404(Estancia, id=estancia_id)
        folio, _ = Folio.objects.get_or_create(estancia=estancia)
        monto = request.POST.get('monto')
        metodo_pago = request.POST.get('metodo_pago', Pago.EFECTIVO)
        transaccion_id = request.POST.get('transaccion_id') or None

        if monto:
            Pago.objects.create(
                folio=folio,
                monto=monto,
                metodo_pago=metodo_pago,
                transaccion_id=transaccion_id
            )
            messages.success(request, 'Pago registrado correctamente.')
        else:
            messages.error(request, 'Monto inválido para el pago.')
    return redirect('folio', estancia_id=estancia_id)


@login_required
def checkout_view(request, estancia_id):
    estancia = get_object_or_404(Estancia, id=estancia_id)
    try:
        cargo_tardanza, minutos_tarde = calcular_cargo_salida_tardia(estancia)
        cargo_ya_registrado = estancia.cargos.filter(concepto__startswith='Salida tardia').exists()
        if cargo_tardanza and not cargo_ya_registrado:
            CargoEstancia.objects.create(
                estancia=estancia,
                concepto=f'Salida tardia ({minutos_tarde} min)',
                monto=cargo_tardanza,
                tipo='HABITACION',
            )
            folio, _ = Folio.objects.get_or_create(estancia=estancia)
            folio.calcular_totales()
            messages.warning(request, 'Se agrego un cargo por salida tardia. Revisa y cierra el folio antes del check-out.')
            return redirect('folio', estancia_id=estancia_id)
        estancia.hacer_checkout()
        messages.success(request, 'Check-out realizado correctamente.')
        return redirect('reservas_lista')
    except Exception as e:
        messages.error(request, str(e))
        return redirect('folio', estancia_id=estancia_id)


@login_required
def housekeeping_view(request):
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
    if request.method == 'POST':
        hab = get_object_or_404(Habitacion, id=hab_id)
        nuevo_estado = request.POST.get('estado')
        if nuevo_estado in ['DISPONIBLE', 'LIMPIEZA', 'MANTENIMIENTO']:
            hab.estado = nuevo_estado
            hab.save()
            messages.success(request, f'Habitación {hab.numero} actualizada a {nuevo_estado}.')
    return redirect('housekeeping')


@login_required
def reportes_view(request):
    import json
    from django.utils import timezone
    from django.db import models
    from estancias.models import Estancia, CargoEstancia
    from reservas.models import Reserva
    from hotel.models import Habitacion
    
    hoy = timezone.now().date()
    
    total_habitaciones = Habitacion.objects.count()
    
    estancias_activas_qs = Estancia.objects.filter(estado='ACTIVA').select_related('reserva__huesped', 'habitacion__tipo')
    estancias_activas_count = estancias_activas_qs.count()
    
    # hab_ocupadas: count distinct de habitaciones con estancia ACTIVA
    hab_ocupadas = estancias_activas_qs.values('habitacion').distinct().count()
    
    ocupacion_hoy = round((hab_ocupadas / total_habitaciones * 100), 1) if total_habitaciones > 0 else 0
    ocupacion_semanal = round((ocupacion_hoy) * 0.85, 1) if total_habitaciones > 0 else 0
    
    reservas_hoy = Reserva.objects.filter(created_at__date=hoy).count()
    reservas_pendientes = Reserva.objects.filter(estado__in=['PENDIENTE', 'CONFIRMADA']).count()
    
    # revenue_activas: sum of cargos de estancias activas
    revenue_activas = CargoEstancia.objects.filter(estancia__estado='ACTIVA').aggregate(total=models.Sum('monto'))['total'] or 0.0
    
    # agrupaciones
    revenue_por_tipo = {}
    ocupacion_por_tipo = {}
    
    for e in estancias_activas_qs:
        tipo = e.habitacion.tipo.nombre
        monto_estancia = CargoEstancia.objects.filter(estancia=e).aggregate(total=models.Sum('monto'))['total'] or 0.0
        revenue_por_tipo[tipo] = revenue_por_tipo.get(tipo, 0.0) + float(monto_estancia)
        ocupacion_por_tipo[tipo] = ocupacion_por_tipo.get(tipo, 0) + 1
        
    ultimas_estancias = Estancia.objects.all().select_related('reserva__huesped', 'habitacion__tipo').order_by('-fecha_checkin')[:5]

    context = {
        'ocupacion_hoy': ocupacion_hoy,
        'ocupacion_semanal': ocupacion_semanal,
        'hab_ocupadas': hab_ocupadas,
        'total_habitaciones': total_habitaciones,
        'reservas_hoy': reservas_hoy,
        'estancias_activas': estancias_activas_count,
        'reservas_pendientes': reservas_pendientes,
        'revenue_activas': revenue_activas,
        'ocupacion_por_tipo': ocupacion_por_tipo,
        'revenue_por_tipo': revenue_por_tipo,
        'ultimas_estancias': ultimas_estancias,
        
        # Para el Chart.js (que requiere JSON válido)
        'tipos_labels_json': json.dumps(list(ocupacion_por_tipo.keys())),
        'tipos_data_json': json.dumps(list(ocupacion_por_tipo.values())),
    }
    
    return render(request, 'reportes/dashboard.html', context)


@login_required
def reservas_calendario(request):
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
def huespedes_lista(request):
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
                if ahora > checkin_time:
                    hab.estado_visual = 'RETRASO'
                elif (checkin_time - ahora).total_seconds() <= 3600 and (checkin_time - ahora).total_seconds() >= 0:
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
    from django.utils import timezone
    estancias = Estancia.objects.select_related(
        'reserva__huesped', 'habitacion__tipo'
    ).all().order_by('-fecha_checkin')

    for e in estancias:
        if e.fecha_checkout:
            e.dias_estancia = (e.fecha_checkout.date() - e.fecha_checkin.date()).days
        else:
            e.dias_estancia = (timezone.now().date() - e.fecha_checkin.date()).days or 1

    return render(request, 'estancias/lista.html', {'estancias': estancias})


