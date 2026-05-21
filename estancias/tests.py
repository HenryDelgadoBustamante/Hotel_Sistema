from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
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
