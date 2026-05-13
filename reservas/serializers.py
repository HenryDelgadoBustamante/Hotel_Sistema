from rest_framework import serializers
from .models import Reserva, Tarifa
from huespedes.serializers import HuespedSerializer
from hotel.serializers import HabitacionSerializer


class TarifaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tarifa
        fields = '__all__'


class ReservaSerializer(serializers.ModelSerializer):
    huesped_detalle = HuespedSerializer(source='huesped', read_only=True)
    habitacion_detalle = HabitacionSerializer(source='habitacion', read_only=True)
    noches = serializers.SerializerMethodField()

    class Meta:
        model = Reserva
        fields = '__all__'

    def get_noches(self, obj):
        return (obj.fecha_salida - obj.fecha_entrada).days

    def validate(self, data):
        fecha_entrada = data.get('fecha_entrada')
        fecha_salida = data.get('fecha_salida')
        if fecha_entrada and fecha_salida:
            if fecha_salida <= fecha_entrada:
                raise serializers.ValidationError('La fecha de salida debe ser posterior a la de entrada.')
        return data
