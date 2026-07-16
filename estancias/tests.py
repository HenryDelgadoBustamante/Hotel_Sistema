from datetime import date, datetime, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.utils import timezone
from hotel.models import Hotel, TipoHabitacion, Habitacion
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia, CargoEstancia, Folio, Pago


class EstanciaModelTest(TestCase):
    def setUp(self):
        # Crear base de datos temporal
        self.hotel = Hotel.objects.create(
            nombre="Hotel Test", ruc="12345678901", direccion="Calle 123", estrellas=4, telefono="999888777"
        )
        self.tipo_hab = TipoHabitacion.objects.create(
            hotel=self.hotel, nombre="Doble", capacidad=2, precio_base=Decimal("150.00")
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_hab, numero="202", piso=2, estado=Habitacion.DISPONIBLE
        )
        self.huesped = Huesped.objects.create(
            tipo_doc=Huesped.DNI, num_doc="87654321", nombres="Maria", apellidos="Gomez"
        )
        self.reserva = Reserva.objects.create(
            hotel=self.hotel, huesped=self.huesped, habitacion=self.habitacion,
            fecha_entrada=date(2026, 8, 1), fecha_salida=date(2026, 8, 5),
            modalidad=Reserva.POR_DIA, estado=Reserva.CONFIRMADA
        )
        self.reserva.precio_total = self.reserva.calcular_precio()
        self.reserva.save()

    def test_folio_cargos_y_bloqueo_checkout(self):
        # 1. Creamos la estancia a partir del check-in
        self.reserva.estado = Reserva.CHECKIN
        self.reserva.save()
        estancia = Estancia.objects.create(
            reserva=self.reserva, habitacion=self.habitacion, precio_final=self.reserva.precio_total, estado=Estancia.ACTIVA
        )
        folio = Folio.objects.create(estancia=estancia)

        # 2. Registramos los cargos en la habitación (alquiler y consumo de restaurante)
        CargoEstancia.objects.create(
            estancia=estancia, concepto="Alquiler de Habitación", monto=Decimal("600.00"), tipo=CargoEstancia.HABITACION
        )
        CargoEstancia.objects.create(
            estancia=estancia, concepto="Consumo Restaurante", monto=Decimal("50.00"), tipo=CargoEstancia.RESTAURANTE
        )

        # Recalcular totales del folio
        folio.calcular_totales()

        # Verificamos la suma total (600 + 50 = 650) y división fiscal (IGV 18%)
        self.assertEqual(folio.total, Decimal("650.00"))
        self.assertEqual(folio.subtotal, Decimal("550.85"))
        self.assertEqual(folio.igv, Decimal("99.15"))
        
        # 3. Intentamos hacer check-out con deuda (Debe arrojar ValidationError)
        self.assertEqual(folio.saldo_pendiente, Decimal("650.00"))
        with self.assertRaises(ValidationError):
            estancia.hacer_checkout()

        # 4. Registramos un pago parcial (Aún debe estar bloqueado)
        Pago.objects.create(folio=folio, monto=Decimal("400.00"), metodo_pago=Pago.EFECTIVO)
        self.assertEqual(folio.saldo_pendiente, Decimal("250.00"))
        with self.assertRaises(ValidationError):
            estancia.hacer_checkout()

        # 5. Registramos el pago restante (Saldo = 0.00, check-out debe permitirse)
        Pago.objects.create(folio=folio, monto=Decimal("250.00"), metodo_pago=Pago.TARJETA)
        self.assertEqual(folio.saldo_pendiente, Decimal("0.00"))

        try:
            estancia.hacer_checkout()
        except ValidationError:
            self.fail("Error lanzado al hacer check-out a pesar de tener saldo en cero.")

        # Verificar estados finales
        self.assertEqual(estancia.estado, Estancia.FINALIZADA)
        self.assertEqual(folio.estado, Folio.CERRADO)
        self.assertEqual(self.habitacion.estado, Habitacion.LIMPIEZA) # Estado cambia a limpieza para preparación


class EstanciaViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.hotel = Hotel.objects.create(
            nombre="Hotel Cusco", ruc="22334455667", direccion="Av Sol", estrellas=4, telefono="084999888"
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
        hoy = timezone.localdate()
        self.reserva = Reserva.objects.create(
            hotel=self.hotel, huesped=self.huesped, habitacion=self.habitacion,
            fecha_entrada=hoy, fecha_salida=hoy + timedelta(days=2),
            modalidad=Reserva.POR_DIA, estado=Reserva.CONFIRMADA
        )
        self.reserva.precio_total = self.reserva.calcular_precio()
        self.reserva.save()

        # Crear y autenticar usuario recepcionista
        self.user = User.objects.create_superuser(username='recep_estancias', password='password123')
        self.group = Group.objects.create(name='recepcionista')
        self.user.groups.add(self.group)
        self.client.login(username='recep_estancias', password='password123')

    def test_reserva_checkin_y_cargos_flujo_completo(self):
        # 1. Realizar check-in
        checkin_url = reverse('reserva_checkin', kwargs={'reserva_id': self.reserva.id})
        response = self.client.post(checkin_url, {'habitacion': self.habitacion.id})
        
        self.assertEqual(response.status_code, 302)  # Redirige a folio
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, Reserva.CHECKIN)
        
        estancia = Estancia.objects.get(reserva=self.reserva)
        self.assertEqual(estancia.estado, Estancia.ACTIVA)
        self.assertEqual(estancia.habitacion.estado, Habitacion.OCUPADA)

        # 2. Verificar que se autogeneró el cargo base de habitación
        folio = Folio.objects.get(estancia=estancia)
        self.assertEqual(estancia.cargos.filter(tipo=CargoEstancia.HABITACION).count(), 1)
        self.assertEqual(folio.total, Decimal("300.00")) # 2 noches * 150

        # 3. Agregar cargo extra por restaurante
        cargo_url = reverse('agregar_cargo', kwargs={'estancia_id': estancia.id})
        response_cargo = self.client.post(cargo_url, {
            'concepto': 'Desayuno Buffet',
            'monto': '25.00',
            'tipo': 'RESTAURANTE'
        })
        self.assertEqual(response_cargo.status_code, 302)
        folio.calcular_totales()
        self.assertEqual(folio.total, Decimal("325.00"))

        # 4. Registrar pago
        pago_url = reverse('registrar_pago', kwargs={'estancia_id': estancia.id})
        response_pago = self.client.post(pago_url, {
            'monto': '325.00',
            'metodo_pago': Pago.EFECTIVO
        })
        self.assertEqual(response_pago.status_code, 302)
        folio.calcular_totales()
        self.assertEqual(folio.saldo_pendiente, Decimal("0.00"))

        # 5. Realizar check-out
        checkout_url = reverse('checkout', kwargs={'estancia_id': estancia.id})
        response_checkout = self.client.get(checkout_url)
        self.assertEqual(response_checkout.status_code, 302)
        
        estancia.refresh_from_db()
        self.assertEqual(estancia.estado, Estancia.FINALIZADA)
        self.assertEqual(estancia.habitacion.estado, Habitacion.LIMPIEZA)

    def test_reserva_checkin_habitacion_ocupada_error(self):
        # Ocupar la habitación
        self.habitacion.estado = Habitacion.OCUPADA
        self.habitacion.save()
        
        # Intentar check-in
        checkin_url = reverse('reserva_checkin', kwargs={'reserva_id': self.reserva.id})
        response = self.client.post(checkin_url, {'habitacion': self.habitacion.id})
        
        # Debe redirigir con error y no cambiar el estado de la reserva
        self.assertEqual(response.status_code, 302)
        self.reserva.refresh_from_db()
        self.assertNotEqual(self.reserva.estado, Reserva.CHECKIN)

    def test_reserva_checkin_exceso_capacidad_error(self):
        # Crear un tipo de habitación Simple (capacidad 1)
        tipo_simple = TipoHabitacion.objects.create(
            hotel=self.hotel, nombre="Simple", capacidad=1, precio_base=Decimal("100.00")
        )
        habitacion_simple = Habitacion.objects.create(
            hotel=self.hotel, tipo=tipo_simple, numero="101", piso=1, estado=Habitacion.DISPONIBLE
        )
        
        # La reserva por defecto tiene num_adultos = 1, vamos a cambiarla a 2 (capacidad de Matrimonial = 2) y guardar
        self.reserva.num_adultos = 2
        self.reserva.save()
        
        # Intentar check-in asignando la habitación Simple (capacidad 1)
        checkin_url = reverse('reserva_checkin', kwargs={'reserva_id': self.reserva.id})
        response = self.client.post(checkin_url, {'habitacion': habitacion_simple.id})
        
        # Debe fallar y redirigir
        self.assertEqual(response.status_code, 302)
        self.reserva.refresh_from_db()
        self.assertNotEqual(self.reserva.estado, Reserva.CHECKIN)

    def test_agregar_cargo_estancia_finalizada_error(self):
        # Crear la estancia, folio y marcarla como finalizada
        estancia = Estancia.objects.create(
            reserva=self.reserva, habitacion=self.habitacion, precio_final=self.reserva.precio_total, estado=Estancia.FINALIZADA
        )
        # Intentar agregar un cargo
        cargo_url = reverse('agregar_cargo', kwargs={'estancia_id': estancia.id})
        response = self.client.post(cargo_url, {
            'concepto': 'Servicio extra',
            'monto': '10.00',
            'tipo': 'OTRO'
        })
        
        # Debe lanzar error (redirecciona) y no agregar el cargo
        self.assertEqual(response.status_code, 302)
        self.assertEqual(estancia.cargos.count(), 0)

    def test_cargo_monto_invalido_db(self):
        from django.db import IntegrityError
        estancia = Estancia.objects.create(
            reserva=self.reserva, habitacion=self.habitacion, precio_final=self.reserva.precio_total, estado=Estancia.ACTIVA
        )
        with self.assertRaises((IntegrityError, ValidationError)):
            CargoEstancia.objects.create(
                estancia=estancia, concepto="Monto Negativo", monto=Decimal("-10.00"), tipo=CargoEstancia.OTRO
            )

    def test_checkin_concurrente(self):
        import estancias.services as estancia_services
        usuario = User.objects.create_user(username='concurrente_user', password='password')
        self.habitacion.estado = Habitacion.DISPONIBLE
        self.habitacion.save()
        
        estancia1 = estancia_services.procesar_checkin(self.reserva.id, self.habitacion.id, usuario)
        self.assertIsNotNone(estancia1)
        
        reserva2 = Reserva.objects.create(
            hotel=self.hotel, huesped=self.huesped, habitacion=self.habitacion,
            fecha_entrada=date(2026, 9, 1), fecha_salida=date(2026, 9, 5),
            modalidad=Reserva.POR_DIA, estado=Reserva.CONFIRMADA
        )
        with self.assertRaises(ValidationError):
            estancia_services.procesar_checkin(reserva2.id, self.habitacion.id, usuario)

    def test_walkin_atomico(self):
        self.reserva.delete()
        import estancias.services as estancia_services
        usuario = User.objects.create_user(username='walkin_user', password='password')
        self.habitacion.estado = Habitacion.DISPONIBLE
        self.habitacion.save()
        
        estancia = estancia_services.hospedaje_directo_walkin(
            hotel_id=self.hotel.id,
            huesped_id=self.huesped.id,
            habitacion_id=self.habitacion.id,
            fecha_salida=date(2026, 8, 3),
            num_adultos=1,
            usuario=usuario
        )
        self.assertIsNotNone(estancia)
        self.assertEqual(estancia.habitacion.estado, Habitacion.OCUPADA)
        
        reserva_count_antes = Reserva.objects.count()
        with self.assertRaises(ValidationError):
            estancia_services.hospedaje_directo_walkin(
                hotel_id=self.hotel.id,
                huesped_id=self.huesped.id,
                habitacion_id=self.habitacion.id,
                fecha_salida=date(2026, 8, 3),
                num_adultos=5,
                usuario=usuario
            )
        reserva_count_despues = Reserva.objects.count()
        self.assertEqual(reserva_count_antes, reserva_count_despues)

    def test_cargos_duplicados_early_late(self):
        import estancias.services as estancia_services
        usuario = User.objects.create_user(username='early_late_user', password='password', is_staff=True)
        usuario.is_superuser = True
        usuario.save()

        self.hotel.cobrar_early_checkin = True
        self.hotel.early_checkin_tipo_cargo = 'FIJO'
        self.hotel.early_checkin_monto_porcentaje = Decimal('50.00')
        self.hotel.early_checkin_tolerancia_minutos = 10
        self.hotel.permitir_early_checkin = True
        self.hotel.save()

        self.habitacion.estado = Habitacion.DISPONIBLE
        self.habitacion.save()

        # Set dates to tomorrow so early check-in is globally triggered
        hoy = timezone.localdate()
        self.reserva.fecha_entrada = hoy + timedelta(days=1)
        self.reserva.fecha_salida = hoy + timedelta(days=3)
        self.reserva.save()
        
        estancia = estancia_services.procesar_checkin(self.reserva.id, self.habitacion.id, usuario)
        
        cargos = estancia.cargos.filter(concepto__icontains="Early Check-In")
        self.assertTrue(cargos.exists())
        
        self.hotel.permitir_late_checkout = True
        self.hotel.late_checkout_tipo_cargo = 'FIJO'
        self.hotel.late_checkout_monto_porcentaje = Decimal('30.00')
        self.hotel.late_checkout_tolerancia_minutos = 5
        self.hotel.save()
        
        # Shift the reservation dates to the past to trigger a late check-out without violating validation constraints
        self.reserva.fecha_entrada = hoy - timedelta(days=3)
        self.reserva.fecha_salida = hoy - timedelta(days=1)
        self.reserva.save()
        
        estancia.estado = Estancia.ACTIVA
        estancia.save()
        
        # Reload relation components from database to resolve caches
        estancia = Estancia.objects.get(id=estancia.id)
        
        folio = estancia.folio
        folio.calcular_totales()
        Pago.objects.create(folio=folio, monto=folio.saldo_pendiente, metodo_pago=Pago.EFECTIVO)
        
        estancia_services.procesar_checkout(
            estancia.id, usuario,
            exonerar_late_checkout=True, motivo_exoneracion_late="Exonerado por cortesía comercial"
        )
        
        late_cargos_count = estancia.cargos.filter(concepto__icontains="Salida Tardía").count()
        self.assertEqual(late_cargos_count, 1)

    def test_exoneracion_motivo_obligatorio(self):
        import estancias.services as estancia_services
        usuario = User.objects.create_user(username='exonerar_user', password='password')
        usuario.is_superuser = True
        usuario.save()

        self.hotel.cobrar_early_checkin = True
        self.hotel.early_checkin_tipo_cargo = 'FIJO'
        self.hotel.early_checkin_monto_porcentaje = Decimal('50.00')
        self.hotel.early_checkin_tolerancia_minutos = 10
        self.hotel.save()
        
        self.habitacion.estado = Habitacion.DISPONIBLE
        self.habitacion.save()

        # Set dates to tomorrow so early check-in is globally triggered
        hoy = timezone.localdate()
        self.reserva.fecha_entrada = hoy + timedelta(days=1)
        self.reserva.fecha_salida = hoy + timedelta(days=3)
        self.reserva.save()

        with self.assertRaises(ValidationError):
            estancia_services.procesar_checkin(
                self.reserva.id, self.habitacion.id, usuario,
                exonerar_early=True, motivo_exoneracion_early=""
            )

    def test_conflictos_extender_estancia(self):
        import estancias.services as estancia_services
        usuario = User.objects.create_user(username='extend_user', password='password')

        self.habitacion.estado = Habitacion.DISPONIBLE
        self.habitacion.save()
        estancia = estancia_services.procesar_checkin(self.reserva.id, self.habitacion.id, usuario)

        Reserva.objects.create(
            hotel=self.hotel, huesped=self.huesped, habitacion=self.habitacion,
            fecha_entrada=date(2026, 8, 6), fecha_salida=date(2026, 8, 10),
            modalidad=Reserva.POR_DIA, estado=Reserva.CONFIRMADA
        )

        with self.assertRaises(ValidationError):
            estancia_services.extender_estancia_activa(estancia.id, date(2026, 8, 8), usuario)

    def test_fallos_atomicos_cambio_habitacion(self):
        import estancias.services as estancia_services
        usuario = User.objects.create_user(username='room_change_user', password='password')

        self.habitacion.estado = Habitacion.DISPONIBLE
        self.habitacion.save()
        estancia = estancia_services.procesar_checkin(self.reserva.id, self.habitacion.id, usuario)

        hab_destino = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_hab, numero="303", piso=3, estado=Habitacion.OCUPADA
        )

        with self.assertRaises(ValidationError):
            estancia_services.cambiar_habitacion_activo(estancia.id, hab_destino.id, "Traslado de prueba", usuario)

        estancia.refresh_from_db()
        self.assertEqual(estancia.habitacion.numero, "204")

    def test_auditoria_sin_duplicados(self):
        import estancias.services as estancia_services
        from reportes.models import Auditoria
        usuario = User.objects.create_user(username='audit_user', password='password')
        self.habitacion.estado = Habitacion.DISPONIBLE
        self.habitacion.save()
        
        auditorias_antes = Auditoria.objects.filter(accion="Check-In Realizado").count()
        estancia = estancia_services.procesar_checkin(self.reserva.id, self.habitacion.id, usuario)
        
        auditorias_despues = Auditoria.objects.filter(accion="Check-In Realizado").count()
        self.assertEqual(auditorias_despues - auditorias_antes, 1)
