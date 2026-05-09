from rest_framework import serializers
from .models import (
    GeneratedAsset, Agent,
    TerminosCondiciones, PoliticaPrivacidad
)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Agent
        fields = ('email', 'password', 'nombre', 'telefono', 'agencia')

    def create(self, validated_data):
        user = Agent.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            nombre=validated_data['nombre'],
            telefono=validated_data.get('telefono', ''),
            agencia=validated_data.get('agencia', '')
        )
        return user


class GeneratedAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedAsset
        fields = '__all__'


class TerminosCondicionesSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerminosCondiciones
        fields = ['id', 'titulo', 'contenido', 'version', 'fecha_actualizacion']


class PoliticaPrivacidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PoliticaPrivacidad
        fields = ['id', 'titulo', 'contenido', 'version', 'fecha_actualizacion']
