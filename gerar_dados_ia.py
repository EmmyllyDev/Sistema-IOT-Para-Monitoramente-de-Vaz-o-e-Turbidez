"""Gera dados sintéticos de operação e valida as duas IAs do SIGUÁ.

Por que este script existe
──────────────────────────
As duas IAs só ligam com volume de dados, e hoje o banco não tem:

  - `modelo_dosagem` precisa de 20 leituras com `dosagem_aplicada_mgl`
    preenchido (o feedback do operador). Abaixo disso ele sempre cai na
    fórmula especialista e o RandomForest nunca roda.
  - `detector_anomalias` precisa de 30 leituras com horário. Abaixo disso
    ele só aplica as regras fixas e o Isolation Forest nunca roda.

Mas gerar número aleatório não valida nada. Para medir se a IA acerta,
é preciso saber a resposta certa. Então aqui a dosagem sai de uma função
latente conhecida — a "verdade" — e as anomalias são injetadas com
etiqueta. Depois o script compara o que a IA respondeu com o que foi
plantado, e isso é a validação.

O que é gerado
──────────────
Operação coerente, não ruído: a água bruta varia com a estação (chuva em
Mato Grosso suja o manancial), a dosagem responde à água bruta, e a água
tratada é consequência da dosagem. Subdosar piora a remoção. É essa
cadeia de causa e efeito que dá ao modelo algo real para aprender.

Uso
───
    python gerar_dados_ia.py                      # 240 leituras em 6 meses + validação
    python gerar_dados_ia.py --quantas 400 --meses 12
    python gerar_dados_ia.py --anomalias 0.15     # 15% de leituras com defeito
    python gerar_dados_ia.py --validar            # só valida o que já está no banco
    python gerar_dados_ia.py --limpar             # apaga o que este script criou

As leituras criadas levam `ponto_coleta = 'SIMULADO-IA'`, então aparecem
marcadas nas telas e o --limpar sabe exatamente o que apagar. As leituras
reais e as do sensor não são tocadas.
"""

import argparse
import math
import os
import random
import sys
from datetime import datetime, timedelta

import django

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(RAIZ, '.env'))
except ImportError:
    pass

# O console do Windows abre em cp1252 e estoura nos caracteres de moldura e
# nos acentos. Sem isso o script morre no primeiro print, não no erro real.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

import numpy as np

from monitoramento.models import LeituraSensor
from monitoramento.vazao import vazao_por_nivel

# Marca das leituras sintéticas. É por aqui que o --limpar as encontra.
MARCA = 'SIMULADO-IA'

OPERADORES = ['J. Ribeiro', 'M. Santana', 'A. Prado', 'C. Nogueira']

# Tipos de defeito injetados, com etiqueta — é contra esta etiqueta que a
# detecção é medida. O último é o único que as regras fixas não pegam.
TIPOS_ANOMALIA = [
    'turbidez_alta',
    'cloro_baixo',
    'cloro_alto',
    'ph_fora',
    'cor_alta',
    'coliformes',
    'remocao_baixa',
    'combinacao_atipica',
]

DESCRICAO_ANOMALIA = {
    'turbidez_alta':       'Falha de filtro — turbidez tratada acima de 5 NTU',
    'cloro_baixo':         'Bomba de cloro parada — residual abaixo de 0,2 mg/L',
    'cloro_alto':          'Sobredosagem de cloro — residual acima de 5 mg/L',
    'ph_fora':             'Falha na cal — pH fora da faixa 6,0–9,5',
    'cor_alta':            'Coagulação ruim — cor aparente acima de 15 uH',
    'coliformes':          'Contaminação — presença de coliformes totais',
    'remocao_baixa':       'Tratamento ineficaz — remoção de turbidez abaixo de 50%',
    'combinacao_atipica':  'Cada valor dentro do limite, mas a combinação é atípica',
}


# ══════════════════════════════════════════════════════════════════════
#  A verdade: como a dosagem realmente é decidida
# ══════════════════════════════════════════════════════════════════════

