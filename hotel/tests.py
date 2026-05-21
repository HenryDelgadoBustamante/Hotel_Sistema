from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from hotel.models import Hotel, TipoHabitacion, Habitacion


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
