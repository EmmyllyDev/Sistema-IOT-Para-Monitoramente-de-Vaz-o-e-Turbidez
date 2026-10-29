import secrets

from django.db import models


def _novo_token():
    """Token aleatório para o ESP32 autenticar na API."""
    return secrets.token_urlsafe(32)


class ConfiguracaoSistema(models.Model):
    """Configuração da instalação. Existe uma linha só, de id 1."""

    token_sensor = models.CharField(
        verbose_name="Token do sensor",
        max_length=64,
        default=_novo_token,
        help_text="Enviado pelo ESP32 no cabeçalho Authorization.",
    )
    token_gerado_em = models.DateTimeField(
        verbose_name="Token gerado em", auto_now_add=True, null=True, blank=True
    )

    class Meta:
        db_table = 'configuracao_sigua'
        verbose_name = 'Configuração do sistema'
        verbose_name_plural = 'Configurações do sistema'

    def __str__(self):
        return 'Configuração do SIGUÁ'

    @classmethod
    def obter(cls):
        """Devolve a configuração, criando-a na primeira chamada."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def regerar_token(self):
        from django.utils import timezone
        self.token_sensor = _novo_token()
        self.token_gerado_em = timezone.now()
        self.save(update_fields=['token_sensor', 'token_gerado_em'])
        return self.token_sensor

class LeituraSensor(models.Model):
    ORIGEM_SENSOR = 'sensor'
    ORIGEM_OPERADOR = 'operador'
    ORIGEM_CHOICES = [
        (ORIGEM_SENSOR, 'Sensor'),
        (ORIGEM_OPERADOR, 'Operador'),
    ]

    RESERVATORIO_METALICO = 'metalico'
    RESERVATORIO_CONCRETO = 'concreto'
    RESERVATORIO_CHOICES = [
        (RESERVATORIO_METALICO, 'Metálico'),
        (RESERVATORIO_CONCRETO, 'Concreto'),
    ]

    # Água tratada (coletada pelo operador via formulário ou ESP32)
    turbidez_ntu       = models.FloatField(verbose_name="Turbidez Tratada (NTU)", null=True, blank=True)
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
    origem = models.CharField(
        verbose_name="Origem da leitura",
        max_length=20,
        choices=ORIGEM_CHOICES,
        default=ORIGEM_OPERADOR,
        db_index=True,
        help_text="Sensor envia a cada 30 min; operador registra a cada 2 horas.",
    )
    tipo_reservatorio = models.CharField(
        verbose_name="Tipo de Reservatório",
        max_length=20,
        choices=RESERVATORIO_CHOICES,
        null=True, blank=True,
    )
    ponto_coleta = models.CharField(verbose_name="Ponto de Coleta", max_length=100, null=True, blank=True)
    operador     = models.CharField(verbose_name="Operador", max_length=150, null=True, blank=True)

    # Nulo significa "não avaliada": a leitura não trouxe nenhum parâmetro
    # da portaria. É o caso das leituras do sensor, que mandam só nível e
    # turbidez. Marcar isso como False diria que a água está fora do padrão,
    # que é afirmação diferente de "não dá para saber".
    status_conformidade = models.BooleanField(
        verbose_name="Dentro da Portaria 888?", null=True, blank=True)
    horario = models.DateTimeField(verbose_name="Horário da Leitura")

    # Feedback do operador — também alimenta o ML
    dosagem_aplicada_mgl = models.FloatField(verbose_name="Dosagem de Coagulante Aplicada (mg/L)", null=True, blank=True)
    sugestao_aceita      = models.BooleanField(verbose_name="Operador aceitou a sugestão?", null=True, blank=True)
    observacao_operador  = models.TextField(verbose_name="Observação do Operador", null=True, blank=True)

    class Meta:
        db_table = 'leituras_sigua'

    def __str__(self):
        if self.status_conformidade is None:
            selo = '— não avaliada'
        else:
            selo = '✅ OK' if self.status_conformidade else '❌ ALERTA'
        return f"Turbidez: {self.turbidez_ntu} | Status: {selo}"