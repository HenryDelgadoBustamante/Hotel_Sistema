# Serializadores REST para huéspedes
from rest_framework import serializers
from .models import Huesped


class HuespedSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.CharField(read_only=True)

    class Meta:
        model = Huesped
        fields = '__all__'
