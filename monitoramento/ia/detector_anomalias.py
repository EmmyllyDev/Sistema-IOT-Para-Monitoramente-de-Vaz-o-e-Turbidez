"""
Detecção de anomalias usando Isolation Forest.
Identifica leituras fora do padrão histórico com base nos parâmetros
físico-químicos da água tratada e bruta.
"""
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

MIN_AMOSTRAS = 30  # mínimo para treinar o detector

FEATURES = [
    'turbidez_ntu',
    'ph',
    'cloro_residual_mgl',
    'cor_uh',
    'turbidez_bruta_ntu',
    'ph_bruto',
]

LIMITES_PORTARIA = {
    'turbidez_ntu':      (0.0,  5.0),
    'ph':                (6.0,  9.5),
    'cloro_residual_mgl':(0.2,  5.0),
    'cor_uh':            (0.0, 15.0),
}


def _extrair_vetor(leitura):
    row = []
    for feat in FEATURES:
        val = getattr(leitura, feat, None)
        row.append(float(val) if val is not None else np.nan)
    return row


def _carregar_historico():
    from monitoramento.models import LeituraSensor
    qs = LeituraSensor.objects.exclude(horario=None).order_by('-horario')[:500]
    matriz = []
    for l in qs:
        row = _extrair_vetor(l)
        if not all(np.isnan(v) for v in row):
            # preenche NaN com mediana da coluna (feito depois)
            matriz.append(row)
    return np.array(matriz, dtype=float)


def _imputar_mediana(X):
    for col in range(X.shape[1]):
        col_vals = X[:, col]
        nan_mask = np.isnan(col_vals)
        if nan_mask.all():
            X[:, col] = 0.0
        elif nan_mask.any():
            X[nan_mask, col] = np.nanmedian(col_vals)
    return X


def detectar(leitura):
    """
    Retorna dict com:
      - anomalia: bool
      - score: float (mais negativo = mais anômalo)
      - alertas: list[str] — descrições legíveis das anomalias
      - modo: 'isolation_forest' | 'regras'
    """
    alertas = _verificar_regras(leitura)

    from monitoramento.models import LeituraSensor
    n_amostras = LeituraSensor.objects.exclude(horario=None).count()

    if n_amostras < MIN_AMOSTRAS:
        return {
            'anomalia': len(alertas) > 0,
            'score': None,
            'alertas': alertas,
            'modo': 'regras',
            'n_amostras': n_amostras,
        }

    X = _carregar_historico()
    if len(X) < MIN_AMOSTRAS:
        return {
            'anomalia': len(alertas) > 0,
            'score': None,
            'alertas': alertas,
            'modo': 'regras',
            'n_amostras': len(X),
        }

    X = _imputar_mediana(X)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    clf = IsolationForest(contamination=0.05, random_state=42, n_estimators=100)
    clf.fit(X_scaled)

    vetor = np.array([_extrair_vetor(leitura)], dtype=float)
    vetor = _imputar_mediana(vetor)
    vetor_scaled = scaler.transform(vetor)

    predicao = clf.predict(vetor_scaled)[0]   # 1=normal, -1=anomalia
    score = clf.score_samples(vetor_scaled)[0]

    anomalia_ml = predicao == -1

    if anomalia_ml and not alertas:
        alertas.append(
            "Combinação incomum de parâmetros detectada pelo modelo de anomalias — "
            "valores individuais parecem normais, mas o padrão geral é atípico."
        )

    return {
        'anomalia': anomalia_ml or len(alertas) > 0,
        'score': round(float(score), 4),
        'alertas': alertas,
        'modo': 'isolation_forest',
        'n_amostras': len(X),
    }


def _verificar_regras(leitura):
    alertas = []
    for campo, (minimo, maximo) in LIMITES_PORTARIA.items():
        valor = getattr(leitura, campo, None)
        if valor is None:
            continue
        valor = float(valor)
        if valor < minimo or valor > maximo:
            nome = {
                'turbidez_ntu':       'Turbidez tratada',
                'ph':                 'pH tratado',
                'cloro_residual_mgl': 'Cloro residual livre',
                'cor_uh':             'Cor aparente',
            }[campo]
            alertas.append(
                f"{nome}: {valor} fora do limite ({minimo}–{maximo} "
                f"{'NTU' if 'turbidez' in campo else 'mg/L' if 'cloro' in campo else 'uH' if 'cor' in campo else ''})"
                .replace("  ", " ").strip()
            )

    # Variação brusca entre bruta e tratada
    if leitura.turbidez_bruta_ntu and leitura.turbidez_ntu:
        eficiencia = 1 - (leitura.turbidez_ntu / leitura.turbidez_bruta_ntu)
        if eficiencia < 0.5 and leitura.turbidez_bruta_ntu > 10:
            alertas.append(
                f"Eficiência de remoção de turbidez baixa: {eficiencia*100:.0f}% "
                f"(bruta {leitura.turbidez_bruta_ntu} NTU → tratada {leitura.turbidez_ntu} NTU)"
            )

    return alertas
