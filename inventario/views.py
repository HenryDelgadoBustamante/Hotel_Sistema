from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum, F
from django.utils import timezone
from decimal import Decimal

from config.roles import es_admin, es_recepcionista, es_housekeeping, pertenece_a_grupo
from reportes.models import registrar_auditoria
from .models import CategoriaProducto, UnidadMedida, Proveedor, Producto, MovimientoInventario, ConteoFisico, DetalleConteoFisico

def _es_inventario(user):
    return es_admin(user) or pertenece_a_grupo(user, 'inventario')

def _es_gerente(user):
    return es_admin(user) or pertenece_a_grupo(user, 'gerente')

def _denegar_acceso(request, msg="No tiene permisos para acceder a esta sección."):
    return render(request, '403.html', {'mensaje_error': msg}, status=403)

@login_required
def inventario_dashboard(request):
    if not (es_recepcionista(request.user) or es_housekeeping(request.user) or _es_inventario(request.user)):
        return _denegar_acceso(request)

    # Filtros
    query = request.GET.get('q', '').strip()
    categoria_id = request.GET.get('categoria', '')
    disponibilidad = request.GET.get('disponibilidad', '')
    es_vendible = request.GET.get('es_vendible', '')
    es_uso_interno = request.GET.get('es_uso_interno', '')

    productos = Producto.objects.select_related('categoria', 'unidad_medida').all()

    if query:
        productos = productos.filter(Q(nombre__icontains=query) | Q(codigo_interno__icontains=query))
    if categoria_id:
        productos = productos.filter(categoria_id=categoria_id)
    if es_vendible == '1':
        productos = productos.filter(es_vendible=True)
    if es_uso_interno == '1':
        productos = productos.filter(es_uso_interno=True)

    # Filtrar por disponibilidad
    if disponibilidad:
        # Se calcula en memoria o mediante anotaciones. Haremos filtrado en base al stock_actual y stock_minimo
        if disponibilidad == 'SIN_STOCK':
            productos = productos.filter(controla_stock=True, stock_actual__lte=0)
        elif disponibilidad == 'STOCK_BAJO':
            productos = productos.filter(controla_stock=True, stock_actual__gt=0, stock_actual__lte=F('stock_minimo'))
        elif disponibilidad == 'DISPONIBLE':
            productos = productos.filter(Q(controla_stock=False) | Q(stock_actual__gt=F('stock_minimo')))

    # KPIs
    kpi_total = Producto.objects.filter(estado='ACTIVO').count()
    kpi_bajo = Producto.objects.filter(estado='ACTIVO', controla_stock=True, stock_actual__gt=0, stock_actual__lte=F('stock_minimo')).count()
    kpi_sin_stock = Producto.objects.filter(estado='ACTIVO', controla_stock=True, stock_actual__lte=0).count()

    categorias = CategoriaProducto.objects.filter(estado='ACTIVO')
    unidades = UnidadMedida.objects.all()

    # Si es recepcionista y no administrador, ocultar productos de uso interno no vendibles
    if es_recepcionista(request.user) and not es_admin(request.user):
        productos = productos.filter(es_vendible=True)

    # Si es housekeeping, mostrar productos de uso interno
    if es_housekeeping(request.user) and not es_admin(request.user):
        productos = productos.filter(es_uso_interno=True)

    return render(request, 'inventario/dashboard.html', {
        'productos': productos,
        'categorias': categorias,
        'unidades': unidades,
        'kpi_total': kpi_total,
        'kpi_bajo': kpi_bajo,
        'kpi_sin_stock': kpi_sin_stock,
        'q': query,
        'categoria_id': int(categoria_id) if categoria_id else '',
        'disponibilidad': disponibilidad,
        'es_vendible': es_vendible,
        'es_uso_interno': es_uso_interno,
        'es_admin_or_inv': _es_inventario(request.user)
    })


