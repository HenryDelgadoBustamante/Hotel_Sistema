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
        Folio.objects.create(estancia=estancia)

        return Response({
            'mensaje': 'Check-in realizado correctamente',
            'estancia_id': estancia.id,
            'habitacion': habitacion.numero
        })
