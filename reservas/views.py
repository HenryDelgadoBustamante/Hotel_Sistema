# Controladores de la API REST para reservas
from datetime import date, datetime, time
from decimal import Decimal

from django.utils import timezone
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
        
        nueva_habitacion = serializer.validated_data.get('habitacion')
        if nueva_habitacion and nueva_habitacion != instance.habitacion:
            entrada = instance.fecha_hora_entrada or timezone.make_aware(datetime.combine(instance.fecha_entrada, time(15, 0)))
            salida = instance.fecha_hora_salida or timezone.make_aware(datetime.combine(instance.fecha_salida, time(12, 0)))
            
            solapadas = Reserva.objects.filter(
                habitacion=nueva_habitacion,
                estado__in=[Reserva.PENDIENTE, Reserva.CONFIRMADA, Reserva.CHECKIN],
                fecha_hora_entrada__lt=salida,
                fecha_hora_salida__gt=entrada
            ).exclude(pk=instance.pk)
            
            if solapadas.exists():
                from rest_framework.exceptions import ValidationError as DRFValidationError
                raise DRFValidationError('La nueva habitación no está disponible en ese rango de fechas.')

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

    @action(detail=False, methods=['get'])
    def disponibilidad(self, request):
        fecha_entrada = request.query_params.get('fecha_entrada')
        fecha_salida = request.query_params.get('fecha_salida')
        tipo_habitacion = request.query_params.get('tipo_habitacion')
        capacidad = request.query_params.get('capacidad')
        precio_min = request.query_params.get('precio_min')
        precio_max = request.query_params.get('precio_max')

        if not fecha_entrada or not fecha_salida:
            return Response({'error': 'fecha_entrada y fecha_salida son requeridos'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            entrada = date.fromisoformat(fecha_entrada)
            salida = date.fromisoformat(fecha_salida)
        except ValueError:
            return Response({'error': 'Formato de fecha inválido. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        if salida <= entrada:
            return Response({'error': 'La fecha de salida debe ser posterior a la de entrada'}, status=status.HTTP_400_BAD_REQUEST)

        qs = Habitacion.objects.filter(estado=Habitacion.DISPONIBLE)
        if tipo_habitacion:
            qs = qs.filter(tipo_id=tipo_habitacion)
        if capacidad:
            qs = qs.filter(tipo__capacidad__gte=capacidad)
        if precio_min:
            qs = qs.filter(tipo__precio_base__gte=precio_min)
        if precio_max:
            qs = qs.filter(tipo__precio_base__lte=precio_max)

        reservados_ids = Reserva.objects.filter(
            estado__in=[Reserva.PENDIENTE, Reserva.CONFIRMADA, Reserva.CHECKIN],
            fecha_entrada__lt=salida,
            fecha_salida__gt=entrada
        ).values_list('habitacion_id', flat=True)

        qs = qs.exclude(id__in=reservados_ids)

        from hotel.serializers import HabitacionSerializer
        serializer = HabitacionSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='pago_anticipado')
    def pago_anticipado(self, request, pk=None):
        reserva = self.get_object()

        if reserva.estado in [Reserva.CHECKIN, Reserva.CHECKOUT, Reserva.CANCELADA]:
            return Response(
                {'error': 'No se puede registrar pago en una reserva finalizada o cancelada'},
                status=status.HTTP_400_BAD_REQUEST
            )

        monto = request.data.get('monto')
        metodo_pago = request.data.get('metodo_pago')
        transaccion_id = request.data.get('transaccion_id', '')

        if not monto or not metodo_pago:
            return Response(
                {'error': 'monto y metodo_pago son requeridos'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            monto = Decimal(str(monto))
        except Exception:
            return Response(
                {'error': 'Monto inválido'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if monto <= 0:
            return Response(
                {'error': 'El monto debe ser mayor a cero'},
                status=status.HTTP_400_BAD_REQUEST
            )

        saldo = reserva.saldo_pendiente
        if monto > saldo:
            return Response(
                {'error': f'El monto no puede superar el saldo pendiente (S/.{saldo})'},
                status=status.HTTP_400_BAD_REQUEST
            )

        pago = Pago.objects.create(
            reserva=reserva,
            monto=monto,
            metodo_pago=metodo_pago,
            transaccion_id=transaccion_id
        )

        from reportes.models import registrar_auditoria
        registrar_auditoria(
            usuario=request.user,
            accion="Pago Anticipado Registrado",
            registro_id=pago.id,
            tabla_afectada="estancias_pago",
            estado_nuevo=f"Pago S/.{monto} ({metodo_pago}) - Reserva #{reserva.id}"
        )

        return Response({
            'mensaje': 'Pago anticipado registrado correctamente',
            'pago_id': pago.id,
            'saldo_pendiente': reserva.saldo_pendiente
        }, status=status.HTTP_201_CREATED)

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

        if reserva.habitacion:
            reserva.habitacion.estado = Habitacion.DISPONIBLE
            reserva.habitacion.save()

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

