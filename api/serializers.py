from rest_framework import serializers
from .models import (
    GeneratedAsset, Agent, ComercialAgentProfile,
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


class ComercialAgentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComercialAgentProfile
        fields = [
            'id',
            'nombre',
            'rol',
            'email',
            'telefono_e164',
            'foto_url',
            'is_default',
            'activo',
            'creado_en',
            'updated_at',
        ]
        read_only_fields = ['id', 'creado_en', 'updated_at']

    def validate_telefono_e164(self, value):
        if value in (None, ''):
            return None

        phone = str(value).strip().replace(' ', '').replace('-', '')
        if not phone.startswith('+'):
            phone = f'+{phone}'

        import re
        if not re.match(r'^\+[1-9]\d{6,14}$', phone):
            raise serializers.ValidationError('telefono_e164 debe estar en formato E.164 (ej: +5491123456789).')

        return phone