def dosagem_verdadeira(turbidez_bruta, cor_bruta, ph_bruto, alcalinidade, vazao_m3_dia):
    """Dosagem de sulfato que um bom operador aplicaria, em mg/L.

    Esta é a função latente que o modelo tem que descobrir. Ela foi feita
    de propósito **diferente** da fórmula especialista do sistema, que usa
    1 mg/L por NTU de forma linear. Aqui a resposta é sublinear na turbidez
    (expoente 0,72), como o ensaio de jarros mostra na prática: dobrar a
    turbidez não dobra o coagulante.

    Essa diferença é o que torna a validação honesta. Se o RandomForest
    só empatasse com a fórmula, não haveria motivo para existir; o que se
    mede aqui é se ele captura a curvatura que a fórmula erra.
    """
    base = 2.9 * (turbidez_bruta ** 0.72)

    # Cor tem contribuição própria: matéria orgânica consome coagulante
    # mesmo quando a turbidez está baixa.
    base += 0.055 * cor_bruta

    # Água ácida ou de baixa alcalinidade coagula pior e pede mais.
    if ph_bruto < 6.8:
        base *= 1.0 + (6.8 - ph_bruto) * 0.17
    if alcalinidade < 25:
        base *= 1.0 + (25 - alcalinidade) * 0.011

    # Vazão alta reduz o tempo de contato: um pouco mais de dose.
    base *= 1.0 + max(vazao_m3_dia - 15000, 0) / 90000.0

    # Variação entre operadores e entre bateladas. Sem isso o alvo seria
    # determinístico e qualquer modelo acertaria em cheio — o que mediria
    # a memorização, não a capacidade de prever.
    base *= random.gauss(1.0, 0.06)

    return round(max(5.0, min(base, 80.0)), 1)


def formula_especialista(turbidez_bruta, ph_bruto):
    """A fórmula que o sistema usa no cold start — serve de baseline.

    Replicada aqui (de `ia/modelo_dosagem.py`) para comparar o erro dela
    com o erro do modelo treinado, nos mesmos dados.
    """
    if turbidez_bruta is None or turbidez_bruta <= 0:
        return None
    fator = 1.0
    if ph_bruto is not None:
        if ph_bruto < 6.5:
            fator = 1.2
        elif ph_bruto > 7.5:
            fator = 1.15
    return float(max(5.0, min(turbidez_bruta * fator, 80.0)))


# ══════════════════════════════════════════════════════════════════════
#  Geração de uma leitura
# ══════════════════════════════════════════════════════════════════════

def _fator_chuva(mes):
    """Quanto o manancial está sujo neste mês, de 0 (seca) a 1 (cheia).

    Em Mato Grosso a estação chuvosa vai de novembro a março. Um cosseno
    centrado em janeiro dá a transição suave em vez de um degrau.
    """
    return 0.5 * (1 + math.cos(2 * math.pi * (mes - 1) / 12.0))


