"""Conversão de altura na calha Parshall para vazão — ETA II.

A tabela abaixo é a transcrição da que está afixada na estação. Ela relaciona
a altura lida (cm) com a vazão correspondente (L/s), e é a referência usada
pelo sensor ultrassônico instalado sobre a calha.

Entre dois pontos da tabela a vazão é interpolada linearmente. Abaixo de
10 cm a interpolação parte de (0 cm, 0 L/s), já que sem lâmina d'água não
há vazão. Acima de 80 cm — último ponto da tabela — o valor é extrapolado
pela inclinação do último trecho, porque o nível máximo da calha (92 cm)
passa do que a tabela cobre.
"""

# (altura em cm, vazão em L/s)
TABELA_ETA_II = [
    (10.0,  10),
    (15.0,  30),
    (20.0,  50),
    (22.5,  60),
    (25.0,  70),
    (27.5,  80),
    (30.0,  90),
    (32.5, 105),
    (35.0, 115),
    (37.5, 130),
    (40.0, 140),
    (42.5, 155),
    (45.0, 170),
    (47.5, 185),
    (50.0, 200),
    (52.5, 215),
    (55.0, 230),
    (57.5, 250),
    (60.0, 265),
    (62.5, 280),
    (65.0, 295),
    (67.5, 315),
    (70.0, 330),
    (72.5, 350),
    (75.0, 370),
    (77.5, 390),
    (80.0, 410),
]

# Altura máxima que a calha comporta.
NIVEL_MAXIMO_CM = 92.0

# Último ponto medido na tabela: acima disso o valor é extrapolado.
NIVEL_TABELADO_MAX_CM = TABELA_ETA_II[-1][0]


def vazao_por_nivel(cm):
    """Converte a altura lida na calha (cm) em vazão (L/s).

    Devolve None quando não há leitura. Valores negativos viram 0.
    O resultado é arredondado em uma casa decimal.
    """
    if cm is None:
        return None

    try:
        altura = float(cm)
    except (TypeError, ValueError):
        return None

    if altura <= 0:
        return 0.0

    primeira_altura, primeira_vazao = TABELA_ETA_II[0]

    # Abaixo da tabela: parte de (0 cm, 0 L/s).
    if altura < primeira_altura:
        return round(altura / primeira_altura * primeira_vazao, 1)

    # Dentro da tabela: interpolação linear entre os dois pontos vizinhos.
    for (a1, v1), (a2, v2) in zip(TABELA_ETA_II, TABELA_ETA_II[1:]):
        if a1 <= altura <= a2:
            if a2 == a1:
                return round(float(v1), 1)
            fracao = (altura - a1) / (a2 - a1)
            return round(v1 + fracao * (v2 - v1), 1)

    # Acima da tabela: segue a inclinação do último trecho.
    (penultima_altura, penultima_vazao), (ultima_altura, ultima_vazao) = TABELA_ETA_II[-2:]
    inclinacao = (ultima_vazao - penultima_vazao) / (ultima_altura - penultima_altura)
    return round(ultima_vazao + (altura - ultima_altura) * inclinacao, 1)


def acima_da_tabela(cm):
    """Diz se a altura passa do último ponto medido na tabela da ETA."""
    if cm is None:
        return False
    try:
        return float(cm) > NIVEL_TABELADO_MAX_CM
    except (TypeError, ValueError):
        return False
