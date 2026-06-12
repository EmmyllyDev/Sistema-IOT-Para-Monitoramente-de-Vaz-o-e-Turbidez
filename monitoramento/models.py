from django.db import models

class LeituraSensor(models.Model):
    turbidez_ntu = models.FloatField(verbose_name="Turbidez (NTU)")
    vazao_ls = models.FloatField(verbose_name="Vazão (L/s)")
    nivel_cm = models.FloatField(verbose_name="Nível (cm)")
    
    status_conformidade = models.BooleanField(verbose_name="Dentro da Portaria 888?")
    
    horario = models.DateTimeField(auto_now_add=True, verbose_name="Horário da Leitura")
    class Meta:
        # Isso avisa o Django para usar a tabela que você já tinha criado!
        db_table = 'leituras_sigua'
        
    def __str__(self):
        return f"Turbidez: {self.turbidez_ntu} | Status: {'✅ OK' if self.status_conformidade else '❌ ALERTA'}"