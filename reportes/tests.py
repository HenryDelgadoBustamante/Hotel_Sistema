from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta, datetime
from hotel.models import Habitacion, TipoHabitacion
from estancias.models import Estancia, Pago, CargoEstancia, Folio
from reservas.models import Reserva, Huesped
from atencion.models import TicketServicio
from reportes.models import registrar_auditoria

class ReportesViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Roles / groups
        self.admin_group = Group.objects.get_or_create(name='admin')[0]
        self.recep_group = Group.objects.get_or_create(name='recepcionista')[0]
        self.hk_group = Group.objects.get_or_create(name='housekeeping')[0]
        
        # Create standard admin user for tests
        self.user = User.objects.create_superuser(username='recep_reportes_test', password='password123')
        self.user.groups.add(self.recep_group)
        self.user.groups.add(self.admin_group) # Make it admin for backward compatibility tests
        
        self.admin_user = User.objects.create_user(username='admin_test', password='password123')
        self.admin_user.groups.add(self.admin_group)
        
        self.recep_user = User.objects.create_user(username='recep_test', password='password123')
        self.recep_user.groups.add(self.recep_group)
        
        self.hk_user = User.objects.create_user(username='hk_test', password='password123')
        self.hk_user.groups.add(self.hk_group)

        # Setup standard hotel entities
        from hotel.models import Hotel
        self.hotel = Hotel.objects.create(
            nombre="Hotel Test",
            ruc="12345678901",
            direccion="Calle Falsa 123",
            estrellas=3
        )
        self.tipo_vip = TipoHabitacion.objects.create(
            hotel=self.hotel,
            nombre="VIP Test",
            capacidad=2,
            precio_base=100.00
        )
        self.hab_101 = Habitacion.objects.create(hotel=self.hotel, numero=901, piso=1, tipo=self.tipo_vip, estado='DISPONIBLE')
        
        # Huesped
        self.huesped = Huesped.objects.create(
            nombres="John", apellidos="Doe", tipo_doc="DNI", num_doc="77777777"
        )
        
        # Reserva
        self.reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.hab_101,
            fecha_entrada=timezone.now().date(),
            fecha_salida=timezone.now().date() + timedelta(days=2),
            modalidad='DIA',
            origen='DIRECTO',
            precio_total=200.0,
            estado='CHECKIN'
        )
        
        # Estancia
        self.estancia = Estancia.objects.create(
            reserva=self.reserva,
            habitacion=self.hab_101,
            fecha_checkin=timezone.now() - timedelta(days=1),
            precio_final=200.0,
            estado='ACTIVA'
        )
        
        self.folio = Folio.objects.create(estancia=self.estancia)
        
        # Cargo early check-in
        CargoEstancia.objects.create(
            estancia=self.estancia,
            tipo='HABITACION',
            concepto='Recargo Early Check-In',
            monto=30.0
        )
        
        # Ticket
        TicketServicio.objects.create(
            estancia=self.estancia,
            categoria='LIMPIEZA',
            prioridad='ALTA',
            estado='ABIERTA',
            descripcion='Limpieza extra'
        )

    def test_reportes_view(self):
        self.client.login(username='recep_reportes_test', password='password123')
        response = self.client.get(reverse('reportes'))
        self.assertEqual(response.status_code, 200)

    def test_reportes_ocupacion_api_view(self):
        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken.for_user(self.user)
        response = self.client.get(reverse('reporte-ocupacion'), HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('tasa_ocupacion', data)
        self.assertIn('total_habitaciones', data)

    def test_exportar_excel_view(self):
        self.client.login(username='recep_reportes_test', password='password123')
        response = self.client.get(reverse('exportar_excel'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_admin_access_all_tabs(self):
        self.client.login(username='admin_test', password='password123')
        # General tab
        response = self.client.get(reverse('reportes'), {'tab': 'general'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Resumen General')
        
        # Finanzas tab
        response = self.client.get(reverse('reportes'), {'tab': 'finanzas'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Finanzas y Caja')

    def test_recep_cannot_access_financial_tabs(self):
        self.client.login(username='recep_test', password='password123')
        # recep asking for general is fallback to ocupacion
        response = self.client.get(reverse('reportes'), {'tab': 'general'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ocupación y Disponibilidad') # Fallback
        
        # recep asking for finanzas is fallback to ocupacion
        response = self.client.get(reverse('reportes'), {'tab': 'finanzas'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ocupación y Disponibilidad')

    def test_housekeeping_redirected_or_forbidden(self):
        self.client.login(username='hk_test', password='password123')
        response = self.client.get(reverse('reportes'))
        self.assertEqual(response.status_code, 403)

    def test_filters_applied(self):
        self.client.login(username='admin_test', password='password123')
        # Filter by piso 99 (which has no rooms)
        response = self.client.get(reverse('reportes'), {'tab': 'ocupacion', 'piso': '99'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No se encontraron habitaciones')

    def test_exportar_excel_with_filters(self):
        self.client.login(username='admin_test', password='password123')
        response = self.client.get(reverse('exportar_excel'), {
            'fecha_inicio': timezone.now().date().strftime('%Y-%m-%d'),
            'fecha_fin': (timezone.now().date() + timedelta(days=2)).strftime('%Y-%m-%d'),
            'piso': '1'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
