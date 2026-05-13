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
        if self.action in ['checkout', 'agregar_cargo']:
            return [EsRecepcionista()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'], url_path='checkout')
    def checkout(self, request, pk=None):
        estancia = self.get_object()
        try:
            estancia.hacer_checkout()
            return Response({'mensaje': 'Check-out realizado correctamente'})
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='cargos')
    def agregar_cargo(self, request, pk=None):
        estancia = self.get_object()
        serializer = CargoEstanciaSerializer(data={**request.data, 'estancia': estancia.id})
        if serializer.is_valid():
            serializer.save()
            folio, _ = Folio.objects.get_or_create(estancia=estancia)
            folio.calcular_totales()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='folio')
    def ver_folio(self, request, pk=None):
        estancia = self.get_object()
        folio, _ = Folio.objects.get_or_create(estancia=estancia)
        folio.calcular_totales()
        serializer = FolioSerializer(folio)
        return Response(serializer.data)
