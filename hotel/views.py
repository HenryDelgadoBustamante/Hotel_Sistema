from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from datetime import datetime
from .models import Hotel, TipoHabitacion, Habitacion
from .serializers import HotelSerializer, TipoHabitacionSerializer, HabitacionSerializer, HabitacionDisponibleSerializer
from reservas.models import Reserva
from config.permissions import EsRecepcionista, EsHousekeeping, EsRecepcionistaOHousekeeping


class HotelViewSet(viewsets.ModelViewSet):
    queryset = Hotel.objects.all()
    serializer_class = HotelSerializer
    permission_classes = [IsAuthenticated]


class TipoHabitacionViewSet(viewsets.ModelViewSet):
    queryset = TipoHabitacion.objects.all()
    serializer_class = TipoHabitacionSerializer
    permission_classes = [IsAuthenticated]


class HabitacionViewSet(viewsets.ModelViewSet):
    queryset = Habitacion.objects.select_related('hotel', 'tipo').all()
    serializer_class = HabitacionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['estado', 'hotel', 'piso']

    def get_permissions(self):
        if self.action == 'housekeeping':
            return [EsRecepcionistaOHousekeeping()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'], url_path='disponibles')
    def disponibles(self, request):
        fecha_entrada = request.query_params.get('fecha_entrada')
        fecha_salida = request.query_params.get('fecha_salida')
        tipo = request.query_params.get('tipo')

        if not fecha_entrada or not fecha_salida:
            return Response(
                {'error': 'Se requieren fecha_entrada y fecha_salida'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            f_entrada = datetime.strptime(fecha_entrada, '%Y-%m-%d').date()
            f_salida = datetime.strptime(fecha_salida, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Formato de fecha inválido. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )

        estados_activos = [Reserva.PENDIENTE, Reserva.CONFIRMADA, Reserva.CHECKIN]
        habitaciones_ocupadas = Reserva.objects.filter(
            estado__in=estados_activos,
            fecha_entrada__lt=f_salida,
            fecha_salida__gt=f_entrada,
        ).values_list('habitacion_id', flat=True)

        habitaciones = Habitacion.objects.filter(
            estado=Habitacion.DISPONIBLE
        ).exclude(id__in=habitaciones_ocupadas)

        if tipo:
            habitaciones = habitaciones.filter(tipo_id=tipo)

        serializer = HabitacionDisponibleSerializer(habitaciones, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'], url_path='housekeeping')
    def housekeeping(self, request, pk=None):
        habitacion = self.get_object()
        nuevo_estado = request.data.get('estado')
        estados_validos = [Habitacion.DISPONIBLE, Habitacion.LIMPIEZA, Habitacion.MANTENIMIENTO]

        if nuevo_estado not in estados_validos:
            return Response(
                {'error': f'Estado inválido. Use: {estados_validos}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        habitacion.estado = nuevo_estado
        habitacion.save()
        return Response({'mensaje': f'Habitación {habitacion.numero} actualizada a {nuevo_estado}'})
