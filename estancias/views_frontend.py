from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Sum
from django.core.exceptions import ValidationError
from datetime import date, datetime, timedelta
from decimal import Decimal
from hotel.models import Habitacion, Hotel
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia, CargoEstancia, Folio, Pago, Reembolso
from utils.auditoria import log_action
from reportes.models import registrar_auditoria
from caja.services import obtener_caja_abierta, registrar_movimiento_pago, registrar_movimiento_reembolso
from config.views_shared import _es_admin, _es_recepcionista, _acceso_denegado, calcular_cargo_salida_tardia


@login_required
def checkin_directo(request, huesped_id=None):
    """
    HOT-HOS-001 – Escenario Alternativo: Check-in directo sin reserva previa.
    Cuando existe disponibilidad pero el huésped no tiene reserva, el recepcionista
    puede registrar el hospedaje directamente desde esta vista.
    Crea una Reserva (origen=DIRECTO) + Estancia + Folio en una transacción atómica.
    """
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    import estancias.services as estancia_services
    from django.db import transaction
    from huespedes.models import Huesped
    from datetime import date, timedelta

    hotel = Hotel.objects.first()
    habitaciones_disponibles = Habitacion.objects.filter(
        estado=Habitacion.DISPONIBLE
    ).select_related('tipo', 'hotel').order_by('numero')

    huesped_presel = None
    if huesped_id:
        huesped_presel = get_object_or_404(Huesped, id=huesped_id)

    if request.method == 'POST':
        hab_id = request.POST.get('habitacion_id')
        huesped_doc = request.POST.get('num_doc', '').strip()
        num_adultos = int(request.POST.get('num_adultos', 1))
        modalidad = request.POST.get('modalidad', Reserva.POR_DIA)
        observaciones = request.POST.get('observaciones', '')
        duracion_horas = Decimal(request.POST.get('duracion_horas', '3'))
        fecha_salida_str = request.POST.get('fecha_salida', '')

        if not huesped_doc:
            messages.error(request, 'El documento de identidad del huésped es obligatorio (RN-HOS-004).')
            return redirect('checkin_directo')
        if num_adultos < 1:
            messages.error(request, 'Debe registrar al menos 1 adulto (RN-HOS-005).')
            return redirect('checkin_directo')
        if not hab_id:
            messages.error(request, 'Debe seleccionar una habitación.')
            return redirect('checkin_directo')

        try:
            huesped = Huesped.objects.get(num_doc=huesped_doc)
        except Huesped.DoesNotExist:
            messages.error(
                request,
                f'No se encontró ningún huésped con el documento "{huesped_doc}". '
                'Primero debe registrar al huésped en el sistema.'
            )
            return redirect('checkin_directo')

        try:
            habitacion = Habitacion.objects.get(id=hab_id)
        except Habitacion.DoesNotExist:
            messages.error(request, 'La habitación seleccionada no existe.')
            return redirect('checkin_directo')

        try:
            if fecha_salida_str:
                from datetime import datetime as dt_import
                fecha_salida = dt_import.strptime(fecha_salida_str, '%Y-%m-%d').date()
            else:
                fecha_salida = date.today() + timedelta(days=1)
        except ValueError:
            fecha_salida = date.today() + timedelta(days=1)

        try:
            with transaction.atomic():
                reserva = Reserva.objects.create(
                    hotel=hotel or habitacion.hotel,
                    huesped=huesped,
                    habitacion=habitacion,
                    fecha_entrada=date.today(),
                    fecha_salida=fecha_salida,
                    modalidad=modalidad,
                    duracion_horas=duracion_horas if modalidad == Reserva.POR_HORA else 0,
                    num_adultos=num_adultos,
                    estado=Reserva.CONFIRMADA,
                    origen=Reserva.DIRECTO,
                    observaciones=observaciones or 'Check-in directo sin reserva previa.',
                )
                reserva.normalizar_horario()
                reserva.precio_total = reserva.calcular_precio()
                reserva.save()

                estancia = estancia_services.procesar_checkin(
                    reserva_id=reserva.id,
                    habitacion_id=habitacion.id,
                    usuario=request.user,
                    exonerar_early=False,
                )

            messages.success(
                request,
                f'Check-in directo completado. Huésped: {huesped.nombres} {huesped.apellidos} '
                f'– Hab. {habitacion.numero} – Estancia #{estancia.id}.'
            )
            return redirect('folio', estancia_id=estancia.id)

        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, 'message') else str(e))
        except Exception as e:
            messages.error(request, f'Error al registrar el hospedaje directo: {str(e)}')

        return redirect('checkin_directo')

    return render(request, 'reservas/checkin_directo.html', {
        'habitaciones': habitaciones_disponibles,
        'huesped_presel': huesped_presel,
        'today': date.today().isoformat(),
        'manana': (date.today() + timedelta(days=1)).isoformat(),
    })


