# Capa de Servicios Reutilizables de Estancias y Caja
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, time, timedelta

from hotel.models import Habitacion, Hotel
from reservas.models import Reserva
from estancias.models import Estancia, Folio, CargoEstancia, Pago, HistorialHabitacionEstancia
from reportes.models import registrar_auditoria
from config.roles import es_admin, es_recepcionista


def detectar_early_checkin(reserva, hotel, now_local):
    """
    Detecta si una reservación está intentando ingresar de manera anticipada
    con respecto a la hora de check-in estándar configurada.
    """
    hora_std = hotel.hora_checkin_estandar if (hotel and hasattr(hotel, 'hora_checkin_estandar')) else time(15, 0)
    dt_std = timezone.make_aware(datetime.combine(reserva.fecha_entrada, hora_std))

    if now_local < dt_std:
        tolerancia = timedelta(minutes=hotel.early_checkin_tolerancia_minutos or 30)
        if now_local < dt_std - tolerancia:
            monto_cargo = Decimal('0.00')
            if hotel.cobrar_early_checkin:
                if hotel.early_checkin_tipo_cargo == 'PORCENTAJE':
                    precio_base = reserva.habitacion.tipo.precio_base
                    monto_cargo = precio_base * (hotel.early_checkin_monto_porcentaje / Decimal('100.00'))
                else:
                    monto_cargo = hotel.early_checkin_monto_porcentaje
            return True, round(monto_cargo, 2)
    return False, Decimal('0.00')


