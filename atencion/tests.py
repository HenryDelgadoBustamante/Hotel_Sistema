from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.utils import timezone
from decimal import Decimal
from hotel.models import Hotel, TipoHabitacion, Habitacion
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia, Folio, CargoEstancia, Pago, Reembolso
from atencion.models import TicketServicio, SeguimientoTicket


class TicketServicioTestCase(TestCase):
    def setUp(self):
        # 1. Crear grupos de usuarios (get_or_create para evitar deadlocks en tests paralelos)
        self.grupo_recepcion, _ = Group.objects.get_or_create(name='recepcionista')
        self.grupo_housekeeping, _ = Group.objects.get_or_create(name='housekeeping')
        self.grupo_admin, _ = Group.objects.get_or_create(name='admin')
        
        # 2. Crear usuarios
        self.usuario_recep = User.objects.create_user(username='recepcionista1', password='password123')
        self.usuario_recep.groups.add(self.grupo_recepcion)
        
        self.usuario_hk = User.objects.create_user(username='camarera1', password='password123')
        self.usuario_hk.groups.add(self.grupo_housekeeping)
        
        self.usuario_admin = User.objects.create_superuser(username='administrador1', email='admin@hotel.com', password='password123')
        self.usuario_admin.groups.add(self.grupo_admin)
        
        # 3. Crear infraestructura básica
        self.hotel = Hotel.objects.create(
            nombre="Hotel Cusco", ruc="10293847561", direccion="Av. El Sol 123", estrellas=4, telefono="084223344"
        )
        self.tipo_hab = TipoHabitacion.objects.create(
            hotel=self.hotel, nombre="Estándar Matrimonial", capacidad=2, precio_base=Decimal("100.00")
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_hab, numero="101", piso=1, estado=Habitacion.DISPONIBLE
        )
        
        # 4. Crear Huesped
        self.huesped = Huesped.objects.create(
            nombres="Pedro", apellidos="Páramo", tipo_doc="DNI", num_doc="00112233"
        )
        
        # 5. Crear Reserva
        self.reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=timezone.now().date(),
            fecha_salida=(timezone.now() + timezone.timedelta(days=2)).date(),
            precio_total=Decimal("200.00"),
            estado=Reserva.CONFIRMADA
        )
        
        # 6. Crear Estancia (Check-in)
        self.estancia = Estancia.objects.create(
            reserva=self.reserva,
            habitacion=self.habitacion,
            fecha_checkin=timezone.now(),
            estado=Estancia.ACTIVA
        )
        self.folio = Folio.objects.create(estancia=self.estancia)
        self.habitacion.estado = Habitacion.OCUPADA
        self.habitacion.save()

        # Configurar cliente de pruebas
        self.client = Client()

    def test_creacion_ticket_feliz(self):
        """Prueba la creación de un ticket de servicio con hospedaje activo"""
        self.client.login(username='recepcionista1', password='password123')
        
        response = self.client.post('/tickets/nuevo/', {
            'estancia': self.estancia.id,
            'categoria': 'INFORMACION',
            'prioridad': 'MEDIA',
            'responsable': 'RECEPCION',
            'descripcion': 'Huésped solicita contraseña del Wi-Fi.'
        })
        
        # Debe redirigir al detalle del ticket
        self.assertEqual(response.status_code, 302)
        
        # Validar en base de datos
        ticket = TicketServicio.objects.first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.numero_atencion, f"TKT-{ticket.fecha.year}-{ticket.id:05d}")
        self.assertEqual(ticket.estado, 'ABIERTA')
        self.assertEqual(ticket.recepcionista, self.usuario_recep)
        
        # Validar seguimiento inicial
        seguimiento = SeguimientoTicket.objects.filter(ticket=ticket).first()
        self.assertIsNotNone(seguimiento)
        self.assertEqual(seguimiento.estado_ticket, 'ABIERTA')
        self.assertIn("Wi-Fi", seguimiento.comentario)

    def test_creacion_ticket_limpieza_automatizacion(self):
        """Prueba que los tickets de categoría Limpieza pongan la habitación en LIMPIEZA"""
        self.client.login(username='recepcionista1', password='password123')
        
        response = self.client.post('/tickets/nuevo/', {
            'estancia': self.estancia.id,
            'categoria': 'LIMPIEZA',
            'prioridad': 'ALTA',
            'responsable': 'RECEPCION',  # Aunque mande RECEPCION, el código sobreescribe responsable o el selector de UI ayuda
            'descripcion': 'El huésped reportó derrame de líquido en la alfombra.'
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Validar estado de la habitación
        self.habitacion.refresh_from_db()
        self.assertEqual(self.habitacion.estado, Habitacion.LIMPIEZA)

    def test_creacion_ticket_mantenimiento_automatizacion(self):
        """Prueba que los tickets de Mantenimiento pongan la habitación en MANTENIMIENTO"""
        self.client.login(username='recepcionista1', password='password123')
        
        response = self.client.post('/tickets/nuevo/', {
            'estancia': self.estancia.id,
            'categoria': 'MANTENIMIENTO',
            'prioridad': 'URGENTE',
            'responsable': 'MANTENIMIENTO',
            'descripcion': 'La ducha no sale con agua caliente.'
        })
        
        self.assertEqual(response.status_code, 302)
        
        self.habitacion.refresh_from_db()
        self.assertEqual(self.habitacion.estado, Habitacion.MANTENIMIENTO)

    def test_ciclo_vida_ticket(self):
        """Prueba el ciclo de vida completo de un ticket (Iniciar -> Resolver -> Cerrar -> Reabrir)"""
        # Crear ticket
        ticket = TicketServicio.objects.create(
            estancia=self.estancia,
            categoria='INFORMACION',
            prioridad='MEDIA',
            responsable='RECEPCION',
            descripcion='Solicitud de toallas extras.',
            recepcionista=self.usuario_recep
        )
        
        self.client.login(username='recepcionista1', password='password123')
        
        # 1. Iniciar trabajo
        response = self.client.post(f'/tickets/{ticket.id}/iniciar/')
        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, 'PROCESO')
        
        # 2. Resolver
        response = self.client.post(f'/tickets/{ticket.id}/resolver/', {
            'solucion': 'Se entregaron 2 toallas adicionales al huésped.',
            'observacion_resolucion': 'Entregado a conformidad.'
        })
        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, 'RESUELTA')
        self.assertEqual(ticket.solucion, 'Se entregaron 2 toallas adicionales al huésped.')
        
        # 3. Cerrar
        response = self.client.post(f'/tickets/{ticket.id}/cerrar/')
        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, 'CERRADA')
        
        # 4. Reabrir
        response = self.client.post(f'/tickets/{ticket.id}/reabrir/', {
            'motivo_reapertura': 'El huésped indica que las toallas están sucias.'
        })
        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, 'PROCESO')
        self.assertEqual(ticket.motivo_reapertura, 'El huésped indica que las toallas están sucias.')

    def test_asociar_cargo_extra(self):
        """Prueba que se pueda cargar un costo extra desde el ticket"""
        ticket = TicketServicio.objects.create(
            estancia=self.estancia,
            categoria='SERVICIO_HABITACION',
            prioridad='MEDIA',
            responsable='RECEPCION',
            descripcion='Pedido de cena a la habitación.',
            recepcionista=self.usuario_recep
        )
        
        self.client.login(username='recepcionista1', password='password123')
        
        # Enviar cargo
        response = self.client.post(f'/tickets/{ticket.id}/cargo/', {
            'concepto': 'Cena de lomo saltado',
            'monto': '45.00',
            'tipo': 'CONSUMO'
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Verificar cargo en folio
        self.folio.calcular_totales()
        self.assertEqual(self.folio.total, Decimal('45.00'))
        
        # Verificar seguimiento en ticket
        seguimiento = SeguimientoTicket.objects.filter(ticket=ticket).last()
        self.assertIn("S/. 45.00", seguimiento.comentario)

    def test_reembolsos_admin_vista_y_aprobacion(self):
        """Prueba que el admin pueda ver y resolver reembolsos pendientes"""
        # Crear un pago y una solicitud de reembolso normal
        pago = Pago.objects.create(
            folio=self.folio,
            monto=Decimal("100.00"),
            metodo_pago="EFECTIVO"
        )
        reembolso = Reembolso.objects.create(
            pago=pago,
            monto=Decimal("100.00"),
            motivo="Error en cobro de habitación.",
            estado=Reembolso.SOLICITADO,
            solicitado_por=self.usuario_recep
        )
        
        # Login como administrador
        self.client.login(username='administrador1', password='password123')
        
        # 1. Verificar listado
        response = self.client.get('/reembolsos/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Solicitudes de Reembolsos")
        
        # 2. Resolver y Aprobar Reembolso (debería finalizar estancia y cerrar folio)
        response = self.client.post(f'/reembolsos/{reembolso.id}/resolver/', {
            'accion': 'APROBAR',
            'observacion': 'Aprobado según reporte de recepción.'
        })
        self.assertEqual(response.status_code, 302)
        
        # Verificar estado del reembolso, folio y estancia
        reembolso.refresh_from_db()
        self.assertEqual(reembolso.estado, Reembolso.APROBADO)
        
        self.folio.refresh_from_db()
        self.assertEqual(self.folio.estado, Folio.CERRADO)
        
        self.estancia.refresh_from_db()
        self.assertEqual(self.estancia.estado, Estancia.FINALIZADA)
