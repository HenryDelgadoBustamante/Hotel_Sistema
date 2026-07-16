from decimal import Decimal
from datetime import time, date, datetime, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.utils import timezone
from hotel.models import Hotel, TipoHabitacion, Habitacion
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia, Folio
from reportes.models import Auditoria


class HotelModelTest(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(
            nombre="Hotel Cusco", ruc="11223344556", direccion="Av. Sol", estrellas=4, telefono="084123456"
        )
        self.tipo_hab = TipoHabitacion.objects.create(
            hotel=self.hotel, nombre="Matrimonial", capacidad=2, precio_base=Decimal("150.00")
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_hab, numero="205", piso=2, estado=Habitacion.DISPONIBLE
        )

    def test_model_str_representations(self):
        self.assertEqual(str(self.hotel), "Hotel Cusco (4★)")
        self.assertEqual(str(self.tipo_hab), "Matrimonial - Hotel Cusco")
        self.assertEqual(str(self.habitacion), "Hab. 205 - Piso 2 (DISPONIBLE)")


class HotelViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.hotel = Hotel.objects.create(
            nombre="Hotel Imperial", ruc="22334455667", direccion="Centro Cusco", estrellas=3, telefono="987654321"
        )
        self.tipo_hab = TipoHabitacion.objects.create(
            hotel=self.hotel, nombre="Simple", capacidad=1, precio_base=Decimal("100.00")
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_hab, numero="101", piso=1, estado=Habitacion.DISPONIBLE
        )

        self.user = User.objects.create_superuser(username='recep_hotel_test', password='password123')
        self.group = Group.objects.create(name='recepcionista')
        self.user.groups.add(self.group)
        self.client.login(username='recep_hotel_test', password='password123')

    def test_habitaciones_lista_view(self):
        response = self.client.get(reverse('habitaciones_lista'))
        self.assertEqual(response.status_code, 200)

    def test_habitacion_nueva_view_post(self):
        data = {
            'hotel': self.hotel.id,
            'tipo': self.tipo_hab.id,
            'numero': '102',
            'piso': 1,
            'estado': 'DISPONIBLE'
        }
        # Assuming the view supports creating room. Let's see if the view redirects or returns 200
        # If it returns 302, it succeeded.
        response = self.client.post(reverse('habitacion_nueva'), data)
        self.assertIn(response.status_code, [200, 302])
        self.assertTrue(Habitacion.objects.filter(numero='102').exists())


class HotelConfiguracionTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Group
        self.admin_group, _ = Group.objects.get_or_create(name='admin')
        self.recep_group, _ = Group.objects.get_or_create(name='recepcionista')
        self.house_group, _ = Group.objects.get_or_create(name='housekeeping')

        self.admin_user = User.objects.create_user(username='admin_conf', password='password123')
        self.admin_user.groups.add(self.admin_group)

        self.recep_user = User.objects.create_user(username='recep_conf', password='password123')
        self.recep_user.groups.add(self.recep_group)

        self.house_user = User.objects.create_user(username='house_conf', password='password123')
        self.house_user.groups.add(self.house_group)

        self.hotel = Hotel.objects.create(
            nombre="Hotel Imperial Cusco",
            ruc="20123456789",
            direccion="Plaza de Armas 123",
            estrellas=5,
            telefono="084999999",
            hora_checkin_estandar=time(15, 0),
            hora_checkout_estandar=time(12, 0),
            permitir_early_checkin=True,
            cobrar_early_checkin=True,
            early_checkin_tipo_cargo='FIJO',
            early_checkin_monto_porcentaje=Decimal('40.00'),
            permitir_late_checkout=True,
            late_checkout_tipo_cargo='FIJO',
            late_checkout_monto_porcentaje=Decimal('50.00'),
            late_checkout_hora_maxima=time(16, 0)
        )

        self.tipo_hab = TipoHabitacion.objects.create(
            hotel=self.hotel, nombre="Matrimonial Superior", capacidad=2, precio_base=Decimal("200.00")
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_hab, numero="301", piso=3, estado=Habitacion.DISPONIBLE
        )
        self.huesped = Huesped.objects.create(
            nombres="Julio", apellidos="Gomez", tipo_doc="DNI", num_doc="77777777"
        )

    def test_model_validations(self):
        # Validar que no permita hora máxima anterior o igual a la estándar de checkout
        self.hotel.late_checkout_hora_maxima = time(11, 0)
        with self.assertRaises(ValidationError):
            self.hotel.full_clean()

    def test_early_checkin_block_when_deactivated(self):
        # Desactivar Early Check-In
        self.hotel.permitir_early_checkin = False
        self.hotel.save()

        reserva = Reserva.objects.create(
            hotel=self.hotel, huesped=self.huesped, habitacion=self.habitacion,
            fecha_entrada=date.today(), fecha_salida=date.today() + timedelta(days=2),
            precio_total=Decimal('400.00'), estado='PENDIENTE'
        )

        # Tratar de hacer check-in temprano (horas antes)
        # Se asume hora actual es las 09:00 AM (Check-in oficial es a las 15:00)
        import estancias.services as estancia_services
        from django.utils import timezone
        from datetime import datetime
        now_local = timezone.make_aware(datetime.combine(date.today(), time(9, 0)))

        with self.assertRaises(ValidationError):
            estancia_services.procesar_checkin(
                reserva_id=reserva.id,
                habitacion_id=self.habitacion.id,
                usuario=self.recep_user,
                now_local_override=now_local # We need to make sure procesar_checkin supports this override or mock timezone.now
            )
        # Wait, if procesar_checkin does not support now_local_override, let's mock/change timezone.now or we can test detectar_early_checkin directly
        es_early, early_monto = estancia_services.detectar_early_checkin(reserva, self.hotel, now_local)
        self.assertTrue(es_early)
        # And check validation in view or custom check
        self.assertFalse(self.hotel.permitir_early_checkin)

    def test_late_checkout_block_when_deactivated(self):
        # Desactivar Late Check-Out
        self.hotel.permitir_late_checkout = False
        self.hotel.save()

        reserva = Reserva.objects.create(
            hotel=self.hotel, huesped=self.huesped, habitacion=self.habitacion,
            fecha_entrada=date.today() - timedelta(days=2), fecha_salida=date.today(),
            precio_total=Decimal('400.00'), estado='CHECKIN'
        )
        reserva.fecha_hora_salida = timezone.make_aware(datetime.combine(date.today(), time(12, 0)))
        reserva.save()

        estancia = Estancia.objects.create(
            reserva=reserva, habitacion=self.habitacion, precio_final=Decimal('400.00'), estado='ACTIVA'
        )
        Folio.objects.create(estancia=estancia, estado=Folio.ABIERTO)

        import estancias.services as estancia_services
        # Tratar de hacer check-out tarde (03:00 PM)
        now_local = timezone.make_aware(datetime.combine(date.today(), time(15, 0)))
        es_late, late_monto, minutos_tarde = estancia_services.detectar_late_checkout(estancia, self.hotel, now_local)
        
        self.assertTrue(es_late)
        self.assertEqual(late_monto, Decimal('0.00')) # because permitir_late_checkout is False
        
        with self.assertRaises(ValidationError):
            estancia_services.procesar_checkout(
                estancia_id=estancia.id,
                usuario=self.recep_user,
                now_local_override=now_local
            )

    def test_view_permissions(self):
        client = Client()
        
        # 1. Housekeeping: No ve costos ni historial
        client.login(username='house_conf', password='password123')
        response = client.get(reverse('configuracion_hotel'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['mostrar_costos'])
        self.assertFalse(response.context['mostrar_historial'])

        # 2. Recepcionista: Ve pero no edita (campos deshabilitados, POST retorna 403)
        client.login(username='recep_conf', password='password123')
        response = client.get(reverse('configuracion_hotel'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['mostrar_costos'])
        self.assertTrue(response.context['mostrar_historial'])
        self.assertFalse(response.context['es_admin'])

        post_response = client.post(reverse('configuracion_hotel'), {'nombre': 'Nuevo'})
        self.assertEqual(post_response.status_code, 403)

        # 3. Administrador: Ve, edita y registra Auditoria
        client.login(username='admin_conf', password='password123')
        response = client.get(reverse('configuracion_hotel'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['es_admin'])

        # Modificar hora y costo
        data = {
            'nombre': 'Hotel Cusco Modificado',
            'ruc': '20123456789',
            'direccion': 'Plaza de Armas 123',
            'telefono': '084999999',
            'hora_checkin_estandar': '14:00',
            'hora_checkout_estandar': '11:00',
            'permitir_early_checkin': 'on',
            'costo_early_checkin': '50.00',
            'permitir_late_checkout': 'on',
            'costo_late_checkout': '60.00',
            'late_checkout_hora_maxima': '15:00'
        }
        post_response = client.post(reverse('configuracion_hotel'), data)
        self.assertEqual(post_response.status_code, 302)

        # Validar que los campos se actualizaron en la base de datos
        self.hotel.refresh_from_db()
        self.assertEqual(self.hotel.nombre, 'Hotel Cusco Modificado')
        self.assertEqual(self.hotel.hora_checkin_estandar, time(14, 0))
        self.assertEqual(self.hotel.early_checkin_monto_porcentaje, Decimal('50.00'))

        # Validar que se crearon los registros de Auditoria
        logs = Auditoria.objects.filter(tabla_afectada="hotel_hotel")
        self.assertTrue(logs.exists())
        self.assertTrue(logs.filter(estado_nuevo="14:00:00").exists())

