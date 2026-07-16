from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from django.db import models, transaction

from config import roles
from reportes.models import registrar_auditoria
from utils.auditoria import log_action
from .models import Caja, MovimientoCaja, AnomaliaCaja
from .services import obtener_caja_abierta


def _es_admin(user):
    return roles.es_admin(user)


def _es_recepcionista(user):
    return roles.es_recepcionista(user)


def _acceso_denegado(request, msg="No tiene permisos para acceder a esta sección."):
    return render(request, '403.html', {'mensaje_error': msg}, status=403)


@login_required
def caja_dashboard(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    caja_activa = obtener_caja_abierta(request.user)
    if not caja_activa:
        # Si no hay caja abierta, forzar a abrir una
        return render(request, 'caja/aperturar.html')

    movimientos = caja_activa.movimientos.all().select_related('usuario', 'pago_origen', 'reembolso_origen')
    anomalias = caja_activa.anomalias.all().select_related('resuelta_por')

    return render(request, 'caja/dashboard.html', {
        'caja': caja_activa,
        'movimientos': movimientos,
        'anomalias': anomalias,
    })


@login_required
def caja_aperturar(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    if request.method == 'POST':
        monto_inicial_str = request.POST.get('monto_inicial', '0')
        observacion = request.POST.get('observacion_apertura', '').strip()

        # RN-CAJ-002: No permitir abrir si ya hay una abierta
        caja_existente = obtener_caja_abierta(request.user)
        if caja_existente:
            messages.error(request, "Ya tienes una caja abierta para tu usuario.")
            return redirect('caja_dashboard')

        try:
            monto_inicial = Decimal(monto_inicial_str)
            # RN-CAJ-003: No negativo
            if monto_inicial < 0:
                raise ValidationError("El monto inicial no puede ser negativo.")

            with transaction.atomic():
                caja = Caja.objects.create(
                    usuario=request.user,
                    monto_inicial=monto_inicial,
                    monto_esperado=monto_inicial,
                    observacion_apertura=observacion,
                    estado=Caja.ABIERTA
                )
                
                # Registrar auditoría
                log_action(
                    user=request.user,
                    accion="Apertura de Caja",
                    registro_id=caja.id,
                    tabla_afectada="caja_caja",
                    observacion=f"Aperturada con saldo inicial de S/. {monto_inicial:.2f}"
                )
                
            messages.success(request, f"Caja #{caja.id} aperturada correctamente.")
        except Exception as e:
            messages.error(request, f"Error al abrir caja: {str(e)}")

    return redirect('caja_dashboard')


@login_required
def caja_movimiento_registrar(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    caja = obtener_caja_abierta(request.user)
    if not caja:
        messages.error(request, "Debes abrir una caja primero.")
        return redirect('caja_dashboard')

    if request.method == 'POST':
        monto_str = request.POST.get('monto', '0')
        tipo = request.POST.get('tipo')
        concepto = request.POST.get('concepto', MovimientoCaja.OTROS)
        metodo_pago = request.POST.get('metodo_pago', MovimientoCaja.EFECTIVO)
        descripcion = request.POST.get('descripcion', '').strip()
        referencia = request.POST.get('referencia', '').strip() or None

        try:
            monto = Decimal(monto_str)
            if monto <= 0:
                raise ValidationError("El monto debe ser mayor a cero.")
            if tipo not in [MovimientoCaja.INGRESO, MovimientoCaja.EGRESO]:
                raise ValidationError("Tipo de movimiento inválido.")

            with transaction.atomic():
                mov = MovimientoCaja.objects.create(
                    caja=caja,
                    monto=monto,
                    tipo=tipo,
                    concepto=concepto,
                    metodo_pago=metodo_pago,
                    descripcion=descripcion,
                    usuario=request.user,
                    referencia=referencia
                )

                log_action(
                    user=request.user,
                    accion="Movimiento Manual Caja",
                    registro_id=mov.id,
                    tabla_afectada="caja_movimientocaja",
                    observacion=f"Tipo: {tipo}, Monto: S/. {monto:.2f}, Concepto: {concepto}"
                )

            messages.success(request, "Movimiento registrado correctamente.")
        except Exception as e:
            messages.error(request, f"Error al registrar movimiento: {str(e)}")

    return redirect('caja_dashboard')


@login_required
def caja_arqueo(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    caja = obtener_caja_abierta(request.user)
    if not caja:
        messages.error(request, "Debes abrir una caja primero.")
        return redirect('caja_dashboard')

    if request.method == 'POST':
        monto_real_str = request.POST.get('monto_real', '0')
        observacion = request.POST.get('observacion_cierre', '').strip()

        try:
            monto_real = Decimal(monto_real_str)
            if monto_real < 0:
                raise ValidationError("El monto real no puede ser negativo.")

            with transaction.atomic():
                caja.monto_real = monto_real
                caja.arqueada = True
                caja.fecha_arqueo = timezone.now()
                caja.observacion_cierre = observacion
                caja.recalcular_totales()  # Esto calcula la diferencia

                # Registrar anomalía si hay diferencia
                if caja.diferencia != 0:
                    tipo_anomalia = AnomaliaCaja.SOBRANTE if caja.diferencia > 0 else AnomaliaCaja.FALTANTE
                    AnomaliaCaja.objects.create(
                        caja=caja,
                        tipo=tipo_anomalia,
                        monto=abs(caja.diferencia),
                        observacion=f"Diferencia detectada en Arqueo: {observacion or 'Sin observaciones'}"
                    )

                log_action(
                    user=request.user,
                    accion="Arqueo de Caja",
                    registro_id=caja.id,
                    tabla_afectada="caja_caja",
                    observacion=f"Monto contado: S/. {monto_real:.2f}, Esperado: S/. {caja.monto_esperado:.2f}, Diferencia: S/. {caja.diferencia:.2f}"
                )

            messages.success(request, f"Arqueo completado. Diferencia calculada: S/. {caja.diferencia:.2f}")
        except Exception as e:
            messages.error(request, f"Error al realizar arqueo: {str(e)}")

    return redirect('caja_dashboard')


@login_required
def caja_cerrar(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    caja = obtener_caja_abierta(request.user)
    if not caja:
        messages.error(request, "Debes abrir una caja primero.")
        return redirect('caja_dashboard')

    # RN-CAJ-030: No cerrar sin arqueo
    if not caja.arqueada:
        messages.error(request, "Debe realizar el arqueo de caja antes de poder cerrarla.")
        return redirect('caja_dashboard')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                caja.estado = Caja.CERRADA
                caja.fecha_cierre = timezone.now()
                caja.save()

                log_action(
                    user=request.user,
                    accion="Cierre de Caja",
                    registro_id=caja.id,
                    tabla_afectada="caja_caja",
                    observacion=f"Cierre definitivo de caja #{caja.id}"
                )

            messages.success(request, f"Caja #{caja.id} cerrada correctamente. Turno finalizado.")
        except Exception as e:
            messages.error(request, f"Error al cerrar caja: {str(e)}")

    return redirect('caja_dashboard')


@login_required
def caja_historial(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    cajas = Caja.objects.all().select_related('usuario')

    # Filtros
    f_fecha_inicio = request.GET.get('fecha_inicio')
    f_fecha_fin = request.GET.get('fecha_fin')
    f_usuario = request.GET.get('recepcionista')
    f_estado = request.GET.get('estado')

    if f_fecha_inicio:
        cajas = cajas.filter(fecha_apertura__date__gte=f_fecha_inicio)
    if f_fecha_fin:
        cajas = cajas.filter(fecha_apertura__date__lte=f_fecha_fin)
    if f_usuario:
        cajas = cajas.filter(usuario__id=f_usuario)
    if f_estado:
        cajas = cajas.filter(estado=f_estado)

    # Usuarios para el select del filtro
    from django.contrib.auth.models import User
    usuarios = User.objects.filter(groups__name__in=['recepcionista', 'admin']).distinct()

    return render(request, 'caja/historial.html', {
        'cajas': cajas,
        'usuarios': usuarios,
        'filtros': {
            'fecha_inicio': f_fecha_inicio,
            'fecha_fin': f_fecha_fin,
            'recepcionista': f_usuario,
            'estado': f_estado,
        }
    })


@login_required
def caja_movimientos_lista(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    movimientos = MovimientoCaja.objects.all().select_related('caja', 'usuario', 'pago_origen', 'reembolso_origen')

    # Filtros
    f_tipo = request.GET.get('tipo')
    f_concepto = request.GET.get('concepto')
    f_metodo = request.GET.get('metodo_pago')

    if f_tipo:
        movimientos = movimientos.filter(tipo=f_tipo)
    if f_concepto:
        movimientos = movimientos.filter(concepto=f_concepto)
    if f_metodo:
        movimientos = movimientos.filter(metodo_pago=f_metodo)

    return render(request, 'caja/movimientos.html', {
        'movimientos': movimientos,
        'filtros': {
            'tipo': f_tipo,
            'concepto': f_concepto,
            'metodo_pago': f_metodo,
        }
    })


@login_required
def caja_anomalias_lista(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    anomalias = AnomaliaCaja.objects.all().select_related('caja', 'caja__usuario', 'resuelta_por')

    return render(request, 'caja/anomalias.html', {
        'anomalias': anomalias,
    })


@login_required
def caja_anomalia_resolver(request, pk):
    if not _es_admin(request.user):
        return _acceso_denegado(request, "Solo los administradores pueden resolver anomalías de caja.")

    anomalia = get_object_or_404(AnomaliaCaja, id=pk)
    if request.method == 'POST':
        anomalia.resuelta = True
        anomalia.resuelta_por = request.user
        anomalia.fecha_resolucion = timezone.now()
        anomalia.save()

        log_action(
            user=request.user,
            accion="Resolución de Anomalía",
            registro_id=anomalia.id,
            tabla_afectada="caja_anomaliacaja",
            observacion=f"Anomalía #{anomalia.id} marcada como resuelta."
        )

        messages.success(request, f"Anomalía #{anomalia.id} marcada como resuelta.")

    return redirect('caja_anomalias')


@login_required
def caja_imprimir_acta(request, pk):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    caja = get_object_or_404(Caja.objects.select_related('usuario'), id=pk)
    movimientos = caja.movimientos.all().select_related('usuario', 'pago_origen', 'reembolso_origen')
    anomalias = caja.anomalias.all().select_related('resuelta_por')

    # Sumatorios por método de pago para el arqueo impreso
    metodos_resumen = {}
    for choice in MovimientoCaja.METODO_PAGO_CHOICES:
        m_code = choice[0]
        m_label = choice[1]
        t_ingresos = movimientos.filter(metodo_pago=m_code, tipo=MovimientoCaja.INGRESO).aggregate(tot=models.Sum('monto'))['tot'] or Decimal('0.00')
        t_egresos = movimientos.filter(metodo_pago=m_code, tipo=MovimientoCaja.EGRESO).aggregate(tot=models.Sum('monto'))['tot'] or Decimal('0.00')
        metodos_resumen[m_label] = {
            'ingresos': t_ingresos,
            'egresos': t_egresos,
            'neto': t_ingresos - t_egresos,
        }

    return render(request, 'caja/acta_imprimir.html', {
        'caja': caja,
        'movimientos': movimientos,
        'anomalias': anomalias,
        'metodos_resumen': metodos_resumen,
    })
