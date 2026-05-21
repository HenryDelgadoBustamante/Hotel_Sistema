from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse


class ReportesViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(username='recep_reportes_test', password='password123')
        self.group = Group.objects.create(name='recepcionista')
        self.user.groups.add(self.group)
        self.client.login(username='recep_reportes_test', password='password123')

    def test_reportes_view(self):
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
        response = self.client.get(reverse('exportar_excel'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