def gerar_leitura(quando, anomalia=None):
    """Monta uma leitura coerente. `anomalia` é um dos TIPOS_ANOMALIA."""
    chuva = _fator_chuva(quando.month)

    # ── Água bruta ──
    # Lognormal porque turbidez tem cauda longa: a maioria dos dias é
    # calma e alguns poucos, depois de chuva forte, disparam.
    base_bruta = 9 + 46 * chuva
    turbidez_bruta = round(min(base_bruta * random.lognormvariate(0, 0.42), 180.0), 1)

    # Cor acompanha a turbidez, mas não é a mesma coisa.
    cor_bruta = round(max(turbidez_bruta * random.uniform(1.6, 2.8), 5.0), 1)
    ph_bruto = round(random.gauss(6.95 - 0.35 * chuva, 0.22), 2)
    ph_bruto = max(5.8, min(ph_bruto, 7.8))
    alcalinidade_bruta = round(random.uniform(16, 48), 1)

    # ── Vazão: nível na calha, convertido pela tabela da ETA ──
    nivel_cm = round(random.uniform(28, 74), 1)
    vazao_ls = vazao_por_nivel(nivel_cm)
    vazao_m3_dia = round(vazao_ls * 86.4, 1)

    # ── Dosagem aplicada (o feedback do operador) ──
    dose_ideal = dosagem_verdadeira(turbidez_bruta, cor_bruta, ph_bruto,
                                    alcalinidade_bruta, vazao_m3_dia)
    dose_aplicada = dose_ideal

    # Em parte dos turnos o operador erra a mão. É isso que depois
    # explica a piora da água tratada.
    if random.random() < 0.18:
        dose_aplicada = round(max(5.0, dose_ideal * random.uniform(0.55, 0.85)), 1)
    elif random.random() < 0.10:
        dose_aplicada = round(min(80.0, dose_ideal * random.uniform(1.15, 1.45)), 1)

    # ── Água tratada é consequência da dosagem ──
    # Dose perto da ideal remove bem; subdosar derruba a remoção.
    adequacao = dose_aplicada / dose_ideal
    if adequacao >= 0.95:
        eficiencia = random.uniform(0.945, 0.988)
    elif adequacao >= 0.80:
        eficiencia = random.uniform(0.90, 0.955)
    else:
        eficiencia = random.uniform(0.72, 0.90)

    turbidez = round(max(turbidez_bruta * (1 - eficiencia), 0.08), 2)
    cor = round(max(cor_bruta * (1 - eficiencia * random.uniform(0.96, 1.02)), 1.0), 1)

    # O coagulante acidifica; a cal corrige. Sobra um resíduo de variação.
    ph = round(random.gauss(7.25, 0.26), 2)
    cloro = round(random.gauss(1.05, 0.26), 2)
    cloro = max(0.25, min(cloro, 2.4))
    coliformes = 0.0
    alcalinidade_tratada = round(max(alcalinidade_bruta * random.uniform(0.55, 0.85), 5.0), 1)

    # ── Injeção do defeito, quando for o caso ──
    if anomalia == 'turbidez_alta':
        turbidez = round(random.uniform(5.6, 16.0), 2)
    elif anomalia == 'cloro_baixo':
        cloro = round(random.uniform(0.0, 0.17), 2)
    elif anomalia == 'cloro_alto':
        cloro = round(random.uniform(5.3, 8.5), 2)
    elif anomalia == 'ph_fora':
        ph = round(random.choice([random.uniform(5.1, 5.9),
                                  random.uniform(9.7, 10.6)]), 2)
    elif anomalia == 'cor_alta':
        cor = round(random.uniform(16.5, 42.0), 1)
    elif anomalia == 'coliformes':
        coliformes = float(random.randint(1, 34))
    elif anomalia == 'remocao_baixa':
        # A regra de eficiência só dispara com bruta acima de 10 NTU.
        turbidez_bruta = round(random.uniform(42, 110), 1)
        cor_bruta = round(turbidez_bruta * random.uniform(1.6, 2.6), 1)
        turbidez = round(turbidez_bruta * random.uniform(0.52, 0.78), 2)
    elif anomalia == 'combinacao_atipica':
        # Nenhum valor viola limite — por isso as regras ficam caladas.
        # O que é estranho é o conjunto: água bruta limpíssima, dose alta,
        # cloro no topo da faixa e turbidez tratada bem acima do normal
        # para uma bruta tão limpa.
        turbidez_bruta = round(random.uniform(3.0, 6.5), 1)
        cor_bruta = round(random.uniform(6, 13), 1)
        turbidez = round(random.uniform(3.4, 4.9), 2)
        cor = round(random.uniform(11.5, 14.8), 1)
        cloro = round(random.uniform(4.2, 4.9), 2)
        ph = round(random.uniform(6.05, 6.3), 2)
        dose_aplicada = round(random.uniform(58, 78), 1)

    return {
        'horario': quando,
        'origem': LeituraSensor.ORIGEM_OPERADOR,
        'ponto_coleta': MARCA,
        'operador': random.choice(OPERADORES),
        'tipo_reservatorio': random.choice([LeituraSensor.RESERVATORIO_METALICO,
                                            LeituraSensor.RESERVATORIO_CONCRETO]),

        'turbidez_bruta_ntu': turbidez_bruta,
        'cor_bruta_uh': cor_bruta,
        'ph_bruto': ph_bruto,
        'alcalinidade_bruta': alcalinidade_bruta,

        'turbidez_ntu': turbidez,
        'cor_uh': cor,
        'ph': ph,
        'cloro_residual_mgl': cloro,
        'coliformes_ufc': coliformes,
        'alcalinidade_tratada': alcalinidade_tratada,

        'nivel_cm': nivel_cm,
        'vazao_ls': vazao_ls,
        'vazao_m3_dia': vazao_m3_dia,

        'sulfato_aluminio_kg': round(dose_aplicada * vazao_m3_dia / 1000.0, 2),
        'hipoclorito_sodio_kg': round(cloro * vazao_m3_dia / 1000.0 * 1.4, 2),

        'dosagem_aplicada_mgl': dose_aplicada,
        'sugestao_aceita': random.random() < 0.72,
        'observacao_operador': (
            f'[{MARCA}] {DESCRICAO_ANOMALIA[anomalia]}' if anomalia
            else f'[{MARCA}] Operação normal'
        ),
        '_anomalia': anomalia,
        '_dose_ideal': dose_ideal,
    }


