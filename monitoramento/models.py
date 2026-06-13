from django.db import models

class LeituraSensor(models.Model):
    # Água tratada (coletada pelo operador via formulário ou ESP32)
    turbidez_ntu       = models.FloatField(verbose_name="Turbidez Tratada (NTU)")
    vazao_ls           = models.FloatField(verbose_name="Vazão (L/s)", null=True, blank=True)
    nivel_cm           = models.FloatField(verbose_name="Nível (cm)", null=True, blank=True)
    ph                 = models.FloatField(verbose_name="pH Tratado", null=True, blank=True)
    cloro_residual_mgl = models.FloatField(verbose_name="Cloro Residual Livre (mg/L)", null=True, blank=True)
    coliformes_ufc     = models.FloatField(verbose_name="Coliformes Totais (UFC/100mL)", null=True, blank=True)
    cor_uh             = models.FloatField(verbose_name="Cor Aparente Tratada (uH)", null=True, blank=True)
    alcalinidade_tratada = models.FloatField(verbose_name="Alcalinidade Tratada", null=True, blank=True)

    # Água bruta (antes do tratamento)
    turbidez_bruta_ntu  = models.FloatField(verbose_name="Turbidez Bruta (NTU)", null=True, blank=True)
    cor_bruta_uh        = models.FloatField(verbose_name="Cor Bruta (uH)", null=True, blank=True)
    ph_bruto            = models.FloatField(verbose_name="pH Bruto", null=True, blank=True)
    alcalinidade_bruta  = models.FloatField(verbose_name="Alcalinidade Bruta", null=True, blank=True)

    # Dosagens aplicadas (insumos do tratamento) — base para o ML
    sulfato_aluminio_kg    = models.FloatField(verbose_name="Sulfato de Alumínio (Kg)", null=True, blank=True)
    policloreto_aluminio_l = models.FloatField(verbose_name="Policloreto de Alumínio (L)", null=True, blank=True)
    hipoclorito_sodio_kg   = models.FloatField(verbose_name="Hipoclorito de Sódio (Kg)", null=True, blank=True)

    # Vazão diária (M³/dia) — vinda do relatório Excel
    vazao_m3_dia = models.FloatField(verbose_name="Vazão de Entrada (M³/dia)", null=True, blank=True)

    # Identificação da coleta
    ponto_coleta = models.CharField(verbose_name="Ponto de Coleta", max_length=100, null=True, blank=True)
    operador     = models.CharField(verbose_name="Operador", max_length=150, null=True, blank=True)

    status_conformidade = models.BooleanField(verbose_name="Dentro da Portaria 888?")
    horario = models.DateTimeField(verbose_name="Horário da Leitura")

    # Feedback do operador — também alimenta o ML
    dosagem_aplicada_mgl = models.FloatField(verbose_name="Dosagem de Coagulante Aplicada (mg/L)", null=True, blank=True)
    sugestao_aceita      = models.BooleanField(verbose_name="Operador aceitou a sugestão?", null=True, blank=True)
    observacao_operador  = models.TextField(verbose_name="Observação do Operador", null=True, blank=True)

    class Meta:
        db_table = 'leituras_sigua'

    def __str__(self):
        return f"Turbidez: {self.turbidez_ntu} | Status: {'✅ OK' if self.status_conformidade else '❌ ALERTA'}"