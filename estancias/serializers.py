# Serializadores de datos de cuentas
from rest_framework import serializers
from .models import Estancia, CargoEstancia, Folio, Pago, Reembolso


class CargoEstanciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CargoEstancia
        fields = '__all__'


class FolioSerializer(serializers.ModelSerializer):
    cargos = CargoEstanciaSerializer(source='estancia.cargos', many=True, read_only=True)

    class Meta:
        model = Folio
        fields = '__all__'


class EstanciaSerializer(serializers.ModelSerializer):
    cargos = CargoEstanciaSerializer(many=True, read_only=True)
    folio = FolioSerializer(read_only=True)

    class Meta:
        model = Estancia
        fields = '__all__'


class PagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pago
        fields = '__all__'


class ReembolsoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reembolso
        fields = '__all__'