# ══════════════════════════════════════════════════════════════════════
#  Gravação
# ══════════════════════════════════════════════════════════════════════

def gerar(quantas, meses, taxa_anomalia, semente):
    """Cria as leituras no banco e devolve o que foi plantado."""
    random.seed(semente)
    np.random.seed(semente)

    fim = datetime.now().replace(minute=0, second=0, microsecond=0)
    inicio = fim - timedelta(days=int(meses * 30.4))
    intervalo = (fim - inicio) / max(quantas, 1)

    quantas_anomalas = max(len(TIPOS_ANOMALIA), int(round(quantas * taxa_anomalia)))
    quantas_anomalas = min(quantas_anomalas, quantas)

    # Garante ao menos uma de cada tipo; o resto é sorteado. Sem isso,
    # um tipo poderia ficar sem nenhum exemplo e a medição daquele tipo
    # não existiria.
    rotulos = list(TIPOS_ANOMALIA)
    while len(rotulos) < quantas_anomalas:
        rotulos.append(random.choice(TIPOS_ANOMALIA))
    rotulos += [None] * (quantas - len(rotulos))
    random.shuffle(rotulos)

    plantadas = []
    objetos = []
    for i, rotulo in enumerate(rotulos):
        # Coleta a cada 2 horas, como o operador faz; com um desvio de
        # alguns minutos para o horário não ficar artificialmente exato.
        quando = inicio + intervalo * i + timedelta(minutes=random.randint(-14, 14))
        d = gerar_leitura(quando, rotulo)
        plantadas.append({'horario': d['horario'], 'anomalia': d['_anomalia'],
                          'dose_ideal': d['_dose_ideal']})
        campos = {k: v for k, v in d.items() if not k.startswith('_')}
        objetos.append(LeituraSensor(status_conformidade=_conforme(campos), **campos))

    LeituraSensor.objects.bulk_create(objetos, batch_size=200)

    for p, o in zip(plantadas, objetos):
        p['id'] = o.id
    return plantadas


def _conforme(c):
    """Conformidade pelos mesmos limites da Portaria usados nas telas."""
    testes = [
        c['turbidez_ntu'] <= 5.0,
        6.0 <= c['ph'] <= 9.5,
        0.2 <= c['cloro_residual_mgl'] <= 5.0,
        c['cor_uh'] <= 15.0,
        c['coliformes_ufc'] == 0,
    ]
    return all(testes)


# ══════════════════════════════════════════════════════════════════════
#  Validação
# ══════════════════════════════════════════════════════════════════════

