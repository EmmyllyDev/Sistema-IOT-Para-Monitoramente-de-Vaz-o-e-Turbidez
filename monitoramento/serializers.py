from rest_framework import serializers
from .models import LeituraSensor

class LeituraSensorSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeituraSensor
        fields = '__all__'
        # Definidos pelo servidor, nunca pelo aparelho: o ESP32 não pode
        # forjar conformidade nem se declarar operador.
        read_only_fields = ['status_conformidade', 'horario', 'origem']