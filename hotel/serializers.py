from rest_framework import serializers
from .models import Hotel, TipoHabitacion, Habitacion


class TipoHabitacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoHabitacion
        fields = '__all__'


class HabitacionSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source='tipo.nombre', read_only=True)

    class Meta:
        model = Habitacion
        fields = '__all__'


class HabitacionDisponibleSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source='tipo.nombre', read_only=True)
    precio_base = serializers.DecimalField(source='tipo.precio_base', max_digits=10, decimal_places=2, read_only=True)
    capacidad = serializers.IntegerField(source='tipo.capacidad', read_only=True)

    class Meta:
        model = Habitacion
        fields = ['id', 'numero', 'piso', 'estado', 'tipo', 'tipo_nombre', 'precio_base', 'capacidad']


class HotelSerializer(serializers.ModelSerializer):
    habitaciones_count = serializers.SerializerMethodField()

    class Meta:
        model = Hotel
        fields = '__all__'

    def get_habitaciones_count(self, obj):
        return obj.habitaciones.count()