@login_required
def reserva_checkin(request, reserva_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if reserva.estado not in ['PENDIENTE', 'CONFIRMADA']:
        messages.error(request, 'Esta reserva no puede hacer check-in.')
        return redirect('reservas_lista')

    import estancias.services as estancia_services
    from estancias.models import Estancia as EstanciaModel

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
            
            import json
            observaciones = reserva.observaciones or ""
            if "__JSON_PRODUCTOS_START__" in observaciones:
                try:
                    json_part = observaciones.split("__JSON_PRODUCTOS_START__")[1].split("__JSON_PRODUCTOS_END__")[0].strip()
                    productos_data = json.loads(json_part)
                    for item in productos_data:
                        estancia_services.registrar_consumo(
                            estancia_id=estancia.id,
                            concepto="",
                            monto=Decimal('0.00'),
                            tipo='OTRO',
                            usuario=request.user,
                            producto_id=int(item['id']),
                            cantidad=int(item['cantidad'])
                        )
                except Exception as ex:
                    pass

            messages.success(request, f'Check-in realizado. Estancia #{estancia.id} creada.')
            return redirect('folio', estancia_id=estancia.id)
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, 'message') else str(e))
            return redirect('reserva_checkin', reserva_id=reserva.id)

    from estancias.models import Estancia as EstanciaModel
    hab_con_estancia_ajena = EstanciaModel.objects.filter(
        estado=EstanciaModel.ACTIVA
    ).exclude(reserva=reserva).values_list('habitacion_id', flat=True)

    habitaciones_disponibles = list(
        Habitacion.objects.filter(estado=Habitacion.DISPONIBLE)
        .exclude(id__in=hab_con_estancia_ajena)
        .select_related('tipo', 'hotel')
        .order_by('numero')
    )
    if reserva.habitacion:
        ids_en_lista = [h.id for h in habitaciones_disponibles]
        if reserva.habitacion.id not in ids_en_lista:
            if reserva.habitacion.id not in hab_con_estancia_ajena:
                habitaciones_disponibles = [reserva.habitacion] + habitaciones_disponibles

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
    
    # Calcular deuda real total (folio + cargos pendientes de tardanza/early)
    deuda_real = folio.saldo_pendiente + cargo_tardanza
    
    from inventario.models import Producto
    productos = Producto.objects.filter(estado='ACTIVO', es_vendible=True)

    return render(request, 'estancias/folio.html', {
        'estancia': estancia,
        'folio': folio,
        'cargo_tardanza': cargo_tardanza,
        'minutos_tarde': minutos_tarde,
        'deuda_real': deuda_real,
        'productos_inventario': productos
    })


