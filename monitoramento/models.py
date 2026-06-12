from django.db import models

class LeituraSensor(models.Model):
    # Campos originais
    turbidez_ntu = models.FloatField(verbose_name="Turbidez (NTU)")
    vazao_ls     = models.FloatField(verbose_name="Vazão (L/s)")
    nivel_cm     = models.FloatField(verbose_name="Nível (cm)")

    # Novos parâmetros físico-químicos (Portaria GM/MS 888/2021)
    ph                 = models.FloatField(verbose_name="pH", null=True, blank=True)
    cloro_residual_mgl = models.FloatField(verbose_name="Cloro Residual Livre (mg/L)", null=True, blank=True)
    coliformes_ufc     = models.FloatField(verbose_name="Coliformes Totais (UFC/100mL)", null=True, blank=True)
    cor_uh             = models.FloatField(verbose_name="Cor Aparente (uH)", null=True, blank=True)

    # Identificação da coleta
    ponto_coleta = models.CharField(verbose_name="Ponto de Coleta", max_length=100, null=True, blank=True)
    operador     = models.CharField(verbose_name="Operador", max_length=150, null=True, blank=True)

    status_conformidade = models.BooleanField(verbose_name="Dentro da Portaria 888?")
    horario = models.DateTimeField(auto_now_add=True, verbose_name="Horário da Leitura")

    class Meta:
        db_table = 'leituras_sigua'

    def __str__(self):
        return f"Turbidez: {self.turbidez_ntu} | Status: {'✅ OK' if self.status_conformidade else '❌ ALERTA'}"