@login_required
def producto_crear(request):
    if not es_admin(request.user):
        return _denegar_acceso(request)

    if request.method == 'POST':
        codigo = request.POST.get('codigo_interno', '').strip()
        nombre = request.POST.get('nombre', '').strip()
        desc = request.POST.get('descripcion', '').strip()
        cat_id = request.POST.get('categoria')
        tipo_elem = request.POST.get('tipo_elemento')
        um_id = request.POST.get('unidad_medida')
        precio_v = Decimal(request.POST.get('precio_venta', '0'))
        costo_r = Decimal(request.POST.get('costo_referencial', '0'))
        controla = request.POST.get('controla_stock') == 'on'
        stock_act = Decimal(request.POST.get('stock_actual', '0'))
        stock_min = Decimal(request.POST.get('stock_minimo', '0'))
        es_vend = request.POST.get('es_vendible') == 'on'
        es_int = request.POST.get('es_uso_interno') == 'on'
        obs = request.POST.get('observaciones', '').strip()

        try:
            with transaction.atomic():
                producto = Producto.objects.create(
                    codigo_interno=codigo,
                    nombre=nombre,
                    descripcion=desc,
                    categoria_id=cat_id,
                    tipo_elemento=tipo_elem,
                    unidad_medida_id=um_id,
                    precio_venta=precio_v,
                    costo_referencial=costo_r,
                    controla_stock=controla,
                    stock_actual=stock_act,
                    stock_minimo=stock_min,
                    es_vendible=es_vend,
                    es_uso_interno=es_int,
                    observaciones=obs,
                    estado='ACTIVO'
                )
                registrar_auditoria(
                    usuario=request.user,
                    accion="Producto Creado",
                    registro_id=producto.id,
                    tabla_afectada="inventario_producto",
                    estado_nuevo=f"Código: {codigo}, Nombre: {nombre}"
                )
                messages.success(request, f"Producto {nombre} creado correctamente.")
                return redirect('inventario_dashboard')
        except Exception as e:
            messages.error(request, f"Error al crear producto: {str(e)}")

    categorias = CategoriaProducto.objects.filter(estado='ACTIVO')
    unidades = UnidadMedida.objects.all()
    return render(request, 'inventario/producto_form.html', {
        'categorias': categorias,
        'unidades': unidades,
        'titulo': 'Nuevo Producto/Servicio'
    })


@login_required
def producto_editar(request, pk):
    if not es_admin(request.user):
        return _denegar_acceso(request)

    producto = get_object_or_404(Producto, id=pk)

    if request.method == 'POST':
        producto.codigo_interno = request.POST.get('codigo_interno', '').strip()
        producto.nombre = request.POST.get('nombre', '').strip()
        producto.descripcion = request.POST.get('descripcion', '').strip()
        producto.categoria_id = request.POST.get('categoria')
        producto.tipo_elemento = request.POST.get('tipo_elemento')
        producto.unidad_medida_id = request.POST.get('unidad_medida')
        producto.precio_venta = Decimal(request.POST.get('precio_venta', '0'))
        producto.costo_referencial = Decimal(request.POST.get('costo_referencial', '0'))
        producto.controla_stock = request.POST.get('controla_stock') == 'on'
        producto.stock_actual = Decimal(request.POST.get('stock_actual', '0'))
        producto.stock_minimo = Decimal(request.POST.get('stock_minimo', '0'))
        producto.es_vendible = request.POST.get('es_vendible') == 'on'
        producto.es_uso_interno = request.POST.get('es_uso_interno') == 'on'
        producto.observaciones = request.POST.get('observaciones', '').strip()
        producto.estado = request.POST.get('estado', 'ACTIVO')

        try:
            with transaction.atomic():
                producto.save()
                registrar_auditoria(
                    usuario=request.user,
                    accion="Producto Modificado",
                    registro_id=producto.id,
                    tabla_afectada="inventario_producto",
                    estado_nuevo=f"Código: {producto.codigo_interno}, Nombre: {producto.nombre}, Estado: {producto.estado}"
                )
                messages.success(request, f"Producto {producto.nombre} actualizado correctamente.")
                return redirect('inventario_dashboard')
        except Exception as e:
            messages.error(request, f"Error al actualizar producto: {str(e)}")

    categorias = CategoriaProducto.objects.filter(estado='ACTIVO')
    unidades = UnidadMedida.objects.all()
    return render(request, 'inventario/producto_form.html', {
        'producto': producto,
        'categorias': categorias,
        'unidades': unidades,
        'titulo': f"Editar Producto: {producto.nombre}"
    })


