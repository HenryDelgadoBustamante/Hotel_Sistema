from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from huespedes.models import Huesped


class HuespedModelTest(TestCase):
    def setUp(self):
        self.huesped = Huesped.objects.create(
            tipo_doc=Huesped.DNI,
            num_doc="99988877",
            nombres="Carlos",
            apellidos="Arias",
            email="carlos@example.com",
            telefono="951753456",
            nacionalidad="Peruana"
        )

    def test_model_properties(self):
        self.assertEqual(self.huesped.nombre_completo, "Carlos Arias")
        self.assertEqual(str(self.huesped), "Carlos Arias (DNI: 99988877)")


class HuespedViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.huesped = Huesped.objects.create(
            tipo_doc=Huesped.DNI,
            num_doc="77766655",
            nombres="Daniela",
            apellidos="Rojas",
            email="daniela@example.com",
            telefono="954852159",
            nacionalidad="Peruana"
        )
        self.user = User.objects.create_superuser(username='recep_huesped_test', password='password123')
        self.group = Group.objects.create(name='recepcionista')
        self.user.groups.add(self.group)
        self.client.login(username='recep_huesped_test', password='password123')

    def test_huespedes_lista_view(self):
        response = self.client.get(reverse('huespedes_lista'))
        self.assertEqual(response.status_code, 200)

    def test_huesped_nuevo_view_post(self):
        data = {
            'tipo_doc': Huesped.CE,
            'num_doc': '00123456',
            'nombres': 'Elena',
            'apellidos': 'Vargas',
            'email': 'elena@example.com',
            'telefono': '951159951',
            'nacionalidad': 'Chilena'
        }
        response = self.client.post(reverse('huesped_nuevo'), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Huesped.objects.filter(num_doc='00123456').exists())

    def test_huesped_editar_view_post(self):
        data = {
            'tipo_doc': Huesped.DNI,
            'num_doc': '77766655',
            'nombres': 'Daniela Modificada',
            'apellidos': 'Rojas',
            'email': 'daniela_mod@example.com',
            'telefono': '954852159',
            'nacionalidad': 'Peruana'
        }
        response = self.client.post(reverse('huesped_editar', kwargs={'huesped_id': self.huesped.id}), data)
        self.assertEqual(response.status_code, 302)
        self.huesped.refresh_from_db()
        self.assertEqual(self.huesped.nombres, 'Daniela Modificada')

    def test_exportar_huespedes_excel_view(self):
        response = self.client.get(reverse('exportar_huespedes_excel'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
