from datetime import date
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from hotel.models import Hotel, TipoHabitacion, Habitacion
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia


class FrontendViewsIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Base setup
        self.hotel = Hotel.objects.create(
            nombre="Hotel Cusco", ruc="11122233344", direccion="Av. Sol", estrellas=4, telefono="084999888"
        )
        self.tipo_hab = TipoHabitacion.objects.create(
            hotel=self.hotel, nombre="Matrimonial", capacidad=2, precio_base=Decimal("150.00")
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_hab, numero="204", piso=2, estado=Habitacion.DISPONIBLE
        )
        self.huesped = Huesped.objects.create(
            tipo_doc=Huesped.DNI, num_doc="99998888", nombres="Rosa", apellidos="Salas"
        )
        self.reserva = Reserva.objects.create(
            hotel=self.hotel, huesped=self.huesped, habitacion=self.habitacion,
            fecha_entrada=date(2026, 8, 1), 
            fecha_salida=date(2026, 8, 3),
            modalidad=Reserva.POR_DIA, estado=Reserva.CONFIRMADA
        )
        self.reserva.precio_total = self.reserva.calcular_precio()
        self.reserva.save()

        # Admin user
        self.admin_user = User.objects.create_superuser(username='admin_test', password='password123', email='admin@test.com')
        self.admin_group, _ = Group.objects.get_or_create(name='admin')
        self.admin_user.groups.add(self.admin_group)

    def test_login_logout_dashboard_views(self):
        # 1. Login page load
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

        # 2. Login submit
        response_post = self.client.post(reverse('login'), {
            'username': 'admin_test',
            'password': 'password123'
        })
        self.assertEqual(response_post.status_code, 302)  # Redirects to dashboard

        # 3. Dashboard page load
        response_dash = self.client.get(reverse('dashboard'))
        self.assertEqual(response_dash.status_code, 200)

        # 4. Logout submit
        response_logout = self.client.post(reverse('logout'))
        self.assertEqual(response_logout.status_code, 302)

    def test_estancias_lista_and_reservas_calendario(self):
        self.client.login(username='admin_test', password='password123')
        
        # Estancias lista
        response = self.client.get(reverse('estancias_lista'))
        self.assertEqual(response.status_code, 200)

        # Reservas calendario
        response_cal = self.client.get(reverse('reservas_calendario'))
        self.assertEqual(response_cal.status_code, 200)

    def test_housekeeping_and_estado(self):
        self.client.login(username='admin_test', password='password123')
        
        # Housekeeping view
        response = self.client.get(reverse('housekeeping'))
        self.assertEqual(response.status_code, 200)

        # Housekeeping change room status
        response_status = self.client.post(
            reverse('housekeeping_estado', kwargs={'hab_id': self.habitacion.id}),
            {'estado': 'LIMPIEZA'}
        )
        self.assertEqual(response_status.status_code, 302)
        self.habitacion.refresh_from_db()
        self.assertEqual(self.habitacion.estado, 'LIMPIEZA')

    def test_usuarios_lista_and_crud(self):
        self.client.login(username='admin_test', password='password123')

        # List
        response = self.client.get(reverse('usuarios_lista'))
        self.assertEqual(response.status_code, 200)

        # Create user
        data_create = {
            'username': 'new_user',
            'password': 'newpassword123',
            'nombres': 'New',
            'apellidos': 'User',
            'email': 'new@user.com',
            'is_active': 'on',
            'rol': self.admin_group.id
        }
        response_create = self.client.post(reverse('usuario_nuevo'), data_create)
        self.assertEqual(response_create.status_code, 302)
        self.assertTrue(User.objects.filter(username='new_user').exists())
        new_u = User.objects.get(username='new_user')

        # Edit user
        data_edit = {
            'nombres': 'New Edited',
            'apellidos': 'User',
            'email': 'new_edit@user.com',
            'is_active': 'on',
            'rol': self.admin_group.id
        }
        response_edit = self.client.post(reverse('usuario_editar', kwargs={'user_id': new_u.id}), data_edit)
        self.assertEqual(response_edit.status_code, 302)
        new_u.refresh_from_db()
        self.assertEqual(new_u.first_name, 'New Edited')
        
    def test_usuarios_edit_and_delete_flow(self):
        self.client.login(username='admin_test', password='password123')
        
        test_u = User.objects.create_user(username='test_crud', password='pw')
        
        # Edit
        response_edit = self.client.post(reverse('usuario_editar', kwargs={'user_id': test_u.id}), {
            'nombres': 'CRUD Name',
            'apellidos': 'CRUD Last',
            'email': 'crud@test.com',
            'is_active': 'on',
            'rol': ''
        })
        self.assertEqual(response_edit.status_code, 302)
        test_u.refresh_from_db()
        self.assertEqual(test_u.first_name, 'CRUD Name')

        # Delete
        response_delete = self.client.post(reverse('usuario_eliminar', kwargs={'user_id': test_u.id}))
        self.assertEqual(response_delete.status_code, 302)
        self.assertFalse(User.objects.filter(id=test_u.id).exists())