@login_required
def registrar_movimiento(request):
    if not _es_inventario(request.user):
        return _denegar_acceso(request)

    if request.method == 'POST':
        producto_id = request.POST.get('producto')
        tipo_mov = request.POST.get('tipo_movimiento')
        cantidad = Decimal(request.POST.get('cantidad', '0'))
        motivo = request.POST.get('motivo', '').strip()
        proveedor_id = request.POST.get('proveedor') or None
        costo_ref = Decimal(request.POST.get('costo_referencial', '0'))
        doc_ref = request.POST.get('documento_referencia', '').strip()
        obs = request.POST.get('observacion', '').strip()

        if cantidad <= 0:
            messages.error(request, "La cantidad del movimiento debe ser mayor a cero.")
            return redirect('registrar_movimiento')

        try:
            with transaction.atomic():
                producto = Producto.objects.select_for_update().get(id=producto_id)
                
                if not producto.controla_stock:
                    raise ValidationError("Solo se pueden registrar movimientos de stock para productos físicos.")

                existencia_anterior = producto.stock_actual

                if tipo_mov == 'ENTRADA':
                    producto.stock_actual += cantidad
                elif tipo_mov == 'SALIDA':
                    if producto.stock_actual < cantidad:
                        raise ValidationError(f"Stock insuficiente. Disponible: {producto.stock_actual:.0f}")
                    producto.stock_actual -= cantidad
                else:
                    raise ValidationError("Tipo de movimiento manual no válido.")

                producto.save()

                mov = MovimientoInventario.objects.create(
                    producto=producto,
                    tipo_movimiento=tipo_mov,
                    cantidad=cantidad,
                    existencia_anterior=existencia_anterior,
                    existencia_posterior=producto.stock_actual,
                    motivo=motivo,
                    proveedor_id=proveedor_id,
                    costo_referencial=costo_ref if costo_ref else producto.costo_referencial,
                    documento_referencia=doc_ref,
                    usuario=request.user,
                    observacion=obs
                )

                registrar_auditoria(
                    usuario=request.user,
                    accion=f"Movimiento {tipo_mov}",
                    registro_id=mov.id,
                    tabla_afectada="inventario_movimientoinventario",
                    estado_nuevo=f"Producto: {producto.nombre}, Cantidad: {cantidad}, Stock Post: {producto.stock_actual}"
                )

                messages.success(request, f"Movimiento de {tipo_mov.lower()} registrado con éxito.")
                return redirect('inventario_dashboard')
        except Exception as e:
            messages.error(request, str(e))

    productos = Producto.objects.filter(estado='ACTIVO', controla_stock=True)
    proveedores = Proveedor.objects.filter(estado='ACTIVO')
    return render(request, 'inventario/movimiento_form.html', {
        'productos': productos,
        'proveedores': proveedores
    })


@login_required
def historial_movimientos(request):
    if not (es_recepcionista(request.user) or es_housekeeping(request.user) or _es_inventario(request.user)):
        return _denegar_acceso(request)

    movimientos = MovimientoInventario.objects.select_related('producto', 'usuario', 'estancia').all()

    # Filtros
    producto_id = request.GET.get('producto', '')
    tipo_mov = request.GET.get('tipo_movimiento', '')
    fecha_ini = request.GET.get('fecha_inicio', '')
    fecha_fi = request.GET.get('fecha_fin', '')

    if producto_id:
        movimientos = movimientos.filter(producto_id=producto_id)
    if tipo_mov:
        movimientos = movimientos.filter(tipo_movimiento=tipo_mov)
    if fecha_ini:
        movimientos = movimientos.filter(fecha__date__gte=fecha_ini)
    if fecha_fi:
        movimientos = movimientos.filter(fecha__date__lte=fecha_fi)

    productos = Producto.objects.filter(estado='ACTIVO')

    return render(request, 'inventario/historial.html', {
        'movimientos': movimientos,
        'productos': productos,
        'producto_id': int(producto_id) if producto_id else '',
        'tipo_mov': tipo_mov,
        'fecha_inicio': fecha_ini,
        'fecha_fin': fecha_fi
    })


@login_required
def categorias_lista(request):
    if not es_admin(request.user):
        return _denegar_acceso(request)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        cat_id = request.POST.get('categoria_id')

        try:
            if cat_id:
                cat = get_object_or_404(CategoriaProducto, id=cat_id)
                cat.nombre = nombre
                cat.estado = request.POST.get('estado', 'ACTIVO')
                cat.save()
                messages.success(request, f"Categoría {nombre} modificada con éxito.")
            else:
                CategoriaProducto.objects.create(nombre=nombre, estado='ACTIVO')
                messages.success(request, f"Categoría {nombre} creada con éxito.")
            return redirect('categorias_lista')
        except Exception as e:
            messages.error(request, f"Error al procesar categoría: {str(e)}")

    categorias = CategoriaProducto.objects.all()
    return render(request, 'inventario/categorias.html', {'categorias': categorias})