def detectar_late_checkout(estancia, hotel, now_local):
    """
    Detecta si el check-out de una estancia activa excede el margen temporal del contrato.
    Retorna (es_late, cargo_estimado, minutos_retraso).
    """
    if not estancia.reserva.fecha_hora_salida:
        return False, Decimal('0.00'), 0

    dt_salida = estancia.reserva.fecha_hora_salida
    tolerancia = timedelta(minutes=hotel.late_checkout_tolerancia_minutos or 10)

    if now_local > dt_salida + tolerancia:
        minutos_retraso = int((now_local - dt_salida).total_seconds() // 60)
        cargo_tardanza = Decimal('0.00')
        if hotel.permitir_late_checkout:
            horas_bloque = hotel.late_checkout_horas_bloque or 3
            bloques = max(1, int(((minutos_retraso / 60) + (horas_bloque - 0.01)) // horas_bloque))

            monto_bloque = Decimal('0.00')
            if hotel.late_checkout_tipo_cargo == 'PORCENTAJE':
                precio_base = estancia.habitacion.tipo.precio_base
                monto_bloque = precio_base * hotel.late_checkout_monto_porcentaje
            else:
                monto_bloque = hotel.late_checkout_monto_porcentaje

            cargo_tardanza = monto_bloque * bloques
        return True, round(cargo_tardanza, 2), minutos_retraso
    return False, Decimal('0.00'), 0


def procesar_checkin(reserva_id, habitacion_id, usuario, exonerar_early=False, motivo_exoneracion_early=None, now_local_override=None):
    """
    Completa de manera transaccional e indexada el check-in (RN-HOS-001).
    """
    with transaction.atomic():
        reserva = Reserva.objects.select_for_update().get(id=reserva_id)
        if reserva.estado in [Reserva.CHECKIN, Reserva.CHECKOUT, Reserva.CANCELADA]:
            raise ValidationError(f"La reserva #{reserva.id} no está en estado válido para Check-In (Estado: {reserva.estado}).")

        # RN-HOS-004: El huésped debe tener documento de identidad registrado
        huesped = reserva.huesped
        if not huesped.num_doc or not huesped.num_doc.strip():
            raise ValidationError(
                f"El huésped '{huesped.nombres} {huesped.apellidos}' no tiene documento de identidad registrado. "
                "Es obligatorio contar con un documento válido para el ingreso (RN-HOS-004)."
            )

        # RN-HOS-005: Debe registrarse la cantidad de huéspedes (mínimo 1 adulto)
        if not reserva.num_adultos or reserva.num_adultos < 1:
            raise ValidationError(
                "La cantidad de huéspedes debe ser al menos 1 adulto (RN-HOS-005). "
                "Verifique los datos de la reserva."
            )

        # Habitación
        habitacion = Habitacion.objects.select_for_update().get(id=habitacion_id) if habitacion_id else reserva.habitacion
        if not habitacion:
            raise ValidationError("No se pre-asignó ni especificó ninguna habitación válida.")

        # Validamos que la habitación no esté físicamente OCUPADA (por otra reserva o estado manual)
        if habitacion.estado == Habitacion.OCUPADA:
            tiene_estancia_propia = Estancia.objects.filter(
                habitacion=habitacion, estado=Estancia.ACTIVA, reserva=reserva
            ).exists()
            if not tiene_estancia_propia:
                raise ValidationError(
                    f"La habitación #{habitacion.numero} está actualmente ocupada y no puede asignarse."
                )

        # Verificar también si hay estancia activa de OTRA reserva
        estancia_activa_ajena = Estancia.objects.filter(
            habitacion=habitacion, estado=Estancia.ACTIVA
        ).exclude(reserva=reserva).exists()
        if estancia_activa_ajena:
            raise ValidationError(f"La habitación #{habitacion.numero} ya tiene una estancia activa de otra reserva.")

        # Si la habitación está en limpieza o mantenimiento y NO es la propia de la reserva, bloquear.
        habitacion_propia = reserva.habitacion and reserva.habitacion.id == habitacion.id
        if habitacion.estado in [Habitacion.LIMPIEZA, Habitacion.MANTENIMIENTO] and not habitacion_propia:
            raise ValidationError(f"La habitación #{habitacion.numero} no se encuentra disponible (Estado: {habitacion.estado}).")

        # Capacidad física
        if reserva.num_adultos > habitacion.tipo.capacidad:
            raise ValidationError(f"La cantidad de pasajeros ({reserva.num_adultos}) supera la capacidad física ({habitacion.tipo.capacidad}).")

        hotel = habitacion.hotel
        now_local = now_local_override or timezone.localtime(timezone.now())

        # Check de Early Check-In
        es_early, early_monto = detectar_early_checkin(reserva, hotel, now_local)
        if es_early and not hotel.permitir_early_checkin:
            raise ValidationError("El ingreso temprano (Early Check-In) no está permitido en este establecimiento.")

        # Actualización de estados
        habitacion.estado = Habitacion.OCUPADA
        habitacion.save()

        reserva.habitacion = habitacion
        reserva.estado = Reserva.CHECKIN
        reserva.save()

        # Creación estancia y folio
        estancia = Estancia.objects.create(
            reserva=reserva,
            habitacion=habitacion,
            precio_final=reserva.precio_total,
            registrado_por=usuario
        )
        folio = Folio.objects.create(estancia=estancia, estado=Folio.ABIERTO)

        # Cargar precio base de alquiler de habitación
        if reserva.precio_total > 0:
            if reserva.modalidad == Reserva.POR_HORA:
                noches_cant = int(reserva.duracion_horas or 3)
                concepto_alquiler = f"Alquiler por horas – Hab. {habitacion.numero} ({noches_cant}h)"
            else:
                noches_cant = (reserva.fecha_salida - reserva.fecha_entrada).days or 1
                concepto_alquiler = f"Alquiler por {noches_cant} noche{'s' if noches_cant != 1 else ''} – Hab. {habitacion.numero}"

            CargoEstancia.objects.create(
                estancia=estancia,
                concepto=concepto_alquiler,
                monto=reserva.precio_total,
                tipo=CargoEstancia.HABITACION
            )

        # Traspaso de anticipos
        Pago.objects.filter(reserva=reserva, folio__isnull=True).update(folio=folio)

        # Registro de cargo Early Check-In si aplica
        if es_early and early_monto > 0:
            cargo_early = CargoEstancia.objects.create(
                estancia=estancia,
                concepto="Recargo por Early Check-In",
                monto=early_monto,
                tipo=CargoEstancia.HABITACION
            )
            if exonerar_early:
                rol_permitido = hotel.early_checkin_rol_exonerar or 'administrador'
                if rol_permitido == 'administrador' and not es_admin(usuario):
                    raise ValidationError("Rol no autorizado para exonerar recargo por Early Check-In.")
                if not motivo_exoneracion_early:
                    raise ValidationError("El motivo de la exoneración es obligatorio.")
                
                cargo_early.exonerado = True
                cargo_early.motivo_exoneracion = motivo_exoneracion_early
                cargo_early.exonerado_por = usuario
                cargo_early.save()

                # Auditoría de la exoneración
                registrar_auditoria(
                    usuario=usuario,
                    accion="CARGO_EXONERADO",
                    registro_id=cargo_early.id,
                    tabla_afectada="estancias_cargoestancia",
                    observacion=f"Exonerado Early Check-in. Motivo: {motivo_exoneracion_early}. Monto perdonado: S/.{early_monto}"
                )

        folio.calcular_totales()

        # Registro de bitácora una sola vez
        registrar_auditoria(
            usuario=usuario,
            accion="Check-In Realizado",
            registro_id=estancia.id,
            tabla_afectada="estancias_estancia",
            estado_nuevo=f"Estancia ACTIVA en Hab. {habitacion.numero}"
        )

        return estancia


def procesar_checkout(estancia_id, usuario, exonerar_late_checkout=False, motivo_exoneracion_late=None, now_local_override=None):
    """
    Completa de manera transaccional e indexada el check-out de la estancia (RN-HOS-041).
    """
    with transaction.atomic():
        estancia = Estancia.objects.select_for_update().get(id=estancia_id)
        if estancia.estado == Estancia.FINALIZADA:
            return estancia

        hotel = estancia.habitacion.hotel
        now_local = now_local_override or timezone.localtime(timezone.now())

        # Check de Late Check-Out
        es_late, late_monto, minutos_tarde = detectar_late_checkout(estancia, hotel, now_local)
        if es_late and not hotel.permitir_late_checkout:
            raise ValidationError("El hotel no permite Late Check-Out en este momento. La salida excede la hora estándar.")
        
        # Cargo de Late Checkout si aplica
        if es_late and late_monto > 0:
            cargo_late_existente = estancia.cargos.filter(concepto__icontains="Salida Tardía").first()
            if not cargo_late_existente:
                cargo_late = CargoEstancia.objects.create(
                    estancia=estancia,
                    concepto=f"Recargo por Salida Tardía ({minutos_tarde} min de desfase)",
                    monto=late_monto,
                    tipo=CargoEstancia.HABITACION
                )
                if exonerar_late_checkout:
                    rol_permitido = hotel.late_checkout_rol_exonerar or 'administrador'
                    if rol_permitido == 'administrador' and not es_admin(usuario):
                        raise ValidationError("Rol no autorizado para exonerar recargo por Late Check-Out.")
                    if not motivo_exoneracion_late:
                        raise ValidationError("El motivo de la exoneración es obligatorio.")

                    cargo_late.exonerado = True
                    cargo_late.motivo_exoneracion = motivo_exoneracion_late
                    cargo_late.exonerado_por = usuario
                    cargo_late.save()

                    # Auditoría de la exoneración
                    registrar_auditoria(
                        usuario=usuario,
                        accion="CARGO_EXONERADO",
                        registro_id=cargo_late.id,
                        tabla_afectada="estancias_cargoestancia",
                        observacion=f"Exonerado Late Check-out. Motivo: {motivo_exoneracion_late}. Monto perdonado: S/.{late_monto}"
                    )

        folio = getattr(estancia, 'folio', None)
        if folio:
            folio.calcular_totales()
            if folio.saldo_pendiente > 0:
                raise ValidationError(f"No se puede hacer checkout: el folio tiene saldo pendiente de S/.{folio.saldo_pendiente}.")
            folio.estado = Folio.CERRADO
            folio.save()

        # Liberamos habitación
        habitacion = estancia.habitacion
        habitacion.estado = Habitacion.LIMPIEZA
        habitacion.save()

        estancia.fecha_checkout = now_local
        estancia.estado = Estancia.FINALIZADA
        estancia.save()

        reserva = estancia.reserva
        reserva.estado = Reserva.CHECKOUT
        reserva.save()

        # Registro único de bitácora
        registrar_auditoria(
            usuario=usuario,
            accion="Check-Out Realizado",
            registro_id=estancia.id,
            tabla_afectada="estancias_estancia",
            estado_anterior=f"ACTIVA Hab. {habitacion.numero}",
            estado_nuevo="FINALIZADA"
        )
        return estancia


def registrar_consumo(estancia_id, concepto, monto, tipo, usuario, producto_id=None, cantidad=1):
    """
    Registra consumos en un folio activo (RN-HOS-031), integrando control de inventario (EPIC 10).
    """
    from inventario.models import Producto, MovimientoInventario

    if monto <= 0 and producto_id is None:
        raise ValidationError("El monto del cargo debe ser mayor a cero.")
    if cantidad <= 0:
        raise ValidationError("La cantidad del producto debe ser mayor a cero.")

    with transaction.atomic():
        estancia = Estancia.objects.select_for_update().get(id=estancia_id)
        if estancia.estado != Estancia.ACTIVA:
            raise ValidationError("No se pueden registrar cargos en una estancia que no esté abierta (ACTIVA).")

        producto = None
        if producto_id:
            producto = Producto.objects.select_for_update().get(id=producto_id)
            if producto.estado != 'ACTIVO':
                raise ValidationError("El producto seleccionado está inactivo.")
            if not producto.es_vendible:
                raise ValidationError("El producto seleccionado no está habilitado para la venta.")
            
            # Si controla stock y no hay suficiente
            if producto.controla_stock:
                if producto.stock_actual < cantidad:
                    raise ValidationError(f"Stock insuficiente para {producto.nombre}. Disponible: {producto.stock_actual:.0f}")
                
                # Descontar stock
                existencia_anterior = producto.stock_actual
                producto.stock_actual -= Decimal(str(cantidad))
                producto.save()
                
                # Registrar movimiento
                MovimientoInventario.objects.create(
                    producto=producto,
                    tipo_movimiento='CONSUMO',
                    cantidad=Decimal(str(cantidad)),
                    existencia_anterior=existencia_anterior,
                    existencia_posterior=producto.stock_actual,
                    motivo=f"Consumo en Estancia #{estancia.id}",
                    costo_referencial=producto.costo_referencial,
                    usuario=usuario,
                    estancia=estancia,
                    documento_referencia=f"Estancia #{estancia.id}"
                )
            
            # Concepto y monto automáticos
            concepto = f"{producto.nombre} x {cantidad}"
            monto = producto.precio_venta * Decimal(str(cantidad))

        cargo = CargoEstancia.objects.create(
            estancia=estancia,
            concepto=concepto,
            monto=monto,
            tipo=tipo,
            producto=producto,
            cantidad=cantidad
        )
        
        folio = estancia.folio
        folio.calcular_totales()

        registrar_auditoria(
            usuario=usuario,
            accion="Cargo Registrado",
            registro_id=cargo.id,
            tabla_afectada="estancias_cargoestancia",
            estado_nuevo=f"Cargo: {concepto} S/.{monto}"
        )
        return cargo


def exonerar_cargo_servicio(cargo_id, motivo, devolver_a_stock, usuario):
    """
    Exonera un cargo y opcionalmente devuelve el producto al inventario (RN-INV-070 a RN-INV-075).
    """
    from inventario.models import MovimientoInventario

    if not motivo or not motivo.strip():
        raise ValidationError("Debe proporcionar un motivo para la exoneración.")

    with transaction.atomic():
        cargo = CargoEstancia.objects.select_for_update().get(id=cargo_id)
        if cargo.exonerado:
            raise ValidationError("El cargo ya se encuentra exonerado.")

        # Marcar como exonerado
        cargo.exonerado = True
        cargo.motivo_exoneracion = motivo
        cargo.exonerado_por = usuario
        cargo.save()

        # Recalcular totales del folio
        folio = cargo.estancia.folio
        folio.calcular_totales()

        # Si hay producto y se autoriza devolución al stock
        if cargo.producto and devolver_a_stock:
            producto = cargo.producto
            if producto.controla_stock:
                existencia_anterior = producto.stock_actual
                producto.stock_actual += Decimal(str(cargo.cantidad))
                producto.save()

                # Registrar movimiento de devolución/anulación
                MovimientoInventario.objects.create(
                    producto=producto,
                    tipo_movimiento='ANULACION',
                    cantidad=Decimal(str(cargo.cantidad)),
                    existencia_anterior=existencia_anterior,
                    existencia_posterior=producto.stock_actual,
                    motivo=f"Anulación de cargo #{cargo.id}: {motivo}",
                    costo_referencial=producto.costo_referencial,
                    usuario=usuario,
                    estancia=cargo.estancia,
                    documento_referencia=f"Cargo #{cargo.id}"
                )

        registrar_auditoria(
            usuario=usuario,
            accion="Cargo Exonerado",
            registro_id=cargo.id,
            tabla_afectada="estancias_cargoestancia",
            estado_nuevo=f"Cargo #{cargo.id} exonerado. Devuelve stock: {devolver_a_stock}"
        )
        return cargo


def eliminar_cargo(cargo_id, usuario):
    """
    Elimina un cargo adicional de una estancia activa y devuelve el stock al inventario si aplica.
    No permite eliminar cargos de tipo HABITACION (alojamiento base).
    """
    from inventario.models import MovimientoInventario

    with transaction.atomic():
        cargo = CargoEstancia.objects.select_for_update().get(id=cargo_id)
        estancia = cargo.estancia

        if estancia.estado != Estancia.ACTIVA:
            raise ValidationError("No se pueden modificar cargos de una estancia que no esté activa.")
        if cargo.tipo == CargoEstancia.HABITACION:
            raise ValidationError("No se puede eliminar el cargo de alojamiento base.")

        # Revertir stock si el cargo tiene producto con control de stock
        if cargo.producto and cargo.producto.controla_stock:
            producto = cargo.producto
            existencia_anterior = producto.stock_actual
            producto.stock_actual += Decimal(str(cargo.cantidad))
            producto.save()

            MovimientoInventario.objects.create(
                producto=producto,
                tipo_movimiento='ANULACION',
                cantidad=Decimal(str(cargo.cantidad)),
                existencia_anterior=existencia_anterior,
                existencia_posterior=producto.stock_actual,
                motivo=f"Eliminación de cargo #{cargo.id} en Estancia #{estancia.id}",
                costo_referencial=producto.costo_referencial,
                usuario=usuario,
                estancia=estancia,
                documento_referencia=f"Cargo #{cargo.id}"
            )

        registrar_auditoria(
            usuario=usuario,
            accion="Cargo Eliminado",
            registro_id=cargo.id,
            tabla_afectada="estancias_cargoestancia",
            estado_nuevo=f"Cargo #{cargo.id} '{cargo.concepto}' S/.{cargo.monto} eliminado de Estancia #{estancia.id}"
        )

        cargo.delete()

        folio = estancia.folio
        folio.calcular_totales()


def editar_cargo(cargo_id, nueva_cantidad, usuario):
    """
    Edita la cantidad de un cargo de producto en una estancia activa.
    Ajusta el stock del inventario sumando o descontando la diferencia.
    Solo aplica a cargos que tienen un producto de inventario asociado.
    """
    from inventario.models import MovimientoInventario

    with transaction.atomic():
        cargo = CargoEstancia.objects.select_for_update().get(id=cargo_id)
        estancia = cargo.estancia

        if estancia.estado != Estancia.ACTIVA:
            raise ValidationError("No se pueden modificar cargos de una estancia que no esté activa.")
        if cargo.tipo == CargoEstancia.HABITACION:
            raise ValidationError("No se puede editar el cargo de alojamiento base.")
        if nueva_cantidad <= 0:
            raise ValidationError("La cantidad debe ser mayor a cero. Para eliminar usa el botón de eliminación.")

        if cargo.producto:
            producto = cargo.producto
            cantidad_anterior = cargo.cantidad
            diferencia = nueva_cantidad - cantidad_anterior  # positivo = más, negativo = devuelve

            if diferencia > 0 and producto.controla_stock:
                if producto.stock_actual < diferencia:
                    raise ValidationError(
                        f"Stock insuficiente para {producto.nombre}. Disponible: {producto.stock_actual:.0f}"
                    )

            if producto.controla_stock and diferencia != 0:
                existencia_anterior = producto.stock_actual
                producto.stock_actual -= Decimal(str(diferencia))  # descuenta si positivo, suma si negativo
                producto.save()

                tipo_mov = 'CONSUMO' if diferencia > 0 else 'ANULACION'
                MovimientoInventario.objects.create(
                    producto=producto,
                    tipo_movimiento=tipo_mov,
                    cantidad=abs(Decimal(str(diferencia))),
                    existencia_anterior=existencia_anterior,
                    existencia_posterior=producto.stock_actual,
                    motivo=f"Ajuste de cantidad en cargo #{cargo.id}: {cantidad_anterior}→{nueva_cantidad}",
                    costo_referencial=producto.costo_referencial,
                    usuario=usuario,
                    estancia=estancia,
                    documento_referencia=f"Cargo #{cargo.id}"
                )

            cargo.cantidad = nueva_cantidad
            cargo.concepto = f"{producto.nombre} x {nueva_cantidad}"
            cargo.monto = producto.precio_venta * Decimal(str(nueva_cantidad))
        else:
            # Cargo libre: solo actualizar cantidad y monto proporcional no aplica, solo guardamos la cantidad
            cargo.cantidad = nueva_cantidad

        cargo.save()

        folio = estancia.folio
        folio.calcular_totales()

        registrar_auditoria(
            usuario=usuario,
            accion="Cargo Editado",
            registro_id=cargo.id,
            tabla_afectada="estancias_cargoestancia",
            estado_nuevo=f"Cargo #{cargo.id} '{cargo.concepto}' S/.{cargo.monto}"
        )
        return cargo


def extender_estancia_activa(estancia_id, nueva_fecha_salida, usuario):
    """
    Extiende la estancia del huésped (RN-HOS-008). 
    """
    with transaction.atomic():
        estancia = Estancia.objects.select_for_update().get(id=estancia_id)
        if estancia.estado != Estancia.ACTIVA:
            raise ValidationError("La estancia debe estar activa para poder extenderse.")

        original_salida = estancia.reserva.fecha_salida
        if nueva_fecha_salida <= original_salida:
            raise ValidationError("La nueva fecha de salida debe ser posterior a la fecha de salida actual.")

        # Verificar disponibilidad física sin solaparse
        solapadas = Reserva.objects.filter(
            habitacion=estancia.habitacion,
            estado__in=[Reserva.PENDIENTE, Reserva.CONFIRMADA, Reserva.CHECKIN]
        ).exclude(pk=estancia.reserva.pk)
        
        # Validar solapamiento directo
        solapadas = solapadas.filter(
            fecha_entrada__lt=nueva_fecha_salida,
            fecha_salida__gt=original_salida
        )

        if solapadas.exists():
            raise ValidationError(f"No se puede extender: la habitación #{estancia.habitacion.numero} está reservada en ese lapso de tiempo.")

        # Calcular diferencia tarifaria
        noches_extras = (nueva_fecha_salida - original_salida).days
        if noches_extras > 0:
            precio_noche = estancia.habitacion.tipo.precio_base
            total_adicional = precio_noche * noches_extras
            
            # Registrar cargo adicional por extensión
            cargo = CargoEstancia.objects.create(
                estancia=estancia,
                concepto=f"Cargo por Extensión de Estadía ({noches_extras} noche{'s' if noches_extras != 1 else ''} adicional(es))",
                monto=total_adicional,
                tipo=CargoEstancia.HABITACION
            )
            
            # Modificar la fecha de la reservación de respaldo
            reserva = estancia.reserva
            reserva.fecha_salida = nueva_fecha_salida
            if reserva.fecha_hora_salida:
                reserva.fecha_hora_salida = timezone.make_aware(
                    datetime.combine(nueva_fecha_salida, reserva.fecha_hora_salida.time())
                )
            reserva.precio_total += total_adicional
            reserva.save()

            estancia.folio.calcular_totales()

            registrar_auditoria(
                usuario=usuario,
                accion="Estancia Extendida",
                registro_id=estancia.id,
                tabla_afectada="estancias_estancia",
                observacion=f"Extendido check-out de {original_salida} a {nueva_fecha_salida}. Cargo extra: S/.{total_adicional}"
            )
            return cargo
    return None


def cambiar_habitacion_activo(estancia_id, nueva_habitacion_id, motivo, usuario):
    """
    Procesa un traslado de habitación conservando el folio del huésped (RN-HOS-006).
    """
    if not motivo:
        raise ValidationError("El motivo del cambio de habitación es de obligado registro.")

    with transaction.atomic():
        estancia = Estancia.objects.select_for_update().get(id=estancia_id)
        if estancia.estado != Estancia.ACTIVA:
            raise ValidationError("La estancia debe encontrarse activa para gestionar un traslado.")

        anterior_habitacion = estancia.habitacion
        if anterior_habitacion.id == int(nueva_habitacion_id):
            raise ValidationError("La habitación seleccionada es la misma habitación actual.")

        nueva_habitacion = Habitacion.objects.select_for_update().get(id=nueva_habitacion_id)

        # Disponibilidad
        if Estancia.objects.filter(habitacion=nueva_habitacion, estado=Estancia.ACTIVA).exists() or nueva_habitacion.estado != Habitacion.DISPONIBLE:
            raise ValidationError(f"La habitación destino #{nueva_habitacion.numero} no se encuentra disponible.")

        # Liberamos la habitación previa mandándola a limpieza
        anterior_habitacion.estado = Habitacion.LIMPIEZA
        anterior_habitacion.save()

        # Ocupamos la nueva habitación
        nueva_habitacion.estado = Habitacion.OCUPADA
        nueva_habitacion.save()

        # Diferencia tarifaria
        noches_restantes = (estancia.reserva.fecha_salida - timezone.localdate()).days
        if noches_restantes <= 0:
            noches_restantes = 1

        diferencia_base = nueva_habitacion.tipo.precio_base - anterior_habitacion.tipo.precio_base
        diferencia_total = diferencia_base * noches_restantes

        if diferencia_total > 0:
            # Creamos el cargo por upgrade
            CargoEstancia.objects.create(
                estancia=estancia,
                concepto=f"Ajuste Tarifario Cambio de Habitación (upgrade #{anterior_habitacion.numero} -> #{nueva_habitacion.numero})",
                monto=diferencia_total,
                tipo=CargoEstancia.HABITACION
            )

        # Bitácora histórica
        HistorialHabitacionEstancia.objects.create(
            estancia=estancia,
            habitacion_anterior=anterior_habitacion,
            habitacion_nueva=nueva_habitacion,
            motivo=motivo,
            usuario=usuario,
            diferencia_tarifaria=max(Decimal('0.00'), diferencia_total)
        )

        # Modificación de punteros y folio
        estancia.habitacion = nueva_habitacion
        estancia.save()

        reserva = estancia.reserva
        reserva.habitacion = nueva_habitacion
        reserva.save()

        estancia.folio.calcular_totales()

        # Registro único de auditoría
        registrar_auditoria(
            usuario=usuario,
            accion="Cambio de Habitación Realizado",
            registro_id=estancia.id,
            tabla_afectada="estancias_estancia",
            observacion=f"Traslado Hab. {anterior_habitacion.numero} -> {nueva_habitacion.numero}. Motivo: {motivo}. Dif: S/.{diferencia_total}"
        )
        return estancia


def registrar_pago_folio(folio_id, monto, metodo, transaccion_id, usuario):
    """
    Registra pagos recibidos para liquidar el folio (RN-HOS-031).
    """
    if monto <= 0:
        raise ValidationError("El importe del pago debe ser mayor a cero.")

    from caja.services import obtener_caja_abierta, registrar_movimiento_pago
    caja = obtener_caja_abierta(usuario)
    if not caja:
        raise ValidationError(
            "No tienes una caja abierta. Es obligatorio aperturar tu caja "
            "antes de registrar cualquier operación de pago (RN-CAJ-012)."
        )

    with transaction.atomic():
        folio = Folio.objects.select_for_update().get(id=folio_id)
        if folio.saldo_pendiente <= 0:
            raise ValidationError("El folio ya se encuentra completamente liquidado (saldo pendiente 0.00).")

        vuelto = Decimal('0.00')
        if monto > folio.saldo_pendiente:
            vuelto = monto - folio.saldo_pendiente
            monto = folio.saldo_pendiente

        pago = Pago.objects.create(
            folio=folio,
            monto=monto,
            metodo_pago=metodo,
            transaccion_id=transaccion_id
        )
        folio.calcular_totales()

        # Registrar el movimiento en la caja del turno
        registrar_movimiento_pago(pago, usuario)

        # Bitácora
        obs_extra = f" (Vuelto de S/.{vuelto} entregado)" if vuelto > 0 else ""
        registrar_auditoria(
            usuario=usuario,
            accion="Pago Registrado",
            registro_id=pago.id,
            tabla_afectada="estancias_pago",
            observacion=f"Abono S/.{monto} (Método: {pago.get_metodo_pago_display()}) al Folio #{folio.id}{obs_extra}"
        )
        return pago


def hospedaje_directo_walkin(hotel_id, huesped_id, habitacion_id, fecha_salida, num_adultos, usuario):
    """
    Flujo atómico e indexado de Walk-in (HOT-HOS-001).
    """
    with transaction.atomic():
        hotel = Hotel.objects.get(id=hotel_id)
        habitacion = Habitacion.objects.select_for_update().get(id=habitacion_id)

        # Crear reserva express directa
        reserva = Reserva.objects.create(
            hotel=hotel,
            huesped_id=huesped_id,
            habitacion=habitacion,
            fecha_entrada=timezone.localdate(),
            fecha_salida=fecha_salida,
            num_adultos=num_adultos,
            modalidad=Reserva.POR_DIA,
            estado=Reserva.PENDIENTE,
            origen=Reserva.DIRECTO,
            observaciones="Hospedaje Directo (Walk-In) Express"
        )
        
        # Calcular el precio total
        noches = (fecha_salida - timezone.localdate()).days or 1
        reserva.precio_total = noches * habitacion.tipo.precio_base
        reserva.save()

        # Completar check-in vinculando transacciones
        estancia = procesar_checkin(
            reserva_id=reserva.id,
            habitacion_id=habitacion.id,
            usuario=usuario
        )
        return estancia
