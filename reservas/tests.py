from datetime import date, datetime, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.utils import timezone
from hotel.models import Hotel, TipoHabitacion, Habitacion
from huespedes.models import Huesped
from reservas.models import Reserva, Tarifa


class ReservaModelAndAvailabilityTest(TestCase):
    def setUp(self):
        # 1. Setup metadata
        self.hotel = Hotel.objects.create(
            nombre="Hotel Cusco Imperial",
            ruc="20123456789",
            direccion="Av. El Sol 123",
            estrellas=5,
            telefono="084234567"
        )
        self.tipo_hab = TipoHabitacion.objects.create(
            hotel=self.hotel,
            nombre="Suite Delux",
            capacidad=2,
            precio_base=Decimal("200.00")
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel,
            tipo=self.tipo_hab,
            numero="301",
            piso=3,
            estado=Habitacion.DISPONIBLE
        )
        self.huesped = Huesped.objects.create(
            tipo_doc=Huesped.DNI,
            num_doc="12345678",
            nombres="Juan",
            apellidos="Perez"
        )

    def test_reserva_por_dia_calculo_precio_sin_tarifa_especial(self):
        reserva = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 5),
            modalidad=Reserva.POR_DIA
        )
        reserva.precio_total = reserva.calcular_precio()
        reserva.save()
        # 4 noches * 200 = 800
        self.assertEqual(reserva.precio_total, Decimal("800.00"))

    def test_reserva_por_dia_calculo_precio_con_tarifa_especial(self):
        # Crear tarifa especial para ese rango de fechas
        Tarifa.objects.create(
            tipo_habitacion=self.tipo_hab,
            nombre="Temporada Alta",
            precio_noche=Decimal("250.00"),
            fecha_inicio=date(2026, 6, 1),
            fecha_fin=date(2026, 6, 10)
        )
        reserva = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 5),
            modalidad=Reserva.POR_DIA
        )
        reserva.precio_total = reserva.calcular_precio()
        reserva.save()
        # 4 noches * 250 = 1000
        self.assertEqual(reserva.precio_total, Decimal("1000.00"))

    def test_reserva_por_horas_calculo_precio(self):
        # Duración de 3 horas -> 1 bloque de 3 horas. Tarifa por bloque = 35% del precio base
        # 35% de 200 = 70.00
        reserva = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 1),
            modalidad=Reserva.POR_HORA,
            duracion_horas=3
        )
        reserva.precio_total = reserva.calcular_precio()
        reserva.save()
        self.assertEqual(reserva.precio_total, Decimal("70.00"))

        # Duración de 4 horas -> 2 bloques de 3 horas (se redondea hacia arriba) -> 2 * 70 = 140.00
        reserva2 = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 2),
            fecha_salida=date(2026, 6, 2),
            modalidad=Reserva.POR_HORA,
            duracion_horas=4
        )
        reserva2.precio_total = reserva2.calcular_precio()
        reserva2.save()
        self.assertEqual(reserva2.precio_total, Decimal("140.00"))

    def test_solapamiento_por_dia_mismas_fechas(self):
        # 1. Primera reserva confirmada del 1 al 5
        r1 = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 5),
            modalidad=Reserva.POR_DIA,
            estado=Reserva.CONFIRMADA
        )
        
        # 2. Segunda reserva en las mismas fechas -> Debe fallar al validar
        r2 = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 5),
            modalidad=Reserva.POR_DIA,
            estado=Reserva.PENDIENTE
        )
        with self.assertRaises(ValidationError):
            r2.save()

    def test_solapamiento_por_dia_fechas_cruzadas(self):
        # Reserva del 5 al 10
        r1 = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 5),
            fecha_salida=date(2026, 6, 10),
            modalidad=Reserva.POR_DIA,
            estado=Reserva.CONFIRMADA
        )
        
        # Cruzada: del 8 al 12
        r2 = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 8),
            fecha_salida=date(2026, 6, 12),
            modalidad=Reserva.POR_DIA,
            estado=Reserva.PENDIENTE
        )
        with self.assertRaises(ValidationError):
            r2.save()

        # Cruzada: del 3 al 6
        r3 = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 3),
            fecha_salida=date(2026, 6, 6),
            modalidad=Reserva.POR_DIA,
            estado=Reserva.PENDIENTE
        )
        with self.assertRaises(ValidationError):
            r3.save()

    def test_no_solapamiento_por_dia_contiguas(self):
        # Reserva del 1 al 5 (check-out el 5 a las 12:00)
        r1 = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 5),
            modalidad=Reserva.POR_DIA,
            estado=Reserva.CONFIRMADA
        )
        
        # Segunda reserva empieza el 5 (check-in el 5 a las 15:00) -> Permitido
        r2 = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 5),
            fecha_salida=date(2026, 6, 10),
            modalidad=Reserva.POR_DIA,
            estado=Reserva.PENDIENTE
        )
        try:
            r2.save()
        except ValidationError:
            self.fail("ValidationError lanzado en reservas contiguas (no solapadas).")

    def test_solapamiento_por_horas(self):
        # Reserva por hora el 1 de junio, de 10:00 a 13:00
        dt_entrada = timezone.make_aware(datetime(2026, 6, 1, 10, 0))
        r1 = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 1),
            fecha_hora_entrada=dt_entrada,
            modalidad=Reserva.POR_HORA,
            duracion_horas=3,
            estado=Reserva.CONFIRMADA
        )

        # Reserva por hora solapada: 1 de junio, de 12:00 a 15:00
        dt_entrada2 = timezone.make_aware(datetime(2026, 6, 1, 12, 0))
        r2 = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 1),
            fecha_hora_entrada=dt_entrada2,
            modalidad=Reserva.POR_HORA,
            duracion_horas=3,
            estado=Reserva.PENDIENTE
        )
        with self.assertRaises(ValidationError):
            r2.save()

        # Reserva por hora NO solapada: 1 de junio, de 14:00 a 17:00 -> Permitido
        dt_entrada3 = timezone.make_aware(datetime(2026, 6, 1, 14, 0))
        r3 = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 1),
            fecha_hora_entrada=dt_entrada3,
            modalidad=Reserva.POR_HORA,
            duracion_horas=3,
            estado=Reserva.PENDIENTE
        )
        try:
            r3.save()
        except ValidationError:
            self.fail("ValidationError lanzado en reservas por horas no solapadas.")

    def test_reserva_habitacion_mantenimiento_forbidden(self):
        self.habitacion.estado = Habitacion.MANTENIMIENTO
        self.habitacion.save()

        reserva = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 5),
            modalidad=Reserva.POR_DIA
        )
        with self.assertRaises(ValidationError):
            reserva.save()

    def test_restricciones_modificar_y_cancelar(self):
        reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 6, 1),
            fecha_salida=date(2026, 6, 5),
            modalidad=Reserva.POR_DIA,
            estado=Reserva.CONFIRMADA
        )
        reserva.estado = Reserva.CHECKIN
        reserva.save()

        client = Client()
        user = User.objects.create_superuser(username='recep_test_p1', password='password123')
        group, _ = Group.objects.get_or_create(name='recepcionista')
        user.groups.add(group)
        client.login(username='recep_test_p1', password='password123')

        response = client.get(reverse('reserva_editar', kwargs={'reserva_id': reserva.id}))
        self.assertEqual(response.status_code, 302)
        
        response = client.post(reverse('reserva_cancelar', kwargs={'reserva_id': reserva.id}), {'motivo_cancelacion': 'Test'})
        self.assertEqual(response.status_code, 302)
        
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reserva.CHECKIN)


class ReservaViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.hotel = Hotel.objects.create(
            nombre="Hotel Imperial", ruc="11122233344", direccion="Centro Cusco", estrellas=3, telefono="987654321"
        )
        self.tipo_hab = TipoHabitacion.objects.create(
            hotel=self.hotel, nombre="Simple", capacidad=1, precio_base=Decimal("100.00")
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_hab, numero="101", piso=1, estado=Habitacion.DISPONIBLE
        )
        self.huesped = Huesped.objects.create(
            tipo_doc=Huesped.DNI, num_doc="77777777", nombres="Ana", apellidos="Mendoza"
        )
        
        # Crear usuario admin y agregarlo al grupo recepcionista
        self.user = User.objects.create_superuser(username='recep_test', password='password123')
        self.group = Group.objects.create(name='recepcionista')
        self.user.groups.add(self.group)
        self.client.login(username='recep_test', password='password123')

    def test_reservas_lista_view(self):
        response = self.client.get(reverse('reservas_lista'))
        self.assertEqual(response.status_code, 200)

    def test_reserva_nueva_view_post(self):
        # Crear reserva vía POST
        data = {
            'huesped_id': self.huesped.id,
            'habitacion': self.habitacion.id,
            'modalidad': Reserva.POR_DIA,
            'fecha_entrada': '2026-07-01',
            'fecha_salida': '2026-07-03',
            'num_adultos': 1,
            'origen': Reserva.DIRECTO
        }
        response = self.client.post(reverse('reserva_nueva'), data)
        self.assertEqual(response.status_code, 302)  # Debe redirigir tras guardar
        self.assertTrue(Reserva.objects.filter(huesped=self.huesped, habitacion=self.habitacion).exists())

    def test_api_habitaciones_disponibles(self):
        response = self.client.get(reverse('api_habitaciones_disponibles'), {
            'entrada': '2026-07-01',
            'salida': '2026-07-03',
            'modalidad': 'DIA'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('habitaciones', data)
        self.assertTrue(any(h['numero'] == '101' for h in data['habitaciones']))

    def test_registro_anticipo_y_traspaso_a_folio(self):
        reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=date(2026, 7, 1),
            fecha_salida=date(2026, 7, 3),
            modalidad=Reserva.POR_DIA,
            precio_total=Decimal("200.00"),
            estado=Reserva.CONFIRMADA
        )
        
        data_pago = {
            'monto': '50.00',
            'metodo_pago': 'TRANSFERENCIA',
            'transaccion_id': 'TX12345'
        }
        response = self.client.post(reverse('registrar_pago_anticipo', kwargs={'reserva_id': reserva.id}), data_pago)
        self.assertEqual(response.status_code, 302)
        
        from estancias.models import Pago
        pago = Pago.objects.get(reserva=reserva, metodo_pago='TRANSFERENCIA')
        self.assertIsNone(pago.folio)
        self.assertEqual(pago.monto, Decimal("50.00"))
        self.assertEqual(reserva.saldo_pendiente, Decimal("150.00"))
        
        response_checkin = self.client.post(reverse('reserva_checkin', kwargs={'reserva_id': reserva.id}), {'habitacion': self.habitacion.id})
        self.assertEqual(response_checkin.status_code, 302)
        
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reserva.CHECKIN)
        
        from estancias.models import Estancia, Folio
        estancia = Estancia.objects.get(reserva=reserva)
        folio = Folio.objects.get(estancia=estancia)
        
        pago.refresh_from_db()
        self.assertEqual(pago.folio, folio)
        self.assertEqual(folio.saldo_pendiente, Decimal("150.00"))