@login_required
def proveedores_lista(request):
    if not _es_inventario(request.user):
        return _denegar_acceso(request)

    if request.method == 'POST':
        prov_id = request.POST.get('proveedor_id')
        rs = request.POST.get('razon_social', '').strip()
        doc = request.POST.get('documento_fiscal', '').strip()
        tel = request.POST.get('telefono', '').strip()
        corr = request.POST.get('correo', '').strip()
        dir_f = request.POST.get('direccion', '').strip()
        cont = request.POST.get('persona_contacto', '').strip()
        obs = request.POST.get('observaciones', '').strip()
        est = request.POST.get('estado', 'ACTIVO')

        try:
            if prov_id:
                prov = get_object_or_404(Proveedor, id=prov_id)
                prov.razon_social = rs
                prov.documento_fiscal = doc
                prov.telefono = tel
                prov.correo = corr
                prov.direccion = dir_f
                prov.persona_contacto = cont
                prov.observaciones = obs
                prov.estado = est
                prov.save()
                messages.success(request, f"Proveedor {rs} modificado con éxito.")
            else:
                Proveedor.objects.create(
                    razon_social=rs, documento_fiscal=doc, telefono=tel,
                    correo=corr, direccion=dir_f, persona_contacto=cont,
                    observaciones=obs, estado='ACTIVO'
                )
                messages.success(request, f"Proveedor {rs} registrado con éxito.")
            return redirect('proveedores_lista')
        except Exception as e:
            messages.error(request, f"Error al procesar proveedor: {str(e)}")

    proveedores = Proveedor.objects.all()
    return render(request, 'inventario/proveedores.html', {'proveedores': proveedores})


# ── Conteos Físicos y Ajustes ──────────────────────────────────────────────────
@login_required
def conteo_fisico_lista(request):
    if not _es_inventario(request.user):
        return _denegar_acceso(request)

    conteos = ConteoFisico.objects.select_related('usuario_creador', 'usuario_aprobador').all()
    return render(request, 'inventario/conteos_lista.html', {'conteos': conteos})


@login_required
def conteo_fisico_crear(request):
    if not _es_inventario(request.user):
        return _denegar_acceso(request)

    if request.method == 'POST':
        obs = request.POST.get('observaciones', '').strip()
        try:
            with transaction.atomic():
                conteo = ConteoFisico.objects.create(
                    estado='BORRADOR',
                    usuario_creador=request.user,
                    observaciones=obs
                )
                # Auto-poblar detalles con todos los productos físicos activos
                productos = Producto.objects.filter(estado='ACTIVO', controla_stock=True)
                for prod in productos:
                    DetalleConteoFisico.objects.create(
                        conteo=conteo,
                        producto=prod,
                        stock_sistema=prod.stock_actual,
                        stock_fisico=prod.stock_actual, # Iniciamos igualado al sistema
                        diferencia=Decimal('0.00')
                    )
                messages.success(request, f"Conteo físico #{conteo.id} iniciado en borrador.")
                return redirect('conteo_fisico_detalle', pk=conteo.id)
        except Exception as e:
            messages.error(request, f"Error al iniciar conteo: {str(e)}")

    return render(request, 'inventario/conteo_crear.html')


