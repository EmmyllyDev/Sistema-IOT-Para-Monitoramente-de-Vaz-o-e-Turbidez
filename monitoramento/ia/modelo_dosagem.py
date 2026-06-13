"""
Módulo de ML para recomendação de dosagem de coagulante.

Fluxo:
  - Com menos de MIN_AMOSTRAS registros com feedback → usa fórmula especialista (cold start)
  - Com dados suficientes → treina RandomForest e retorna predição com explicação
"""

import os
import pickle
import numpy as np

MIN_AMOSTRAS = 20  # mínimo de feedbacks para ativar o ML

MODELO_PATH = os.path.join(os.path.dirname(__file__), 'modelo_treinado.pkl')

FEATURES = [
    'turbidez_bruta_ntu',
    'turbidez_ntu',
    'cor_bruta_uh',
    'cor_uh',
    'ph_bruto',
    'ph',
    'cloro_residual_mgl',
    'vazao_m3_dia',
]


# ── Fórmula especialista (cold start) ──────────────────────────────────────

def _dosagem_por_formula(turbidez_bruta, ph_bruto, vazao_m3_dia):
    """
    Estimativa baseada em conhecimento técnico de ETA:
    - Base: 1 mg/L de sulfato para cada NTU de turbidez bruta
    - Ajuste de pH: água ácida precisa de mais coagulante
    - Ajuste de vazão: dosagem proporcional à produção
    """
    if turbidez_bruta is None or turbidez_bruta <= 0:
        return None, None

    dose_base = turbidez_bruta * 1.0  # mg/L por NTU

    # Ajuste pH: fora da faixa ótima (6,5–7,5) aumenta necessidade
    fator_ph = 1.0
    if ph_bruto is not None:
        if ph_bruto < 6.5:
            fator_ph = 1.2
        elif ph_bruto > 7.5:
            fator_ph = 1.15

    dose_estimada = round(dose_base * fator_ph, 1)
    dose_estimada = max(5.0, min(dose_estimada, 80.0))  # limites práticos

    justificativa = (
        f"Estimativa baseada em fórmula especialista: "
        f"turbidez bruta de {turbidez_bruta:.1f} NTU "
        f"{'com ajuste de pH aplicado ' if fator_ph != 1.0 else ''}"
        f"→ {dose_estimada} mg/L de sulfato de alumínio. "
        f"(Modo inicial — o modelo aprenderá com os feedbacks dos operadores)"
    )
    return dose_estimada, justificativa


# ── Treinamento ─────────────────────────────────────────────────────────────

def treinar_modelo():
    """
    Treina RandomForestRegressor com os registros que têm dosagem_aplicada_mgl.
    Salva o modelo em disco. Retorna (modelo, n_amostras).
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()

    from monitoramento.models import LeituraSensor

    qs = LeituraSensor.objects.exclude(dosagem_aplicada_mgl=None).values(*FEATURES, 'dosagem_aplicada_mgl')
    registros = list(qs)

    if len(registros) < MIN_AMOSTRAS:
        return None, len(registros)

    X, y = [], []
    for r in registros:
        linha = [r.get(f) or 0.0 for f in FEATURES]
        X.append(linha)
        y.append(r['dosagem_aplicada_mgl'])

    X = np.array(X)
    y = np.array(y)

    modelo = Pipeline([
        ('scaler', StandardScaler()),
        ('rf', RandomForestRegressor(n_estimators=100, random_state=42)),
    ])
    modelo.fit(X, y)

    with open(MODELO_PATH, 'wb') as f:
        pickle.dump({'modelo': modelo, 'n_amostras': len(registros)}, f)

    return modelo, len(registros)


def _carregar_modelo():
    if not os.path.exists(MODELO_PATH):
        return None, 0
    with open(MODELO_PATH, 'rb') as f:
        dados = pickle.load(f)
    return dados['modelo'], dados['n_amostras']


# ── Interface principal ──────────────────────────────────────────────────────

def recomendar_dosagem(leitura):
    """
    Recebe um objeto LeituraSensor e retorna:
        {
            'dose_mgl': float,
            'modo': 'ml' | 'formula',
            'n_amostras': int,
            'justificativa': str,
        }
    Retorna None se não houver dados suficientes para estimar.
    """
    from monitoramento.models import LeituraSensor

    n_feedbacks = LeituraSensor.objects.exclude(dosagem_aplicada_mgl=None).count()

    # Com feedbacks suficientes: tenta usar ou treinar o modelo
    if n_feedbacks >= MIN_AMOSTRAS:
        modelo, n_treino = _carregar_modelo()

        # Retreina se o modelo está desatualizado (mais 10 registros novos)
        if modelo is None or n_feedbacks >= n_treino + 10:
            modelo, n_treino = treinar_modelo()

        if modelo is not None:
            entrada = np.array([[
                getattr(leitura, f) or 0.0 for f in FEATURES
            ]])
            dose = round(float(modelo.predict(entrada)[0]), 1)
            dose = max(5.0, min(dose, 80.0))

            # Importância das features para explicar a predição
            rf = modelo.named_steps['rf']
            importancias = sorted(
                zip(FEATURES, rf.feature_importances_),
                key=lambda x: x[1], reverse=True
            )
            fator_principal = importancias[0][0].replace('_', ' ')

            justificativa = (
                f"Modelo treinado com {n_treino} registros reais. "
                f"Principal fator considerado: {fator_principal}. "
                f"Dose recomendada: {dose} mg/L de sulfato de alumínio."
            )
            return {'dose_mgl': dose, 'modo': 'ml', 'n_amostras': n_treino, 'justificativa': justificativa}

    # Cold start: fórmula especialista
    dose, justificativa = _dosagem_por_formula(
        leitura.turbidez_bruta_ntu,
        leitura.ph_bruto,
        leitura.vazao_m3_dia,
    )
    if dose is None:
        return None

    return {'dose_mgl': dose, 'modo': 'formula', 'n_amostras': n_feedbacks, 'justificativa': justificativa}
