from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta

from hotel.models import Hotel, TipoHabitacion, Habitacion
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia, CargoEstancia, Folio
from inventario.models import CategoriaProducto, UnidadMedida, Proveedor, Producto, MovimientoInventario, ConteoFisico, DetalleConteoFisico
import estancias.services as estancia_services

class InventarioTests(TestCase):
    def setUp(self):
        # Configurar roles
        self.admin_group, _ = Group.objects.get_or_create(name='admin')
        self.recep_group, _ = Group.objects.get_or_create(name='recepcionista')
        self.inv_group, _ = Group.objects.get_or_create(name='inventario')
        
        self.admin_user = User.objects.create_user(username='admin_inv', password='password123')
        self.admin_user.groups.add(self.admin_group)
        
        self.recep_user = User.objects.create_user(username='recep_inv', password='password123')
        self.recep_user.groups.add(self.recep_group)
        
        self.inv_user = User.objects.create_user(username='inv_user', password='password123')
        self.inv_user.groups.add(self.inv_group)

        # Auxiliares de Inventario
        self.cat_bebida = CategoriaProducto.objects.create(nombre="Bebidas", estado="ACTIVO")
        self.um_unid = UnidadMedida.objects.create(nombre="Unidad", abreviatura="UND")
        self.proveedor = Proveedor.objects.create(razon_social="Distribuidora Alfa", documento_fiscal="20999999999")

        # Hotel & Habitaciones
        self.hotel = Hotel.objects.create(nombre="Hotel Central", ruc="11111111111", direccion="Av. Lima 123", estrellas=4)
        self.tipo_hab = TipoHabitacion.objects.create(hotel=self.hotel, nombre="Estándar", capacidad=2, precio_base=Decimal('80.00'))
        self.hab_201 = Habitacion.objects.create(hotel=self.hotel, numero=201, piso=2, tipo=self.tipo_hab, estado='DISPONIBLE')

        # Huésped
        self.huesped = Huesped.objects.create(nombres="Carlos", apellidos="Perez", tipo_doc="DNI", num_doc="44444444")

        # Reserva & Estancia
        self.reserva = Reserva.objects.create(
            hotel=self.hotel, huesped=self.huesped, habitacion=self.hab_201,
            fecha_entrada=date.today(), fecha_salida=date.today() + timedelta(days=2),
            precio_total=Decimal('160.00'), estado='CHECKIN'
        )
        self.estancia = Estancia.objects.create(
            reserva=self.reserva, habitacion=self.hab_201, precio_final=Decimal('160.00'), estado='ACTIVA'
        )
        self.folio = Folio.objects.create(estancia=self.estancia)

    def test_crear_producto_validaciones(self):
        # Crear producto físico exitoso
        p_agua = Producto.objects.create(
            codigo_interno="AGUA-01",
            nombre="Agua San Mateo 500ml",
            categoria=self.cat_bebida,
            unidad_medida=self.um_unid,
            tipo_elemento="PRODUCTO_STOCK",
            precio_venta=Decimal('3.00'),
            costo_referencial=Decimal('1.20'),
            controla_stock=True,
            stock_actual=Decimal('10.00'),
            stock_minimo=Decimal('3.00'),
            es_vendible=True
        )
        self.assertEqual(p_agua.stock_actual, 10.00)
        self.assertEqual(p_agua.estado_disponibilidad, 'Disponible')

        # Probar restricción de precio negativo
        with self.assertRaises(ValidationError):
            Producto.objects.create(
                codigo_interno="AGUA-02",
                nombre="Agua Invalida",
                categoria=self.cat_bebida,
                unidad_medida=self.um_unid,
                precio_venta=Decimal('-1.00')
            )

    def test_registrar_entrada_salida_inventario(self):
        # Crear producto
        p_soda = Producto.objects.create(
            codigo_interno="SODA-01", nombre="Coca-Cola 500ml", categoria=self.cat_bebida,
            unidad_medida=self.um_unid, controla_stock=True, stock_actual=Decimal('5.00')
        )

        # Entrada manual
        # Emular entrada de 10 unidades
        existencia_anterior = p_soda.stock_actual
        p_soda.stock_actual += Decimal('10.00')
        p_soda.save()

        mov_in = MovimientoInventario.objects.create(
            producto=p_soda, tipo_movimiento='ENTRADA', cantidad=Decimal('10.00'),
            existencia_anterior=existencia_anterior, existencia_posterior=p_soda.stock_actual,
            motivo="Compra Reposicion", proveedor=self.proveedor, usuario=self.admin_user
        )
        self.assertEqual(p_soda.stock_actual, 15.00)
        self.assertEqual(mov_in.tipo_movimiento, 'ENTRADA')

        # Salida manual (Merma)
        existencia_anterior = p_soda.stock_actual
        p_soda.stock_actual -= Decimal('2.00')
        p_soda.save()

        mov_out = MovimientoInventario.objects.create(
            producto=p_soda, tipo_movimiento='SALIDA', cantidad=Decimal('2.00'),
            existencia_anterior=existencia_anterior, existencia_posterior=p_soda.stock_actual,
            motivo="Producto Dañado", usuario=self.admin_user
        )
        self.assertEqual(p_soda.stock_actual, 13.00)
        self.assertEqual(mov_out.tipo_movimiento, 'SALIDA')

    def test_descontar_stock_por_consumo(self):
        # Producto físico con stock
        p_snack = Producto.objects.create(
            codigo_interno="SNK-01", nombre="Papas Lays 150g", categoria=self.cat_bebida,
            unidad_medida=self.um_unid, controla_stock=True, stock_actual=Decimal('5.00'),
            precio_venta=Decimal('4.50'), es_vendible=True
        )

        # Recepcionista registra consumo de 2 unidades
        cargo = estancia_services.registrar_consumo(
            estancia_id=self.estancia.id,
            concepto="", monto=Decimal('0.00'), tipo='RESTAURANTE', usuario=self.recep_user,
            producto_id=p_snack.id, cantidad=2
        )
        
        # Validar descuento de stock
        p_snack.refresh_from_db()
        self.assertEqual(p_snack.stock_actual, 3.00)
        
        # Validar cargo creado en folio
        self.assertEqual(cargo.monto, Decimal('9.00')) # 4.50 * 2
        self.assertEqual(cargo.producto, p_snack)
        self.assertEqual(cargo.cantidad, 2)
        
        # Validar total folio recalculado
        self.folio.refresh_from_db()
        self.assertEqual(self.folio.total, Decimal('9.00'))

    def test_stock_insuficiente_lanza_error(self):
        p_beer = Producto.objects.create(
            codigo_interno="CERV-01", nombre="Cerveza Pilsen 630ml", categoria=self.cat_bebida,
            unidad_medida=self.um_unid, controla_stock=True, stock_actual=Decimal('1.00'),
            precio_venta=Decimal('7.00'), es_vendible=True
        )

        # Intentar consumir 2 unidades (solo hay 1)
        with self.assertRaises(ValidationError):
            estancia_services.registrar_consumo(
                estancia_id=self.estancia.id,
                concepto="", monto=Decimal('0.00'), tipo='RESTAURANTE', usuario=self.recep_user,
                producto_id=p_beer.id, cantidad=2
            )

    def test_servicio_sin_stock_no_descuenta_inventario(self):
        p_laundry = Producto.objects.create(
            codigo_interno="SRV-LAV", nombre="Servicio Planchado", categoria=self.cat_bebida,
            unidad_medida=self.um_unid, controla_stock=False, stock_actual=Decimal('0.00'),
            precio_venta=Decimal('15.00'), es_vendible=True, tipo_elemento='SERVICIO_SIN_STOCK'
        )

        # Consumir el servicio
        cargo = estancia_services.registrar_consumo(
            estancia_id=self.estancia.id,
            concepto="", monto=Decimal('0.00'), tipo='LAVANDERIA', usuario=self.recep_user,
            producto_id=p_laundry.id, cantidad=1
        )
        
        p_laundry.refresh_from_db()
        self.assertEqual(p_laundry.stock_actual, 0.00) # Sigue en cero
        self.assertEqual(cargo.monto, Decimal('15.00'))

    def test_anular_consumo_con_devolucion_stock(self):
        p_water = Producto.objects.create(
            codigo_interno="H2O-01", nombre="Agua de Mesa 1L", categoria=self.cat_bebida,
            unidad_medida=self.um_unid, controla_stock=True, stock_actual=Decimal('10.00'),
            precio_venta=Decimal('2.50'), es_vendible=True
        )

        # Registrar consumo
        cargo = estancia_services.registrar_consumo(
            estancia_id=self.estancia.id,
            concepto="", monto=Decimal('0.00'), tipo='RESTAURANTE', usuario=self.recep_user,
            producto_id=p_water.id, cantidad=2
        )
        p_water.refresh_from_db()
        self.assertEqual(p_water.stock_actual, 8.00)

        # Anular por error de registro (restaura stock)
        estancia_services.exonerar_cargo_servicio(
            cargo_id=cargo.id,
            motivo="Error de digitación, no se entregó",
            devolver_a_stock=True,
            usuario=self.admin_user
        )
        
        p_water.refresh_from_db()
        self.assertEqual(p_water.stock_actual, 10.00) # Regresó a 10
        
        # Cargo debe estar exonerado
        cargo.refresh_from_db()
        self.assertTrue(cargo.exonerado)
        self.assertEqual(cargo.motivo_exoneracion, "Error de digitación, no se entregó")

    def test_exoneracion_financiera_sin_devolver_stock(self):
        p_cookie = Producto.objects.create(
            codigo_interno="CK-01", nombre="Galletas Oreo", categoria=self.cat_bebida,
            unidad_medida=self.um_unid, controla_stock=True, stock_actual=Decimal('5.00'),
            precio_venta=Decimal('1.50'), es_vendible=True
        )

        # Registrar consumo
        cargo = estancia_services.registrar_consumo(
            estancia_id=self.estancia.id,
            concepto="", monto=Decimal('0.00'), tipo='RESTAURANTE', usuario=self.recep_user,
            producto_id=p_cookie.id, cantidad=1
        )
        p_cookie.refresh_from_db()
        self.assertEqual(p_cookie.stock_actual, 4.00)

        # Exoneración por cortesía comercial (NO devuelve stock)
        estancia_services.exonerar_cargo_servicio(
            cargo_id=cargo.id,
            motivo="Cortesía comercial a cliente frecuente",
            devolver_a_stock=False,
            usuario=self.admin_user
        )
        
        p_cookie.refresh_from_db()
        self.assertEqual(p_cookie.stock_actual, 4.00) # Sigue en 4

    def test_conteo_fisico_ajustes(self):
        p_juice = Producto.objects.create(
            codigo_interno="JUG-01", nombre="Jugo de Naranja 1L", categoria=self.cat_bebida,
            unidad_medida=self.um_unid, controla_stock=True, stock_actual=Decimal('8.00')
        )

        # Iniciar conteo físico
        conteo = ConteoFisico.objects.create(estado='PENDIENTE_REVISION', usuario_creador=self.admin_user)
        
        # Registrar detalle con diferencia (físicamente hay 6, diferencia de -2)
        det = DetalleConteoFisico.objects.create(
            conteo=conteo, producto=p_juice, stock_sistema=Decimal('8.00'), stock_fisico=Decimal('6.00'), diferencia=Decimal('-2.00')
        )

        # Aprobar conteo por admin
        client = Client()
        client.login(username='admin_inv', password='password123')
        
        url_aprobar = reverse('conteo_fisico_aprobar', args=[conteo.id])
        response = client.post(url_aprobar)
        
        self.assertEqual(response.status_code, 302)
        
        # Validar actualización de stock y movimiento de ajuste
        p_juice.refresh_from_db()
        self.assertEqual(p_juice.stock_actual, 6.00)
        
        conteo.refresh_from_db()
        self.assertEqual(conteo.estado, 'APROBADO')
        
        # Debe haberse creado un movimiento de ajuste negativo
        mov = MovimientoInventario.objects.filter(producto=p_juice, tipo_movimiento='AJUSTE_NEG').first()
        self.assertIsNotNone(mov)
        self.assertEqual(mov.cantidad, Decimal('2.00'))
