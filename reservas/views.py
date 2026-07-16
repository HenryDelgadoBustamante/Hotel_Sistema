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
        habitacion_id = request.data.get('habitacion_id') or (reserva.habitacion.id if reserva.habitacion else None)
        exonerar_early = request.data.get('exonerar_early') in [True, 'true', 'True', 'on']
        motivo_early = request.data.get('motivo_exoneracion_early')

        import estancias.services as estancia_services
        from django.core.exceptions import ValidationError

        try:
            estancia = estancia_services.procesar_checkin(
                reserva_id=reserva.id,
                habitacion_id=habitacion_id,
                usuario=request.user,
                exonerar_early=exonerar_early,
                motivo_exoneracion_early=motivo_early
            )
            return Response({
                'mensaje': 'Check-in realizado correctamente',
                'estancia_id': estancia.id,
                'habitacion': estancia.habitacion.numero
            })
        except ValidationError as e:
            return Response(
                {'error': e.message if hasattr(e, 'message') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

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