@login_required
def conteo_fisico_detalle(request, pk):
    if not _es_inventario(request.user):
        return _denegar_acceso(request)

    conteo = get_object_or_404(ConteoFisico, id=pk)

    if request.method == 'POST':
        # Procesar actualización de cantidades físicas
        if conteo.estado in ['BORRADOR', 'PROCESO', 'PENDIENTE_REVISION']:
            try:
                with transaction.atomic():
                    for key, val in request.POST.items():
                        if key.startswith('fisico_'):
                            det_id = int(key.split('_')[1])
                            det = DetalleConteoFisico.objects.get(id=det_id, conteo=conteo)
                            fisico_val = Decimal(val)
                            if fisico_val < 0:
                                raise ValidationError("La cantidad física no puede ser negativa.")
                            det.stock_fisico = fisico_val
                            det.diferencia = fisico_val - det.stock_sistema
                            det.save()

                    # Guardar comentarios
                    conteo.observaciones = request.POST.get('observaciones', '').strip()
                    accion = request.POST.get('accion')
                    if accion == 'ENVIAR_REVISION':
                        conteo.estado = 'PENDIENTE_REVISION'
                    elif accion == 'GUARDAR':
                        conteo.estado = 'PROCESO'
                    conteo.save()
                    messages.success(request, "Conteo físico actualizado.")
                    if accion == 'ENVIAR_REVISION':
                        return redirect('conteo_fisico_lista')
            except Exception as e:
                messages.error(request, f"Error al actualizar conteo: {str(e)}")

    detalles = conteo.detalles.select_related('producto').all()
    return render(request, 'inventario/conteo_detalle.html', {
        'conteo': conteo,
        'detalles': detalles,
        'es_borrador_o_proceso': conteo.estado in ['BORRADOR', 'PROCESO'],
        'es_pendiente_revision': conteo.estado == 'PENDIENTE_REVISION',
        'es_admin': es_admin(request.user)
    })


@login_required
def conteo_fisico_aprobar(request, pk):
    if not es_admin(request.user):
        return _denegar_acceso(request, "Solo administradores pueden aprobar conteos y aplicar ajustes.")

    conteo = get_object_or_404(ConteoFisico, id=pk)

    if conteo.estado != 'PENDIENTE_REVISION':
        messages.error(request, "Solo se pueden aprobar conteos en estado PENDIENTE_REVISION.")
        return redirect('conteo_fisico_detalle', pk=conteo.id)

    try:
        with transaction.atomic():
            detalles = conteo.detalles.select_related('producto').all()
            for det in detalles:
                prod = det.producto
                # Si hay diferencia, aplicar ajuste
                if det.diferencia != 0:
                    existencia_anterior = prod.stock_actual
                    prod.stock_actual = det.stock_fisico
                    prod.save()

                    tipo_mov = 'AJUSTE_POS' if det.diferencia > 0 else 'AJUSTE_NEG'
                    
                    # Generar Movimiento de Inventario
                    mov = MovimientoInventario.objects.create(
                        producto=prod,
                        tipo_movimiento=tipo_mov,
                        cantidad=abs(det.diferencia),
                        existencia_anterior=existencia_anterior,
                        existencia_posterior=prod.stock_actual,
                        motivo=f"Ajuste automático por Conteo Físico #{conteo.id}",
                        usuario=request.user,
                        observacion=conteo.observaciones
                    )

                    # Trazabilidad
                    registrar_auditoria(
                        usuario=request.user,
                        accion=f"Ajuste de Stock ({tipo_mov})",
                        registro_id=mov.id,
                        tabla_afectada="inventario_movimientoinventario",
                        estado_nuevo=f"Producto: {prod.nombre}, Diff: {det.diferencia}, Stock Post: {prod.stock_actual}"
                    )

            conteo.estado = 'APROBADO'
            conteo.fecha_fin = timezone.now()
            conteo.usuario_aprobador = request.user
            conteo.save()

            messages.success(request, f"Conteo físico #{conteo.id} aprobado con éxito y stock actualizado.")
            return redirect('conteo_fisico_lista')
    except Exception as e:
        messages.error(request, f"Error al aprobar conteo: {str(e)}")
        return redirect('conteo_fisico_detalle', pk=conteo.id)


@login_required
def api_categoria_crear(request):
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    if not es_admin(request.user):
        return JsonResponse({'error': 'No autorizado'}, status=403)
    
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'error': 'El nombre es obligatorio'}, status=400)
        
    try:
        # Validar si ya existe
        if CategoriaProducto.objects.filter(nombre__iexact=nombre, estado='ACTIVO').exists():
            return JsonResponse({'error': 'La categoría ya existe y está activa'}, status=400)
            
        cat = CategoriaProducto.objects.create(nombre=nombre, estado='ACTIVO')
        
        # Registrar auditoría
        registrar_auditoria(
            usuario=request.user,
            accion="Categoria Creada API",
            registro_id=cat.id,
            tabla_afectada="inventario_categoriaproducto",
            estado_nuevo=f"Nombre: {nombre}"
        )
        
        return JsonResponse({
            'success': True,
            'id': cat.id,
            'nombre': cat.nombre
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
