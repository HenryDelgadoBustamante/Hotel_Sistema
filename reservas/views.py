# Controladores de la API REST para reservas
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from config.permissions import EsRecepcionista
from .models import Reserva, Tarifa
from .serializers import ReservaSerializer, TarifaSerializer
from hotel.models import Habitacion
from estancias.models import Estancia, Folio


class TarifaViewSet(viewsets.ModelViewSet):
    queryset = Tarifa.objects.all()
    serializer_class = TarifaSerializer
    permission_classes = [IsAuthenticated]


class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.select_related('huesped', 'habitacion', 'hotel').all()
    serializer_class = ReservaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['estado', 'hotel', 'fecha_entrada']

    def get_permissions(self):
        if self.action in ['checkin', 'create', 'update', 'partial_update']:
            return [EsRecepcionista()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        reserva = serializer.save()
        precio = reserva.calcular_precio()
        reserva.precio_total = precio
        reserva.save()

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.estado in [Reserva.CHECKIN, Reserva.CHECKOUT, Reserva.CANCELADA]:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError('No se puede modificar una reserva en estado check-in, check-out o cancelada.')
        reserva = serializer.save()
        reserva.precio_total = reserva.calcular_precio()
        reserva.save()

    def perform_destroy(self, instance):
        if instance.estado in [Reserva.CHECKIN, Reserva.CHECKOUT, Reserva.CANCELADA]:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError('No se puede eliminar una reserva en estado check-in, check-out o cancelada.')
        instance.delete()

    @action(detail=True, methods=['post'], url_path='checkin')
    def checkin(self, request, pk=None):
        reserva = self.get_object()

        if reserva.estado not in [Reserva.PENDIENTE, Reserva.CONFIRMADA]:
            return Response(
                {'error': 'La reserva no está en estado válido para check-in'},
                status=status.HTTP_400_BAD_REQUEST
            )

        habitacion = reserva.habitacion
        if not habitacion:
            habitacion_id = request.data.get('habitacion_id')
            if not habitacion_id:
                return Response(
                    {'error': 'Se requiere habitacion_id para el check-in'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                habitacion = Habitacion.objects.get(id=habitacion_id)
            except Habitacion.DoesNotExist:
                return Response({'error': 'Habitación no encontrada'}, status=status.HTTP_404_NOT_FOUND)

        if habitacion.estado in [Habitacion.MANTENIMIENTO, Habitacion.LIMPIEZA]:
            return Response(
                {'error': f'No se puede hacer check-in. Habitación en estado: {habitacion.estado}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        habitacion.estado = Habitacion.OCUPADA
        habitacion.save()
        reserva.habitacion = habitacion
        reserva.estado = Reserva.CHECKIN
        reserva.save()

        estancia = Estancia.objects.create(
            reserva=reserva,
            habitacion=habitacion,
            precio_final=reserva.precio_total
        )
        folio = Folio.objects.create(estancia=estancia)

        from estancias.models import Pago
        Pago.objects.filter(reserva=reserva, folio__isnull=True).update(folio=folio)
        folio.calcular_totales()

        return Response({
            'mensaje': 'Check-in realizado correctamente',
            'estancia_id': estancia.id,
            'habitacion': habitacion.numero
        })

    @action(detail=True, methods=['post'], url_path='cancelar')
    def cancelar(self, request, pk=None):
        reserva = self.get_object()

        if reserva.estado in [Reserva.CHECKIN, Reserva.CHECKOUT, Reserva.CANCELADA]:
            return Response(
                {'error': 'No se puede cancelar una reserva en estado check-in, check-out o cancelada'},
                status=status.HTTP_400_BAD_REQUEST
            )

        motivo = request.data.get('motivo_cancelacion', '').strip()
        if not motivo:
            return Response(
                {'error': 'Debes ingresar un motivo de cancelación'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reserva.estado = Reserva.CANCELADA
        reserva.motivo_cancelacion = motivo
        reserva.save()

        # Registrar auditoria
        from reportes.models import registrar_auditoria
        registrar_auditoria(
            usuario=request.user,
            accion="Cancelar Reserva",
            registro_id=reserva.id,
            tabla_afectada="reservas_reserva",
            estado_nuevo=f"Estado: CANCELADA, Motivo: {motivo}"
        )

        return Response({'mensaje': 'Reserva cancelada correctamente'})

