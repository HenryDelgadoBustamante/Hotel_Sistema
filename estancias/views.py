# Lógica operativa de cargos y folios
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from config.permissions import EsRecepcionista
from .models import Estancia, CargoEstancia, Folio
from .serializers import EstanciaSerializer, CargoEstanciaSerializer, FolioSerializer


class EstanciaViewSet(viewsets.ModelViewSet):
    queryset = Estancia.objects.select_related('reserva', 'habitacion').all()
    serializer_class = EstanciaSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['checkout', 'agregar_cargo', 'extender', 'cambiar_habitacion', 'walkin']:
            return [EsRecepcionista()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'], url_path='checkout')
    def checkout(self, request, pk=None):
        estancia = self.get_object()
        exonerar_late = request.data.get('exonerar_late_checkout') in [True, 'true', 'True', 'on']
        motivo_late = request.data.get('motivo_exoneracion_late')

        import estancias.services as estancia_services
        try:
            estancia_services.procesar_checkout(
                estancia_id=estancia.id,
                usuario=request.user,
                exonerar_late_checkout=exonerar_late,
                motivo_exoneracion_late=motivo_late
            )
            return Response({'mensaje': 'Check-out realizado correctamente'})
        except ValidationError as e:
            return Response({'error': e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='cargos')
    def agregar_cargo(self, request, pk=None):
        estancia = self.get_object()
        concepto = request.data.get('concepto')
        monto = request.data.get('monto')
        tipo = request.data.get('tipo', 'OTRO')

        if not concepto or not monto:
            return Response({'error': 'concepto y monto son requeridos'}, status=status.HTTP_400_BAD_REQUEST)

        import estancias.services as estancia_services
        from decimal import Decimal
        try:
            cargo = estancia_services.registrar_consumo(
                estancia_id=estancia.id,
                concepto=concepto,
                monto=Decimal(monto),
                tipo=tipo,
                usuario=request.user
            )
            return Response(CargoEstanciaSerializer(cargo).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({'error': e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='extender')
    def extender(self, request, pk=None):
        from datetime import date
        estancia = self.get_object()
        nueva_fecha_str = request.data.get('nueva_fecha_salida')
        if not nueva_fecha_str:
            return Response({'error': 'nueva_fecha_salida es requerida (YYYY-MM-DD)'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            nueva_fecha = date.fromisoformat(nueva_fecha_str)
        except ValueError:
            return Response({'error': 'Formato de fecha inválido, usar YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        import estancias.services as estancia_services
        try:
            estancia_services.extender_estancia_activa(
                estancia_id=estancia.id,
                nueva_fecha_salida=nueva_fecha,
                usuario=request.user
            )
            return Response({'mensaje': 'Estancia extendida correctamente'})
        except ValidationError as e:
            return Response({'error': e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='cambiar-habitacion')
    def cambiar_habitacion(self, request, pk=None):
        estancia = self.get_object()
        nueva_habitacion_id = request.data.get('nueva_habitacion_id')
        motivo = request.data.get('motivo')

        if not nueva_habitacion_id or not motivo:
            return Response({'error': 'nueva_habitacion_id y motivo son requeridos'}, status=status.HTTP_400_BAD_REQUEST)

        import estancias.services as estancia_services
        try:
            estancia_services.cambiar_habitacion_activo(
                estancia_id=estancia.id,
                nueva_habitacion_id=nueva_habitacion_id,
                motivo=motivo,
                usuario=request.user
            )
            return Response({'mensaje': 'Cambio de habitación completado correctamente'})
        except ValidationError as e:
            return Response({'error': e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='walkin')
    def walkin(self, request):
        hotel_id = request.data.get('hotel_id')
        huesped_id = request.data.get('huesped_id')
        habitacion_id = request.data.get('habitacion_id')
        fecha_salida_str = request.data.get('fecha_salida')
        num_adultos = request.data.get('num_adultos')

        if not all([hotel_id, huesped_id, habitacion_id, fecha_salida_str, num_adultos]):
            return Response({'error': 'hotel_id, huesped_id, habitacion_id, fecha_salida, y num_adultos son requeridos'}, status=status.HTTP_400_BAD_REQUEST)

        from datetime import date
        try:
            fecha_salida = date.fromisoformat(fecha_salida_str)
        except ValueError:
            return Response({'error': 'Formato de fecha inválido, usar YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        import estancias.services as estancia_services
        try:
            estancia = estancia_services.hospedaje_directo_walkin(
                hotel_id=hotel_id,
                huesped_id=huesped_id,
                habitacion_id=habitacion_id,
                fecha_salida=fecha_salida,
                num_adultos=int(num_adultos),
                usuario=request.user
            )
            return Response({
                'mensaje': 'Hospedaje directo registrado correctamente',
                'estancia_id': estancia.id
            }, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({'error': e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='folio')
    def ver_folio(self, request, pk=None):
        estancia = self.get_object()
        folio, _ = Folio.objects.get_or_create(estancia=estancia)
        folio.calcular_totales()
        serializer = FolioSerializer(folio)
        return Response(serializer.data)
