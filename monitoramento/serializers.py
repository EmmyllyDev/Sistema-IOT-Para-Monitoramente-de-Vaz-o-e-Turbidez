from rest_framework import serializers
from .models import LeituraSensor

class LeituraSensorSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeituraSensor
        fields = '__all__'
        # Avisamos o Django que o ESP32 não precisa enviar esses dois campos no JSON
        read_only_fields = ['status_conformidade', 'horario']