class RolesAndPermissionsTest(TestCase):
    def setUp(self):
        # Setup basic data
        self.hotel = Hotel.objects.create(
            nombre="Hotel Imperial", ruc="11122233344", direccion="Centro Cusco", estrellas=3, telefono="987654321"
        )
        self.tipo_hab = TipoHabitacion.objects.create(
            hotel=self.hotel, nombre="Simple", capacidad=1, precio_base=Decimal("100.00")
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_hab, numero="101", piso=1, estado=Habitacion.DISPONIBLE
        )
        self.huesped = Huesped.objects.create(
            tipo_doc=Huesped.DNI, num_doc="77777777", nombres="Ana", apellidos="Mendoza"
        )
        
        # Clean current groups for clean testing
        Group.objects.all().delete()
        
    def test_sincronizar_roles_and_access(self):
        from django.core.management import call_command
        # 1. Crear grupos antiguos con mayúsculas
        admin_old = Group.objects.create(name='Administrador')
        recep_old = Group.objects.create(name='Recepcionista')
        house_old = Group.objects.create(name='Housekeeping')
        
        # Crear usuarios y asociar a grupos antiguos
        u_admin = User.objects.create_user(username='u_admin', password='password123')
        u_recep = User.objects.create_user(username='u_recep', password='password123')
        u_house = User.objects.create_user(username='u_house', password='password123')
        u_none = User.objects.create_user(username='u_none', password='password123')
        
        u_admin.groups.add(admin_old)
        u_recep.groups.add(recep_old)
        u_house.groups.add(house_old)
        
        # 2. Ejecutar la sincronización
        call_command('sincronizar_roles')
        
        # 3. Comprobar que los grupos antiguos se eliminaron y existen los canónicos en minúscula
        self.assertFalse(Group.objects.filter(name='Administrador').exists())
        self.assertFalse(Group.objects.filter(name='Recepcionista').exists())
        self.assertFalse(Group.objects.filter(name='Housekeeping').exists())
        
        self.assertTrue(Group.objects.filter(name='admin').exists())
        self.assertTrue(Group.objects.filter(name='recepcionista').exists())
        self.assertTrue(Group.objects.filter(name='housekeeping').exists())
        
        # 4. Comprobar que los usuarios fueron migrados correctamente
        u_admin.refresh_from_db()
        u_recep.refresh_from_db()
        u_house.refresh_from_db()
        
        self.assertTrue(u_admin.groups.filter(name='admin').exists())
        self.assertTrue(u_recep.groups.filter(name='recepcionista').exists())
        self.assertTrue(u_house.groups.filter(name='housekeeping').exists())
        
        # 5. Comprobar que los permisos estén asignados correctamente
        # Recepcionista no debe tener permisos de eliminación en hotel, huespedes, reservas, estancias
        recep_group = Group.objects.get(name='recepcionista')
        delete_perms = recep_group.permissions.filter(codename__startswith='delete_')
        self.assertEqual(delete_perms.count(), 0)
        
        # 6. Comprobar que el comando puede ejecutarse múltiples veces sin problemas
        try:
            call_command('sincronizar_roles')
        except Exception as e:
            self.fail(f"Error al ejecutar sincronizar_roles por segunda vez: {e}")
            
        # 7. Verificar acceso a través del cliente Django
        client = Client()
        
        # Usuario sin grupo recibe 403 o redirección a login/error
        client.login(username='u_none', password='password123')
        response = client.get(reverse('reservas_lista'))
        self.assertEqual(response.status_code, 403)
        client.logout()
        
        # Obtener tokens JWT para APIs
        res = client.post(reverse('token_obtain_pair'), {'username': 'u_recep', 'password': 'password123'})
        recep_token = res.json().get('access')
        
        res = client.post(reverse('token_obtain_pair'), {'username': 'u_admin', 'password': 'password123'})
        admin_token = res.json().get('access')

        # Recepcionista puede acceder a reservas pero no a reportes ni exportaciones
        client.login(username='u_recep', password='password123')
        response = client.get(reverse('reservas_lista'))
        self.assertEqual(response.status_code, 200)
        
        # Debe recibir 403 al acceder a la vista de reportes
        response = client.get(reverse('reportes'))
        self.assertEqual(response.status_code, 403)
        
        # Debe recibir 403 al acceder a la exportación a Excel
        response = client.get(reverse('exportar_excel'))
        self.assertEqual(response.status_code, 403)
        client.logout()
        
        # Debe recibir 403 al acceder a la API de ocupación (con cabecera JWT)
        response = client.get(reverse('reporte-ocupacion'), HTTP_AUTHORIZATION=f'Bearer {recep_token}')
        self.assertEqual(response.status_code, 403)
        
        # Housekeeping no puede acceder a reservas (403)
        client.login(username='u_house', password='password123')
        response = client.get(reverse('reservas_lista'))
        self.assertEqual(response.status_code, 403)
        client.logout()
        
        # Administrador puede acceder a reservas y a reportes/exportaciones
        client.login(username='u_admin', password='password123')
        response = client.get(reverse('reservas_lista'))
        self.assertEqual(response.status_code, 200)
        
        response = client.get(reverse('reportes'))
        self.assertEqual(response.status_code, 200)
        
        response = client.get(reverse('exportar_excel'))
        self.assertEqual(response.status_code, 200)
        client.logout()
        
        # Debe recibir 200 al acceder a la API de ocupación (con cabecera JWT)
        response = client.get(reverse('reporte-ocupacion'), HTTP_AUTHORIZATION=f'Bearer {admin_token}')
        self.assertEqual(response.status_code, 200)
        
        # Superusuario mantiene acceso completo
        superuser = User.objects.create_superuser(username='super_user', password='password123')
        client.login(username='super_user', password='password123')
        response = client.get(reverse('reservas_lista'))
        self.assertEqual(response.status_code, 200)
        response = client.get(reverse('reportes'))
        self.assertEqual(response.status_code, 200)
        client.logout()