@login_required
def agregar_cargo(request, estancia_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    if request.method == 'POST':
        try:
            import estancias.services as estancia_services
            producto_id = request.POST.get('producto_id')
            if producto_id:
                cantidad = int(request.POST.get('cantidad', 1))
                estancia_services.registrar_consumo(
                    estancia_id=estancia_id,
                    concepto="",
                    monto=Decimal('0.00'),
                    tipo=request.POST.get('tipo', 'OTRO'),
                    usuario=request.user,
                    producto_id=int(producto_id),
                    cantidad=cantidad
                )
            else:
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
def agregar_cargo_tardanza(request, estancia_id):
    """Agrega automáticamente el cargo de salida tardía calculado al folio."""
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    if request.method == 'POST':
        estancia = get_object_or_404(Estancia, id=estancia_id)
        cargo_tardanza, minutos_tarde = calcular_cargo_salida_tardia(estancia)
        
        if cargo_tardanza > 0:
            try:
                CargoEstancia.objects.create(
                    estancia=estancia,
                    concepto=f'Salida Tardía ({minutos_tarde} min excedidos)',
                    monto=cargo_tardanza,
                    tipo='HABITACION'
                )
                messages.success(request, f'Cargo por salida tardía de S/. {cargo_tardanza} agregado al folio.')
            except Exception as e:
                messages.error(request, f'Error al agregar cargo: {str(e)}')
        else:
            messages.info(request, 'No se detectó salida tardía pendiente.')
    return redirect('folio', estancia_id=estancia_id)


@login_required
def eliminar_cargo_view(request, cargo_id):
    """Elimina un cargo adicional del folio y revierte el stock si corresponde."""
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    cargo = get_object_or_404(CargoEstancia, id=cargo_id)
    estancia_id = cargo.estancia_id

    if request.method == 'POST':
        try:
            # Permitir eliminar cargos de tardanza/early check-in si no tienen pagos aplicados
            es_cargo_tardanza = 'Salida Tardía' in cargo.concepto or 'Early Check-In' in cargo.concepto
            folio = getattr(cargo.estancia, 'folio', None)
            tiene_pagos = folio and folio.pagos.exists() if folio else False
            
            if es_cargo_tardanza and not tiene_pagos:
                cargo.delete()
                if folio:
                    folio.calcular_totales()
                messages.success(request, f'Cargo "{cargo.concepto}" eliminado correctamente.')
            else:
                import estancias.services as estancia_services
                estancia_services.eliminar_cargo(cargo_id=cargo_id, usuario=request.user)
                messages.success(request, f'Cargo "{cargo.concepto}" eliminado correctamente.')
        except Exception as e:
            messages.error(request, str(e))

    return redirect('folio', estancia_id=estancia_id)


@login_required
def editar_cargo_view(request, cargo_id):
    """Edita la cantidad de un cargo de producto en el folio, ajustando el stock."""
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)

    cargo = get_object_or_404(CargoEstancia, id=cargo_id)
    estancia_id = cargo.estancia_id

    if request.method == 'POST':
        try:
            nueva_cantidad = int(request.POST.get('cantidad', 1))
            import estancias.services as estancia_services
            estancia_services.editar_cargo(
                cargo_id=cargo_id,
                nueva_cantidad=nueva_cantidad,
                usuario=request.user
            )
            messages.success(request, 'Cargo actualizado correctamente.')
        except (ValueError, TypeError):
            messages.error(request, 'Cantidad inválida.')
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
                
                # Calcular deuda real incluyendo cargos pendientes de tardanza
                cargo_tardanza, _ = calcular_cargo_salida_tardia(estancia)
                deuda_real = folio.saldo_pendiente + cargo_tardanza
                
                if monto_decimal <= 0:
                    messages.error(request, 'El monto debe ser mayor a cero.')
                elif monto_decimal > deuda_real:
                    messages.error(request, f'El monto no puede ser mayor a la deuda real (S/. {deuda_real:.2f}). Incluye cargos pendientes.')
                elif metodo_pago != Pago.EFECTIVO and not transaccion_id:
                    messages.error(request, 'Debes ingresar el ID de transacción para pagos electrónicos/bancarios.')
                else:
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
def folio_imprimir(request, estancia_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    estancia = get_object_or_404(Estancia, id=estancia_id)
    folio, _ = Folio.objects.get_or_create(estancia=estancia)
    folio.calcular_totales()
    return render(request, 'estancias/imprimir_folio.html', {'estancia': estancia, 'folio': folio})


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
        from django.db import transaction
        monto_str = request.POST.get('monto')
        motivo = request.POST.get('motivo', '').strip()
        cancelar_estancia_problema = 'cancelar_estancia_problema' in request.POST
        estado_habitacion = request.POST.get('estado_habitacion', 'MANTENIMIENTO')
        
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
                
            with transaction.atomic():
                if cancelar_estancia_problema:
                    estancia = pago.folio.estancia if pago.folio else getattr(pago.reserva, 'estancia', None)
                    reserva = pago.reserva if pago.reserva else (estancia.reserva if estancia else None)
                    
                    if estancia and estancia.estado == Estancia.ACTIVA:
                        cargos = CargoEstancia.objects.filter(estancia=estancia)
                        for cargo in cargos:
                            cargo.exonerado = True
                            cargo.motivo_exoneracion = f"Cancelación por problema en la habitación: {motivo}"
                            cargo.exonerado_por = request.user
                            cargo.save()
                            
                            registrar_auditoria(
                                usuario=request.user,
                                accion="Cargo Exonerado (Problema de Hab.)",
                                registro_id=cargo.id,
                                tabla_afectada="estancias_cargoestancia",
                                estado_nuevo=f"ID: {cargo.id}, Concepto: {cargo.concepto}, Monto: S/. {cargo.monto} -> Exonerado por problema"
                            )
                        
                        folio = estancia.folio
                        folio.calcular_totales()
                        
                        estancia.estado = Estancia.FINALIZADA
                        estancia.fecha_checkout = timezone.now()
                        estancia.precio_final = Decimal('0.00')
                        estancia.save()
                        
                        folio.estado = Folio.CERRADO
                        folio.save()
                        
                        if reserva:
                            reserva.estado = Reserva.CANCELADA
                            reserva.motivo_cancelacion = f"Cancelada por problema en habitación ({estancia.habitacion.numero}): {motivo}"
                            reserva.save()
                            
                        habitacion = estancia.habitacion
                        habitacion.estado = estado_habitacion
                        habitacion.save()
                            
                        registrar_auditoria(
                            usuario=request.user,
                            accion="Cancelar Estancia (Problema de Hab.)",
                            registro_id=estancia.id,
                            tabla_afectada="estancias_estancia",
                            estado_nuevo=f"ID: {estancia.id}, Hab: {habitacion.numero} -> {estado_habitacion}, Reserva: {reserva.id if reserva else 'N/A'}"
                        )
                    elif reserva and reserva.estado in [Reserva.PENDIENTE, Reserva.CONFIRMADA]:
                        reserva.estado = Reserva.CANCELADA
                        reserva.motivo_cancelacion = f"Cancelada por problema en habitación antes de check-in: {motivo}"
                        reserva.save()
                        if reserva.habitacion:
                            reserva.habitacion.estado = Habitacion.DISPONIBLE
                            reserva.habitacion.save()
                    
                    reembolso = Reembolso.objects.create(
                        pago=pago,
                        monto=monto_decimal,
                        motivo=motivo,
                        estado=Reembolso.APROBADO,
                        solicitado_por=request.user,
                        aprobado_por=request.user,
                        fecha_resolucion=timezone.now(),
                        observacion=f"Aprobado automáticamente por cancelación de estancia debido a problemas de habitación: {motivo}"
                    )
                    
                    registrar_auditoria(
                        usuario=request.user,
                        accion="Resolver Reembolso",
                        registro_id=reembolso.id,
                        tabla_afectada="estancias_reembolso",
                        estado_nuevo=f"ID: {reembolso.id}, Estado: APROBADO (Aut. por Problema Hab.), Monto: S/. {monto_decimal}"
                    )
                    
                    messages.success(request, 'Estancia cancelada, cargos exonerados, habitación liberada y reembolso procesado correctamente.')
                else:
                    reembolso = Reembolso.objects.create(
                        pago=pago,
                        monto=monto_decimal,
                        motivo=motivo,
                        estado=Reembolso.SOLICITADO,
                        solicitado_por=request.user
                    )
                    
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
def cancelar_estancia_sin_pago(request, estancia_id):
    """
    Obs. 1 – Escenario 3: Cancela una estancia activa cuando NO existe pago anticipado.
    No genera ningún objeto Reembolso. Exonera cargos, finaliza estancia/reserva
    y cambia estado de la habitación a Mantenimiento o Limpieza.
    """
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    estancia = get_object_or_404(Estancia, id=estancia_id)

    if request.method == 'POST':
        motivo = request.POST.get('motivo', '').strip()
        estado_habitacion = request.POST.get('estado_habitacion_nopago', 'MANTENIMIENTO')

        if not motivo:
            messages.error(request, 'El motivo de la cancelación es obligatorio.')
            return redirect('folio', estancia_id=estancia_id)

        folio = getattr(estancia, 'folio', None)
        if folio and folio.total_pagado > 0:
            messages.error(
                request,
                'Esta estancia tiene pagos registrados. Use la opción "Solicitar Reembolso" para cancelarla.'
            )
            return redirect('folio', estancia_id=estancia_id)

        if estancia.estado != Estancia.ACTIVA:
            messages.error(request, 'Solo se pueden cancelar estancias activas.')
            return redirect('folio', estancia_id=estancia_id)

        try:
            from django.db import transaction
            with transaction.atomic():
                cargos = CargoEstancia.objects.filter(estancia=estancia)
                for cargo in cargos:
                    cargo.exonerado = True
                    cargo.motivo_exoneracion = f"Cancelación por problema de habitación (sin pago previo): {motivo}"
                    cargo.exonerado_por = request.user
                    cargo.save()
                    registrar_auditoria(
                        usuario=request.user,
                        accion="Cargo Exonerado (Cancelación Sin Pago)",
                        registro_id=cargo.id,
                        tabla_afectada="estancias_cargoestancia",
                        estado_nuevo=f"ID: {cargo.id}, {cargo.concepto} -> Exonerado (sin pago)"
                    )

                if folio:
                    folio.calcular_totales()
                    folio.estado = Folio.CERRADO
                    folio.save()

                estancia.estado = Estancia.FINALIZADA
                estancia.fecha_checkout = timezone.now()
                estancia.precio_final = Decimal('0.00')
                estancia.save()

                reserva = estancia.reserva
                if reserva:
                    reserva.estado = Reserva.CANCELADA
                    reserva.motivo_cancelacion = (
                        f"Cancelada por problema de habitación "
                        f"({estancia.habitacion.numero}) sin pago previo: {motivo}"
                    )
                    reserva.save()

                habitacion = estancia.habitacion
                habitacion.estado = estado_habitacion
                habitacion.save()

                registrar_auditoria(
                    usuario=request.user,
                    accion="Cancelar Estancia Sin Pago (Problema Hab.)",
                    registro_id=estancia.id,
                    tabla_afectada="estancias_estancia",
                    estado_nuevo=(
                        f"ID: {estancia.id}, Hab: {habitacion.numero} -> {estado_habitacion}, "
                        f"Reserva: {reserva.id if reserva else 'N/A'}, Sin reembolso"
                    )
                )

            messages.success(
                request,
                f'Estancia cancelada correctamente. Cargos exonerados. '
                f'Habitación {habitacion.numero} enviada a {habitacion.get_estado_display()}. '
                f'No se generó reembolso ya que no existía pago registrado.'
            )
        except Exception as e:
            messages.error(request, f'Error al cancelar la estancia: {str(e)}')

    return redirect('dashboard')


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
            from caja.services import obtener_caja_abierta, registrar_movimiento_reembolso
            caja = obtener_caja_abierta(request.user)
            if not caja:
                messages.error(request, 'No tienes una caja abierta. Debes abrir una caja para poder procesar reembolsos.')
                return redirect_url

            with transaction.atomic():
                reembolso.estado = Reembolso.APROBADO
                reembolso.aprobado_por = request.user
                reembolso.fecha_resolucion = timezone.now()
                reembolso.observacion = observacion
                reembolso.save()
                
                registrar_movimiento_reembolso(reembolso, request.user)

            pago = reembolso.pago
            estancia = pago.folio.estancia if pago.folio else None
            reserva = pago.reserva if pago.reserva else (estancia.reserva if estancia else None)
            
            if estancia and estancia.estado == Estancia.ACTIVA:
                folio = estancia.folio
                folio.calcular_totales()
                
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
        
        registrar_auditoria(
            usuario=request.user,
            accion="Resolver Reembolso",
            registro_id=reembolso.id,
            tabla_afectada="estancias_reembolso",
            estado_nuevo=f"ID: {reembolso.id}, Estado: {reembolso.estado}, Observacion: {observacion}"
        )
        
        messages.success(request, f'Reembolso #{reembolso.id} resuelto: {reembolso.get_estado_display()}.')
        
    return redirect_url


@login_required
def reembolsos_lista_admin(request):
    if not _es_admin(request.user):
        return _acceso_denegado(request, 'Solo los administradores pueden ver la lista de reembolsos.')
        
    from estancias.models import Reembolso
    reembolsos = Reembolso.objects.select_related('pago__folio__estancia__habitacion', 'pago__reserva__huesped', 'solicitado_por', 'aprobado_por').all().order_by('-fecha_solicitud')
    
    estado_q = request.GET.get('estado', '').strip()
    if estado_q:
        reembolsos = reembolsos.filter(estado=estado_q)
        
    return render(request, 'reportes/reembolsos.html', {
        'reembolsos': reembolsos,
        'f_estado': estado_q,
    })
