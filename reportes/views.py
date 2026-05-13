from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from hotel.models import Habitacion
from estancias.models import Estancia


class OcupacionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        fecha_str = request.query_params.get('fecha')
        if fecha_str:
            from datetime import datetime
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        else:
            fecha = timezone.now().date()

        total = Habitacion.objects.count()
        ocupadas = Habitacion.objects.filter(estado=Habitacion.OCUPADA).count()
        tasa = round((ocupadas / total * 100), 1) if total > 0 else 0

        estancias_activas = Estancia.objects.filter(
            estado='ACTIVA',
            fecha_checkin__date=fecha
        ).select_related('habitacion__tipo')

        revenue_por_tipo = {}
        for estancia in estancias_activas:
            tipo = estancia.habitacion.tipo.nombre
            revenue_por_tipo[tipo] = revenue_por_tipo.get(tipo, 0) + float(estancia.precio_final)

        return Response({
            'fecha': fecha,
            'total_habitaciones': total,
            'habitaciones_ocupadas': ocupadas,
            'tasa_ocupacion': tasa,
            'revenue_por_tipo': revenue_por_tipo,
        })