def validar_dosagem():
    """Mede o erro do modelo de dosagem contra a dosagem realmente aplicada.

    Usa validação cruzada em 5 partes: o modelo nunca prevê um registro
    que viu no treino. E compara com a fórmula especialista nos mesmos
    dados, porque um erro só significa algo contra uma alternativa.
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import KFold, cross_val_predict
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    from monitoramento.ia.modelo_dosagem import FEATURES, MIN_AMOSTRAS

    qs = (LeituraSensor.objects.exclude(dosagem_aplicada_mgl=None)
          .values(*FEATURES, 'dosagem_aplicada_mgl'))
    registros = list(qs)

    print(f"\n{'═' * 68}")
    print("  1. MODELO DE DOSAGEM — RandomForestRegressor")
    print('═' * 68)
    print(f"  Registros com feedback do operador : {len(registros)}")
    print(f"  Mínimo para o ML ligar             : {MIN_AMOSTRAS}")

    if len(registros) < MIN_AMOSTRAS:
        print(f"\n  → O ML NÃO liga. O sistema usa a fórmula especialista.")
        print(f"    Faltam {MIN_AMOSTRAS - len(registros)} registros com dosagem aplicada.")
        return
    print(f"  → O ML liga.")

    X = np.array([[r.get(f) or 0.0 for f in FEATURES] for r in registros], dtype=float)
    y = np.array([r['dosagem_aplicada_mgl'] for r in registros], dtype=float)

    modelo = Pipeline([
        ('scaler', StandardScaler()),
        ('rf', RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)),
    ])
    pred = cross_val_predict(modelo, X, y,
                             cv=KFold(n_splits=5, shuffle=True, random_state=42))

    mae = mean_absolute_error(y, pred)
    rmse = math.sqrt(mean_squared_error(y, pred))
    r2 = r2_score(y, pred)

    print(f"\n  Validação cruzada k=5, alvo = dosagem realmente aplicada")
    print(f"    MAE  : {mae:5.2f} mg/L")
    print(f"    RMSE : {rmse:5.2f} mg/L")
    print(f"    R²   : {r2:6.4f}")
    print(f"    Dose média no período: {y.mean():.1f} mg/L "
          f"(erro de {mae / y.mean() * 100:.1f}%)")

    # Baseline: a fórmula do cold start, nos mesmos registros.
    i_tb = FEATURES.index('turbidez_bruta_ntu')
    i_ph = FEATURES.index('ph_bruto')
    base, alvo = [], []
    for linha, real in zip(X, y):
        f = formula_especialista(linha[i_tb], linha[i_ph])
        if f is not None:
            base.append(f)
            alvo.append(real)
    if base:
        mae_f = mean_absolute_error(alvo, base)
        print(f"\n  Baseline — fórmula especialista (1 mg/L por NTU)")
        print(f"    MAE  : {mae_f:5.2f} mg/L")
        if mae < mae_f:
            print(f"    → O modelo treinado erra {(1 - mae / mae_f) * 100:.0f}% menos "
                  f"que a fórmula. O ML se justifica.")
        else:
            print(f"    → A fórmula empata ou vence. O ML não está agregando "
                  f"nada aqui; reveja features ou volume de dados.")

    modelo.fit(X, y)
    importancias = modelo.named_steps['rf'].feature_importances_
    print(f"\n  O que o modelo usa para decidir:")
    for nome, imp in sorted(zip(FEATURES, importancias), key=lambda t: -t[1]):
        barra = '█' * int(round(imp * 40))
        print(f"    {nome:22} {imp * 100:5.1f}%  {barra}")


def validar_anomalias(plantadas):
    """Mede quantos defeitos plantados a IA encontrou, por tipo.

    Chama o `detectar()` do próprio sistema, não uma reimplementação:
    o que se valida é o caminho que o site usa de verdade.
    """
    from monitoramento.ia.detector_anomalias import detectar, MIN_AMOSTRAS

    n_hist = LeituraSensor.objects.exclude(horario=None).count()

    print(f"\n{'═' * 68}")
    print("  2. DETECTOR DE ANOMALIAS — Isolation Forest")
    print('═' * 68)
    print(f"  Leituras no histórico   : {n_hist}")
    print(f"  Mínimo para o ML ligar  : {MIN_AMOSTRAS}")
    if n_hist < MIN_AMOSTRAS:
        print(f"\n  → O Isolation Forest NÃO liga; só as regras fixas rodam.")
    else:
        print(f"  → O Isolation Forest liga.")

    if not plantadas:
        print("\n  Sem leituras plantadas nesta execução, nada a medir.")
        print("  Rode sem --validar para gerar dados com defeito etiquetado.")
        return

    ids = [p['id'] for p in plantadas]
    por_id = {p['id']: p['anomalia'] for p in plantadas}
    leituras = {l.id: l for l in LeituraSensor.objects.filter(id__in=ids)}

    print(f"\n  Avaliando {len(ids)} leituras uma por uma. O detector retreina")
    print(f"  a cada chamada, então isso leva alguns segundos.")

    acertos = {t: [0, 0] for t in TIPOS_ANOMALIA}   # [pegas, total]
    falso_positivo = 0
    normais = 0
    modos = {}

    for lid in ids:
        leitura = leituras.get(lid)
        if leitura is None:
            continue
        r = detectar(leitura)
        modos[r['modo']] = modos.get(r['modo'], 0) + 1
        rotulo = por_id[lid]
        if rotulo is None:
            normais += 1
            if r['anomalia']:
                falso_positivo += 1
        else:
            acertos[rotulo][1] += 1
            if r['anomalia']:
                acertos[rotulo][0] += 1

    print(f"\n  Modo usado: " + ', '.join(f"{k}={v}" for k, v in modos.items()))
    print(f"\n  {'Defeito plantado':22} {'Pegos':>12}   {'Taxa':>6}")
    print(f"  {'-' * 22} {'-' * 12}   {'-' * 6}")
    total_p = total_t = 0
    for tipo in TIPOS_ANOMALIA:
        pegos, total = acertos[tipo]
        if not total:
            continue
        total_p += pegos
        total_t += total
        taxa = pegos / total * 100
        marca = 'ok' if taxa >= 99 else ('--' if taxa < 50 else '~ ')
        print(f"  {tipo:22} {pegos:5}/{total:<6} {taxa:5.0f}%  {marca}")

    if total_t:
        print(f"  {'-' * 22} {'-' * 12}   {'-' * 6}")
        print(f"  {'TOTAL':22} {total_p:5}/{total_t:<6} "
              f"{total_p / total_t * 100:5.0f}%")

    if normais:
        print(f"\n  Falsos positivos: {falso_positivo} de {normais} leituras normais "
              f"({falso_positivo / normais * 100:.1f}%)")
        print(f"  O Isolation Forest roda com contamination=0,05, então ele")
        print(f"  marca ~5% do histórico como atípico por construção. Um valor")
        print(f"  nessa ordem é esperado, não defeito.")

    pegos_at, total_at = acertos['combinacao_atipica']
    if total_at:
        print(f"\n  O caso que mais importa é 'combinacao_atipica': {pegos_at} de "
              f"{total_at} pegos.")
        print(f"  Nele nenhum valor viola limite, então as regras fixas ficam")
        print(f"  caladas e quem acha é o Isolation Forest. Se esse número for")
        print(f"  zero, o modelo não está agregando nada sobre as regras.")

    print(f"\n  Ressalva de método: o detector treina nas últimas 500 leituras,")
    print(f"  incluindo a que está sendo avaliada. Isso favorece um pouco o")
    print(f"  resultado — é como o código de produção funciona, e a medição")
    print(f"  reflete o sistema real, não um cenário ideal.")


def validar_sugestoes(plantadas):
    """Confere que gerar_sugestoes() não quebra e produz texto coerente."""
    from monitoramento.sugestoes import gerar_sugestoes

    print(f"\n{'═' * 68}")
    print("  3. PAINEL DE SUGESTÕES — texto mostrado ao operador")
    print('═' * 68)

    if plantadas:
        ids = [p['id'] for p in plantadas if p['anomalia']][:3]
    else:
        ids = list(LeituraSensor.objects.exclude(horario=None)
                   .order_by('-horario').values_list('id', flat=True)[:3])
    if not ids:
        print("  Sem leituras para avaliar.")
        return

    for lid in ids:
        leitura = LeituraSensor.objects.get(id=lid)
        sugs = gerar_sugestoes(leitura)
        criticas = [s for s in sugs if s['status'] == 'critico']
        print(f"\n  Leitura {lid} — {len(sugs)} sugestões, "
              f"{len(criticas)} críticas")
        for s in sugs[:4]:
            print(f"    [{s['status']:8}] {s['parametro']}: {s['valor']}")


# ══════════════════════════════════════════════════════════════════════
#  Limpeza
# ══════════════════════════════════════════════════════════════════════

def limpar(sem_perguntar=False):
    qs = LeituraSensor.objects.filter(ponto_coleta=MARCA)
    n = qs.count()
    if not n:
        print(f"Nenhuma leitura com ponto_coleta='{MARCA}' no banco.")
        return
    if not sem_perguntar:
        if input(f"Apagar {n} leitura(s) sintética(s)? (digite sim) ").strip().lower() != 'sim':
            print("Nada apagado.")
            return
    qs.delete()
    print(f"{n} leitura(s) sintética(s) apagada(s).")

    # O modelo salvo foi treinado nos dados que acabaram de sair.
    caminho = os.path.join(RAIZ, 'monitoramento', 'ia', 'modelo_treinado.pkl')
    if os.path.exists(caminho):
        os.remove(caminho)
        print("modelo_treinado.pkl removido — foi treinado nos dados apagados.")


# ══════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description='Gera dados sintéticos e valida as IAs do SIGUÁ.')
    p.add_argument('--quantas', type=int, default=240,
                   help='Quantas leituras gerar (padrão 240)')
    p.add_argument('--meses', type=float, default=6,
                   help='Em quantos meses distribuir (padrão 6)')
    p.add_argument('--anomalias', type=float, default=0.12,
                   help='Fração com defeito, 0 a 1 (padrão 0,12)')
    p.add_argument('--semente', type=int, default=42,
                   help='Semente do sorteio — repetir o número repete os dados')
    p.add_argument('--validar', action='store_true',
                   help='Só valida o que já está no banco, sem gerar nada')
    p.add_argument('--limpar', action='store_true',
                   help='Apaga as leituras sintéticas e sai')
    p.add_argument('--sim', action='store_true',
                   help='Não pedir confirmação no --limpar')
    a = p.parse_args()

    if a.limpar:
        limpar(a.sim)
        return

    if not 0 <= a.anomalias < 1:
        p.error('--anomalias precisa estar entre 0 e 1')

    print('═' * 68)
    print('  SIGUÁ — dados sintéticos e validação das IAs')
    print('═' * 68)

    plantadas = []
    if a.validar:
        print(f"\nModo --validar: nada foi gerado.")
        print(f"Leituras no banco: {LeituraSensor.objects.count()}")
    else:
        ja_tem = LeituraSensor.objects.filter(ponto_coleta=MARCA).count()
        if ja_tem:
            print(f"\nJá existem {ja_tem} leitura(s) sintética(s) no banco.")
            print(f"Rode --limpar antes se quiser começar do zero; "
                  f"senão as novas somam às antigas.")
        print(f"\nGerando {a.quantas} leituras em {a.meses:g} meses, "
              f"{a.anomalias * 100:g}% com defeito (semente {a.semente})...")
        plantadas = gerar(a.quantas, a.meses, a.anomalias, a.semente)
        com_defeito = sum(1 for x in plantadas if x['anomalia'])
        print(f"{len(plantadas)} gravadas — {com_defeito} com defeito etiquetado, "
              f"{len(plantadas) - com_defeito} normais.")
        print(f"Marcadas com ponto_coleta='{MARCA}'.")

    validar_dosagem()
    validar_anomalias(plantadas)
    validar_sugestoes(plantadas)

    print(f"\n{'═' * 68}")
    print("  Para apagar estes dados antes de usar o sistema de verdade:")
    print("    python gerar_dados_ia.py --limpar")
    print('═' * 68)


if __name__ == '__main__':
    main()
