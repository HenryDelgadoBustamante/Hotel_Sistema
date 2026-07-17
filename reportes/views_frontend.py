from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import models
from django.db.models import Sum, Q, Count, Avg
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from datetime import timedelta, datetime
from decimal import Decimal
import json
from hotel.models import Habitacion, TipoHabitacion
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia, CargoEstancia, Folio, Pago, Reembolso, HistorialHabitacionEstancia
from atencion.models import TicketServicio
from reportes.models import Auditoria
from config.views_shared import _es_admin, _es_recepcionista, _acceso_denegado


@login_required
def reportes_view(request):
    if not (_es_admin(request.user) or _es_recepcionista(request.user)):
        return _acceso_denegado(request, 'No tiene permiso para ver esta sección.')
    
    is_admin = _es_admin(request.user)
    is_recep = _es_recepcionista(request.user)
    
    import json
    from datetime import timedelta, datetime
    from django.utils import timezone
    from django.db import models
    from django.db.models import Sum, Q, Count, Avg
    from django.db.models.functions import TruncMonth
    from estancias.models import Estancia, CargoEstancia, Folio, Pago, Reembolso, HistorialHabitacionEstancia
    from reservas.models import Reserva, Huesped
    from hotel.models import Habitacion, TipoHabitacion
    from reportes.models import Auditoria
    from atencion.models import TicketServicio
    from decimal import Decimal
    
    hoy = timezone.now().date()
    periodo = request.GET.get('periodo', '')
    fecha_inicio_str = request.GET.get('fecha_inicio', '').strip()
    fecha_fin_str = request.GET.get('fecha_fin', '').strip()
    
    if fecha_inicio_str and fecha_fin_str:
        try:
            start_date = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            periodo = 'custom'
        except ValueError:
            periodo = 'mes'
    
    if not periodo or periodo not in ['hoy', 'semana', 'mes', 'anio', 'custom']:
        periodo = 'mes'
        
    if periodo == 'hoy':
        start_date = hoy
        end_date = hoy
    elif periodo == 'semana':
        start_date = hoy - timedelta(days=hoy.weekday())
        end_date = start_date + timedelta(days=6)
    elif periodo == 'anio':
        start_date = hoy.replace(month=1, day=1)
        end_date = hoy.replace(month=12, day=31)
    elif periodo == 'mes':
        start_date = hoy.replace(day=1)
        next_month = start_date.replace(day=28) + timedelta(days=4)
        end_date = next_month - timedelta(days=next_month.day)
        
    dias = (end_date - start_date).days + 1
    
    if periodo == 'hoy':
        prev_start = start_date - timedelta(days=1)
        prev_end = prev_start
    elif periodo == 'semana':
        prev_start = start_date - timedelta(days=7)
        prev_end = end_date - timedelta(days=7)
    elif periodo == 'anio':
        prev_start = start_date.replace(year=start_date.year - 1)
        prev_end = end_date.replace(year=end_date.year - 1)
    else:
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=dias - 1)
        
    dias_prev = (prev_end - prev_start).days + 1
    
    active_tab = request.GET.get('tab', 'general')
    if not is_admin:
        if active_tab in ['general', 'finanzas']:
            active_tab = 'ocupacion'
            
    f_piso = request.GET.get('piso', '')
    f_tipo = request.GET.get('tipo_habitacion', '')
    f_estado = request.GET.get('estado', '')
    f_habitacion = request.GET.get('habitacion', '')
    
    total_habitaciones = Habitacion.objects.count()
    rooms_maint = Habitacion.objects.filter(estado='MANTENIMIENTO').count()
    hab_disponibles_periodo = max(1, (total_habitaciones - rooms_maint) * dias)
    hab_disponibles_prev = max(1, (total_habitaciones - rooms_maint) * dias_prev)
    
    estancias_periodo = Estancia.objects.filter(fecha_checkin__date__gte=start_date, fecha_checkin__date__lte=end_date)
    noches_actual = 0
    for e in estancias_periodo:
        if e.reserva.modalidad == 'DIA':
            noches_actual += max(1, (e.reserva.fecha_salida - e.reserva.fecha_entrada).days)
        else:
            noches_actual += 1
            
    ocupacion_actual = round((noches_actual / hab_disponibles_periodo * 100), 1) if hab_disponibles_periodo > 0 else 0.0
    
    estancias_prev = Estancia.objects.filter(fecha_checkin__date__gte=prev_start, fecha_checkin__date__lte=prev_end)
    noches_prev = 0
    for e in estancias_prev:
        if e.reserva.modalidad == 'DIA':
            noches_prev += max(1, (e.reserva.fecha_salida - e.reserva.fecha_entrada).days)
        else:
            noches_prev += 1
    ocupacion_prev = round((noches_prev / hab_disponibles_prev * 100), 1) if hab_disponibles_prev > 0 else 0.0
    
    revenue_total = CargoEstancia.objects.filter(
        fecha__date__gte=start_date, fecha__date__lte=end_date
    ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    
    revenue_prev = CargoEstancia.objects.filter(
        fecha__date__gte=prev_start, fecha__date__lte=prev_end
    ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    
    revenue_hab = CargoEstancia.objects.filter(
        tipo='HABITACION', fecha__date__gte=start_date, fecha__date__lte=end_date
    ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    
    revenue_hab_prev = CargoEstancia.objects.filter(
        tipo='HABITACION', fecha__date__gte=prev_start, fecha__date__lte=prev_end
    ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    
    adr_actual = float(revenue_hab) / noches_actual if noches_actual > 0 else 0.0
    adr_prev = float(revenue_hab_prev) / noches_prev if noches_prev > 0 else 0.0
    
    revpar_actual = float(revenue_hab) / hab_disponibles_periodo if hab_disponibles_periodo > 0 else 0.0
    revpar_prev = float(revenue_hab_prev) / hab_disponibles_prev if hab_disponibles_prev > 0 else 0.0
    
    def calc_var(actual, prev):
        if prev == 0: return 100.0 if actual > 0 else 0.0
        return round(((float(actual) - float(prev)) / float(prev)) * 100, 1)
        
    variaciones = {
        'ocupacion': calc_var(ocupacion_actual, ocupacion_prev),
        'revenue': calc_var(revenue_total, revenue_prev),
        'adr': calc_var(adr_actual, adr_prev),
        'revpar': calc_var(revpar_actual, revpar_prev)
    }
    
    context = {
        'periodo': periodo,
        'start_date': start_date,
        'end_date': end_date,
        'active_tab': active_tab,
        'is_admin': is_admin,
        'is_recep': is_recep,
        'mostrar_financiero': is_admin,
        'ocupacion_actual': ocupacion_actual,
        'revenue_total': revenue_total,
        'adr_actual': adr_actual,
        'revpar_actual': revpar_actual,
        'variaciones': variaciones,
    }
    
    if active_tab == 'general':
        estancias_activas_qs = Estancia.objects.filter(estado='ACTIVA').select_related('habitacion__tipo')
        ocupacion_por_tipo = {}
        for e in estancias_activas_qs:
            tipo = e.habitacion.tipo.nombre
            ocupacion_por_tipo[tipo] = ocupacion_por_tipo.get(tipo, 0) + 1
            
        doce_meses_atras = hoy.replace(day=1) - timedelta(days=365)
        ingresos_mensuales = CargoEstancia.objects.filter(fecha__date__gte=doce_meses_atras) \
            .annotate(mes=TruncMonth('fecha')) \
            .values('mes') \
            .annotate(total=Sum('monto')) \
            .order_by('mes')
        
        meses_labels = [i['mes'].strftime('%b %Y') for i in ingresos_mensuales]
        meses_data = [float(i['total']) for i in ingresos_mensuales]
        
        ingresos_origen = Reserva.objects.filter(
            fecha_entrada__gte=start_date, fecha_entrada__lte=end_date, estado__in=['CHECKIN', 'CHECKOUT']
        ).values('origen').annotate(total=Sum('precio_total'))
        
        origen_labels = [i['origen'] for i in ingresos_origen]
        origen_data = [float(i['total']) for i in ingresos_origen]
        
        ultimas_estancias = Estancia.objects.all().select_related('reserva__huesped', 'habitacion__tipo').order_by('-fecha_checkin')[:8]
        reservas_pendientes = Reserva.objects.filter(estado__in=['PENDIENTE', 'CONFIRMADA'], fecha_entrada__gte=hoy).order_by('fecha_entrada')[:5]
        
        reservas_confirmadas = Reserva.objects.filter(fecha_entrada__gte=start_date, fecha_entrada__lte=end_date, estado__in=['CONFIRMADA', 'CHECKIN', 'CHECKOUT']).count()
        reservas_canceladas = Reserva.objects.filter(fecha_entrada__gte=start_date, fecha_entrada__lte=end_date, estado='CANCELADA').count()
        estancias_activas_count = Estancia.objects.filter(estado='ACTIVA').count()
        estancias_canceladas_count = Estancia.objects.filter(fecha_checkin__date__gte=start_date, fecha_checkin__date__lte=end_date, estado='CANCELADA').count()
        
        duracion_avg = Reserva.objects.filter(
            fecha_entrada__gte=start_date, fecha_entrada__lte=end_date, estado__in=['CHECKIN', 'CHECKOUT']
        ).aggregate(avg_d=Avg('duracion_horas'))['avg_d'] or 0.0
        
        reembolsos_aprobados = Reembolso.objects.filter(fecha_resolucion__date__gte=start_date, fecha_resolucion__date__lte=end_date, estado='APROBADO').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        
        pago_popular = Pago.objects.filter(fecha__date__gte=start_date, fecha__date__lte=end_date).values('metodo_pago').annotate(cnt=Count('id')).order_by('-cnt').first()
        metodo_pago_popular = pago_popular['metodo_pago'] if pago_popular else 'Ninguno'
        
        completions = Auditoria.objects.filter(
            tabla_afectada="hotel_habitacion",
            accion__in=["Housekeeping Estado Modificado", "Habitación Estado Modificado"],
            estado_nuevo="DISPONIBLE",
            estado_anterior="LIMPIEZA",
            fecha__date__gte=start_date,
            fecha__date__lte=end_date
        )
        total_limp_minutos = 0
        count_limp = 0
        for c in completions:
            start_log = Auditoria.objects.filter(
                tabla_afectada="hotel_habitacion",
                registro_id=c.registro_id,
                estado_nuevo="LIMPIEZA",
                fecha__lt=c.fecha
            ).order_by('-fecha').first()
            if start_log:
                diff = c.fecha - start_log.fecha
                if diff.total_seconds() > 0 and diff < timedelta(hours=6):
                    total_limp_minutos += diff.total_seconds() / 60
                    count_limp += 1
        tiempo_limpieza_prom = round(total_limp_minutos / count_limp, 1) if count_limp > 0 else 0.0
        
        tkt_pendientes = TicketServicio.objects.filter(estado__in=['ABIERTA', 'PROCESO', 'PENDIENTE']).count()
        
        context.update({
            'tipos_labels_json': json.dumps(list(ocupacion_por_tipo.keys())),
            'tipos_data_json': json.dumps(list(ocupacion_por_tipo.values())),
            'meses_labels_json': json.dumps(meses_labels),
            'meses_data_json': json.dumps(meses_data),
            'origen_labels_json': json.dumps(origen_labels),
            'origen_data_json': json.dumps(origen_data),
            'ultimas_estancias': ultimas_estancias,
            'reservas_pendientes': reservas_pendientes,
            'reservas_confirmadas': reservas_confirmadas,
            'reservas_canceladas': reservas_canceladas,
            'estancias_activas_count': estancias_activas_count,
            'estancias_canceladas_count': estancias_canceladas_count,
            'duracion_avg': round(duracion_avg, 1),
            'reembolsos_aprobados': reembolsos_aprobados,
            'metodo_pago_popular': metodo_pago_popular,
            'tiempo_limpieza_prom': tiempo_limpieza_prom,
            'tickets_pendientes': tkt_pendientes,
        })
        
    elif active_tab == 'ocupacion':
        habs_qs = Habitacion.objects.all().select_related('tipo')
        if f_piso:
            habs_qs = habs_qs.filter(piso=f_piso)
        if f_tipo:
            habs_qs = habs_qs.filter(tipo_id=f_tipo)
        if f_estado:
            habs_qs = habs_qs.filter(estado=f_estado)
        if f_habitacion:
            habs_qs = habs_qs.filter(id=f_habitacion)
            
        hab_list = []
        tipo_count = {}
        for h in habs_qs:
            est_hab = Estancia.objects.filter(habitacion=h, fecha_checkin__date__lte=end_date)
            noches_hab = 0
            for e in est_hab:
                e_end = e.fecha_checkout.date() if e.fecha_checkout else hoy
                e_start = e.fecha_checkin.date()
                o_start = max(e_start, start_date)
                o_end = min(e_end, end_date)
                overlap = (o_end - o_start).days
                if overlap > 0:
                    noches_hab += overlap
                elif e_start >= start_date and e_start <= end_date:
                    noches_hab += 1
            pct = round((noches_hab / dias * 100), 1) if dias > 0 else 0
            hab_list.append({
                'id': h.id,
                'numero': h.numero,
                'piso': h.piso,
                'tipo': h.tipo.nombre,
                'estado': h.estado,
                'noches_ocupadas': noches_hab,
                'pct_ocupacion': pct
            })
            if noches_hab > 0:
                tipo_count[h.tipo.nombre] = tipo_count.get(h.tipo.nombre, 0) + noches_hab
                
        tipo_solicitado = max(tipo_count, key=tipo_count.get) if tipo_count else 'Ninguno'
        noches_totales_disponibles = habs_qs.count() * dias
        noches_totales_ocupadas = sum(h['noches_ocupadas'] for h in hab_list)
        tasa_ocupacion_consolidada = round((noches_totales_ocupadas / noches_totales_disponibles * 100), 1) if noches_totales_disponibles > 0 else 0.0
        
        context.update({
            'habitaciones_reporte': hab_list,
            'noches_totales_disponibles': noches_totales_disponibles,
            'noches_totales_ocupadas': noches_totales_ocupadas,
            'tasa_ocupacion_consolidada': tasa_ocupacion_consolidada,
            'tipo_solicitado': tipo_solicitado,
            'pisos': Habitacion.objects.values_list('piso', flat=True).distinct().order_by('piso'),
            'tipos_habitacion': TipoHabitacion.objects.all(),
            'habitaciones_all': Habitacion.objects.all().order_by('numero'),
            'f_piso': f_piso,
            'f_tipo': f_tipo,
            'f_estado': f_estado,
            'f_habitacion': f_habitacion,
        })
        
    elif active_tab == 'reservas':
        res_qs = Reserva.objects.filter(fecha_entrada__gte=start_date, fecha_entrada__lte=end_date).select_related('huesped', 'habitacion__tipo')
        if f_tipo:
            res_qs = res_qs.filter(habitacion__tipo_id=f_tipo)
        if f_estado:
            res_qs = res_qs.filter(estado=f_estado)
            
        reservas_lista_reporte = []
        for r in res_qs:
            anticipo = r.pagos.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
            reemb = Reembolso.objects.filter(pago__reserva=r, estado='APROBADO').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
            retenido = Decimal('0.00')
            if r.estado == 'CANCELADA':
                retenido = max(Decimal('0.00'), anticipo - reemb)
            reservas_lista_reporte.append({
                'id': r.id,
                'guest': f"{r.huesped.nombres} {r.huesped.apellidos}",
                'room': r.habitacion.numero if r.habitacion else 'Sin asignar',
                'tipo': r.habitacion.tipo.nombre if r.habitacion else 'Sin asignar',
                'entrada': r.fecha_entrada,
                'salida': r.fecha_salida,
                'estado': r.estado,
                'precio_total': r.precio_total,
                'anticipo': anticipo,
                'reembolso': reemb,
                'retenido': retenido,
                'motivo_cancelacion': r.motivo_cancelacion or '—'
            })
            
        counts = res_qs.values('estado').annotate(cnt=Count('id'))
        cnt_dict = {c['estado']: c['cnt'] for c in counts}
        
        cancelaciones_con_reembolso_total = 0
        cancelaciones_con_reembolso_parcial = 0
        cancelaciones_sin_reembolso = 0
        monto_reembolsado_total = Decimal('0.00')
        monto_retenido_total = Decimal('0.00')
        
        for item in reservas_lista_reporte:
            if item['estado'] == 'CANCELADA':
                monto_reembolsado_total += item['reembolso']
                monto_retenido_total += item['retenido']
                if item['anticipo'] > 0:
                    if item['reembolso'] == item['anticipo']:
                        cancelaciones_con_reembolso_total += 1
                    elif item['reembolso'] > 0:
                        cancelaciones_con_reembolso_parcial += 1
                    else:
                        cancelaciones_sin_reembolso += 1
                else:
                    cancelaciones_sin_reembolso += 1
                    
        context.update({
            'reservas_lista_reporte': reservas_lista_reporte,
            'r_pendientes': cnt_dict.get('PENDIENTE', 0),
            'r_confirmadas': cnt_dict.get('CONFIRMADA', 0),
            'r_checkin': cnt_dict.get('CHECKIN', 0),
            'r_checkout': cnt_dict.get('CHECKOUT', 0),
            'r_canceladas': cnt_dict.get('CANCELADA', 0),
            'r_reembolsado': cnt_dict.get('REEMBOLSADO', 0),
            'cancelaciones_reembolso_total': cancelaciones_con_reembolso_total,
            'cancelaciones_reembolso_parcial': cancelaciones_con_reembolso_parcial,
            'cancelaciones_sin_reembolso': cancelaciones_sin_reembolso,
            'monto_reembolsado_total': monto_reembolsado_total,
            'monto_retenido_total': monto_retenido_total,
            'tipos_habitacion': TipoHabitacion.objects.all(),
            'f_tipo': f_tipo,
            'f_estado': f_estado,
        })
        
    elif active_tab == 'estancias':
        est_qs = Estancia.objects.filter(fecha_checkin__date__gte=start_date, fecha_checkin__date__lte=end_date).select_related('reserva__huesped', 'habitacion__tipo')
        if f_tipo:
            est_qs = est_qs.filter(habitacion__tipo_id=f_tipo)
        if f_estado:
            est_qs = est_qs.filter(estado=f_estado)
            
        estancias_lista_reporte = []
        early_count = 0
        late_count = 0
        salidas_anticipadas = 0
        
        for e in est_qs:
            total_alojamiento = e.cargos.filter(tipo='HABITACION').exclude(concepto__icontains="Salida Tardía").exclude(concepto__icontains="Early Check-In").aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
            total_consumos = e.cargos.filter(tipo='CONSUMO').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
            cargo_early = e.cargos.filter(concepto__icontains="Early Check-In").aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
            if cargo_early > 0:
                early_count += 1
            cargo_late = e.cargos.filter(concepto__icontains="Salida Tardía").aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
            if cargo_late > 0:
                late_count += 1
            is_anticipada = False
            if e.fecha_checkout and e.fecha_checkout.date() < e.reserva.fecha_salida:
                is_anticipada = True
                salidas_anticipadas += 1
            duracion_prog_horas = (e.reserva.fecha_hora_salida - e.reserva.fecha_hora_entrada).total_seconds() / 3600 if e.reserva.fecha_hora_salida and e.reserva.fecha_hora_entrada else 0
            duracion_real_horas = 0
            if e.fecha_checkin:
                checkout_time = e.fecha_checkout or timezone.now()
                duracion_real_horas = (checkout_time - e.fecha_checkin).total_seconds() / 3600
                
            folio = getattr(e, 'folio', None)
            total_pagado = folio.total_pagado if folio else Decimal('0.00')
            saldo_pendiente = folio.saldo_pendiente if folio else Decimal('0.00')
            
            estancias_lista_reporte.append({
                'id': e.id,
                'guest': f"{e.reserva.huesped.nombres} {e.reserva.huesped.apellidos}",
                'room': e.habitacion.numero,
                'tipo': e.habitacion.tipo.nombre,
                'checkin': e.fecha_checkin,
                'checkout': e.fecha_checkout,
                'checkout_prog': e.reserva.fecha_hora_salida,
                'duracion_prog': round(duracion_prog_horas, 1),
                'duracion_real': round(duracion_real_horas, 1),
                'total_alojamiento': total_alojamiento,
                'total_consumos': total_consumos,
                'cargo_early': cargo_early,
                'cargo_late': cargo_late,
                'total_pagado': total_pagado,
                'saldo_pendiente': saldo_pendiente,
                'is_anticipada': is_anticipada,
                'estado': e.estado
            })
            
        context.update({
            'estancias_lista_reporte': estancias_lista_reporte,
            'est_activas': est_qs.filter(estado='ACTIVA').count(),
            'est_finalizadas': est_qs.filter(estado='FINALIZADA').count(),
            'est_canceladas': est_qs.filter(estado='CANCELADA').count(),
            'early_count': early_count,
            'late_count': late_count,
            'salidas_anticipadas': salidas_anticipadas,
            'tipos_habitacion': TipoHabitacion.objects.all(),
            'f_tipo': f_tipo,
            'f_estado': f_estado,
        })
        
    elif active_tab == 'finanzas' and is_admin:
        saldo_inicial = Pago.objects.filter(fecha__lt=start_date).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        reembolsos_inicial = Reembolso.objects.filter(fecha_resolucion__lt=start_date, estado='APROBADO').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        saldo_inicial_neto = saldo_inicial - reembolsos_inicial
        
        pagos_qs = Pago.objects.filter(fecha__date__gte=start_date, fecha__date__lte=end_date).select_related('folio__estancia__habitacion', 'reserva__huesped')
        reemb_qs = Reembolso.objects.filter(fecha_resolucion__date__gte=start_date, fecha_resolucion__date__lte=end_date, estado='APROBADO').select_related('pago__reserva__huesped', 'pago__folio__estancia__habitacion')
        
        ingresos_periodo = pagos_qs.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        reembolsos_periodo = reemb_qs.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        egresos_periodo = Decimal('0.00')
        balance_neto = ingresos_periodo - reembolsos_periodo
        
        metodos_pago_stats = pagos_qs.values('metodo_pago').annotate(total=Sum('monto')).order_by('-total')
        
        cargos_caja_qs = CargoEstancia.objects.filter(fecha__date__gte=start_date, fecha__date__lte=end_date)
        origen_cargos_stats = cargos_caja_qs.values('tipo').annotate(total=Sum('monto')).order_by('-total')
        
        movimientos = []
        for p in pagos_qs:
            refunded_amt = p.reembolsos.filter(estado='APROBADO').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
            movimientos.append({
                'tipo': 'INGRESO',
                'origen': f"Folio #{p.folio.id}" if p.folio else f"Reserva #{p.reserva.id}",
                'huesped': p.folio.estancia.reserva.huesped.nombre_completo if p.folio else p.reserva.huesped.nombre_completo,
                'metodo': p.get_metodo_pago_display(),
                'referencia': p.transaccion_id or '—',
                'fecha': p.fecha,
                'monto': p.monto,
                'reembolsado': refunded_amt
            })
        for r in reemb_qs:
            movimientos.append({
                'tipo': 'REEMBOLSO',
                'origen': f"Pago #{r.pago.id}",
                'huesped': r.pago.folio.estancia.reserva.huesped.nombre_completo if r.pago.folio else r.pago.reserva.huesped.nombre_completo,
                'metodo': r.pago.get_metodo_pago_display(),
                'referencia': f"Reembolso #{r.id}",
                'fecha': r.fecha_resolucion,
                'monto': -r.monto,
                'reembolsado': Decimal('0.00')
            })
        movimientos.sort(key=lambda x: x['fecha'], reverse=True)
        
        context.update({
            'saldo_inicial_neto': saldo_inicial_neto,
            'ingresos_periodo': ingresos_periodo,
            'egresos_periodo': egresos_periodo,
            'reembolsos_periodo': reembolsos_periodo,
            'balance_neto': balance_neto,
            'metodos_pago_stats': metodos_pago_stats,
            'origen_cargos_stats': origen_cargos_stats,
            'movimientos': movimientos,
        })
        
    elif active_tab == 'clientes':
        huespedes_qs = Huesped.objects.annotate(
            total_bookings=Count('reservas', distinct=True),
            total_estancias=Count('reservas__estancia', distinct=True)
        )
        huespedes_lista_reporte = []
        for h in huespedes_qs:
            pagos_h = Pago.objects.filter(Q(folio__estancia__reserva__huesped=h) | Q(reserva__huesped=h))
            gasto_total = pagos_h.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
            reemb_h = Reembolso.objects.filter(Q(pago__folio__estancia__reserva__huesped=h) | Q(pago__reserva__huesped=h), estado='APROBADO')
            reembolso_total = reemb_h.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
            gasto_neto = gasto_total - reembolso_total
            cancelaciones = h.reservas.filter(estado='CANCELADA').count()
            noches_total = 0
            estancias_h = Estancia.objects.filter(reserva__huesped=h)
            for e in estancias_h:
                if e.reserva.modalidad == 'DIA':
                    noches_total += max(1, (e.reserva.fecha_salida - e.reserva.fecha_entrada).days)
                else:
                    noches_total += 1
            if h.total_estancias > 0 or gasto_neto > 0:
                huespedes_lista_reporte.append({
                    'id': h.id,
                    'nombre': h.nombre_completo,
                    'doc': f"{h.tipo_doc} {h.num_doc}",
                    'telefono': h.telefono or '—',
                    'bookings_count': h.total_bookings,
                    'estancias_count': h.total_estancias,
                    'cancelaciones_count': cancelaciones,
                    'noches_hospedadas': noches_total,
                    'gasto_neto': gasto_neto,
                    'promedio_estancia': round(noches_total / h.total_estancias, 1) if h.total_estancias > 0 else 0
                })
        huespedes_lista_reporte.sort(key=lambda x: x['gasto_neto'], reverse=True)
        context.update({
            'huespedes_lista_reporte': huespedes_lista_reporte[:30],
        })
        
    elif active_tab == 'housekeeping':
        limpiezas_aud = Auditoria.objects.filter(
            tabla_afectada="hotel_habitacion",
            accion__in=["Housekeeping Estado Modificado", "Habitación Estado Modificado"],
            estado_nuevo="DISPONIBLE",
            estado_anterior="LIMPIEZA",
            fecha__date__gte=start_date,
            fecha__date__lte=end_date
        ).select_related('usuario')
        
        limpiezas_lista = []
        user_counts = {}
        total_minutos = 0
        count_limp = 0
        
        for c in limpiezas_aud:
            start_log = Auditoria.objects.filter(
                tabla_afectada="hotel_habitacion",
                registro_id=c.registro_id,
                estado_nuevo="LIMPIEZA",
                fecha__lt=c.fecha
            ).order_by('-fecha').first()
            duracion = '—'
            if start_log:
                diff = c.fecha - start_log.fecha
                if diff.total_seconds() > 0 and diff < timedelta(hours=6):
                    mins = int(diff.total_seconds() // 60)
                    duracion = f"{mins} min"
                    total_minutos += mins
                    count_limp += 1
            limpiezas_lista.append({
                'habitacion_id': c.registro_id,
                'fecha': c.fecha,
                'usuario': c.usuario.username if c.usuario else 'Sistema',
                'duracion': duracion,
                'estado_anterior': c.estado_anterior,
                'estado_nuevo': c.estado_nuevo
            })
            u_name = c.usuario.username if c.usuario else 'Sistema'
            user_counts[u_name] = user_counts.get(u_name, 0) + 1
            
        tiempo_limpieza_prom = round(total_minutos / count_limp, 1) if count_limp > 0 else 0
        status_counts = Habitacion.objects.values('estado').annotate(cnt=Count('id'))
        status_dict = {s['estado']: s['cnt'] for s in status_counts}
        
        context.update({
            'limpiezas_lista': limpiezas_lista[:50],
            'tiempo_limpieza_prom': tiempo_limpieza_prom,
            'limpiezas_por_usuario': user_counts,
            'hab_disponibles': status_dict.get('DISPONIBLE', 0),
            'hab_ocupadas': status_dict.get('OCUPADA', 0),
            'hab_limpieza': status_dict.get('LIMPIEZA', 0),
            'hab_mantenimiento': status_dict.get('MANTENIMIENTO', 0),
        })
        
    elif active_tab == 'atencion':
        tickets_qs = TicketServicio.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date).select_related('estancia__habitacion')
        by_state = tickets_qs.values('estado').annotate(cnt=Count('id'))
        state_dict = {s['estado']: s['cnt'] for s in by_state}
        by_priority = tickets_qs.values('prioridad').annotate(cnt=Count('id'))
        priority_dict = {p['prioridad']: p['cnt'] for p in by_priority}
        by_cat = tickets_qs.values('categoria').annotate(cnt=Count('id')).order_by('-cnt')
        
        tickets_resueltos = tickets_qs.filter(estado__in=['RESUELTA', 'CERRADA'], resolved_at__isnull=False)
        total_res_minutos = 0
        count_res = 0
        for t in tickets_resueltos:
            diff = t.resolved_at - t.created_at
            if diff.total_seconds() > 0:
                total_res_minutos += diff.total_seconds() // 60
                count_res += 1
        tiempo_resolucion_prom = round(total_res_minutos / count_res, 1) if count_res > 0 else 0
        
        tickets_pendientes_list = []
        pending_tkts = tickets_qs.filter(estado__in=['ABIERTA', 'PROCESO', 'PENDIENTE']).order_by('-created_at')
        for t in pending_tkts:
            diff = timezone.now() - t.created_at
            horas = int(diff.total_seconds() // 3600)
            mins = int((diff.total_seconds() % 3600) // 60)
            elapsed = f"{horas}h {mins}m" if horas > 0 else f"{mins} min"
            tickets_pendientes_list.append({
                'id': t.id,
                'numero': t.numero_atencion,
                'habitacion': t.estancia.habitacion.numero,
                'categoria': t.get_categoria_display(),
                'prioridad': t.prioridad,
                'estado': t.get_estado_display(),
                'descripcion': t.descripcion,
                'responsable': t.get_responsable_display(),
                'tiempo_transcurrido': elapsed,
                'fecha': t.created_at
            })
            
        context.update({
            'tickets_pendientes_list': tickets_pendientes_list,
            'tiempo_resolucion_prom': tiempo_resolucion_prom,
            'tkt_abiertos': state_dict.get('ABIERTA', 0),
            'tkt_proceso': state_dict.get('PROCESO', 0),
            'tkt_pendientes': state_dict.get('PENDIENTE', 0),
            'tkt_resueltos': state_dict.get('RESUELTA', 0) + state_dict.get('CERRADA', 0),
            'tkt_alta_urgente': priority_dict.get('ALTA', 0) + priority_dict.get('URGENTE', 0),
            'tkt_prioridades': priority_dict,
            'tkt_categorias': by_cat,
        })
        
    return render(request, 'reportes/dashboard.html', context)


@login_required
def api_ocupacion_habitaciones(request):
    """
    Obs. 2: Retorna JSON con el estado de ocupación en tiempo real de todas las
    estancias activas. Incluye tiempos transcurridos, restantes y el flag
    `proxima_salida` que activa la alerta visual de check-out próximo.
    """
    from django.http import JsonResponse
    from datetime import timedelta

    now = timezone.localtime(timezone.now())
    try:
        from hotel.models import Hotel
        hotel = Hotel.objects.first()
        alerta_minutos = getattr(hotel, 'alerta_checkout_minutos', 30) if hotel else 30
    except Exception:
        alerta_minutos = 30

    estancias_activas = Estancia.objects.filter(
        estado=Estancia.ACTIVA
    ).select_related('reserva', 'reserva__huesped', 'habitacion')

    data = []
    for est in estancias_activas:
        checkin_local = timezone.localtime(est.fecha_checkin)
        tiempo_transcurrido = now - checkin_local
        minutos_transcurridos = int(tiempo_transcurrido.total_seconds() // 60)
        horas_t = minutos_transcurridos // 60
        mins_t = minutos_transcurridos % 60

        fecha_salida = getattr(est.reserva, 'fecha_hora_salida', None)
        minutos_restantes = None
        proxima_salida = False
        salida_vencida = False
        salida_str = '—'

        if fecha_salida:
            salida_local = timezone.localtime(fecha_salida)
            salida_str = salida_local.strftime('%H:%M %d/%m')
            diff = salida_local - now
            minutos_restantes = int(diff.total_seconds() // 60)
            proxima_salida = 0 < minutos_restantes <= alerta_minutos
            salida_vencida = minutos_restantes < 0

        huesped = est.reserva.huesped
        data.append({
            'estancia_id': est.id,
            'habitacion': est.habitacion.numero,
            'huesped': f"{huesped.nombres} {huesped.apellidos}",
            'checkin': checkin_local.strftime('%H:%M'),
            'salida_estimada': salida_str,
            'minutos_transcurridos': minutos_transcurridos,
            'tiempo_transcurrido_str': f"{horas_t}h {mins_t:02d}m",
            'minutos_restantes': minutos_restantes,
            'proxima_salida': proxima_salida,
            'salida_vencida': salida_vencida,
            'folio_url': f"/estancias/{est.id}/folio/",
        })

    return JsonResponse({
        'estancias': data,
        'alerta_minutos': alerta_minutos,
        'total': len(data),
    })
