"""
Script de avaliação do modelo de ML — SIGUA
Gera métricas e gráficos para o artigo do PSI.

Execução:
    python avaliar_modelo.py

Saída:
    resultados/metricas_resumo.txt
    resultados/grafico_real_vs_predito.png
    resultados/importancia_features.png
    resultados/distribuicao_anomalias.png
    resultados/curva_aprendizado.png
"""

import os
import sys
import django
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

from monitoramento.models import LeituraSensor
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_predict, KFold, learning_curve
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

os.makedirs('resultados', exist_ok=True)

FEATURES = [
    'turbidez_bruta_ntu',
    'turbidez_ntu',
    'ph_bruto',
    'ph',
    'cloro_residual_mgl',
    'vazao_m3_dia',
]

FEATURES_LABELS = {
    'turbidez_bruta_ntu': 'Turbidez Bruta (NTU)',
    'turbidez_ntu':       'Turbidez Tratada (NTU)',
    'ph_bruto':           'pH Bruto',
    'ph':                 'pH Tratado',
    'cloro_residual_mgl': 'Cloro Residual (mg/L)',
    'vazao_m3_dia':       'Vazão de Entrada (M³/dia)',
}

COLORS = {
    'azul':    '#2563eb',
    'verde':   '#16a34a',
    'laranja': '#d97706',
    'vermelho':'#dc2626',
    'cinza':   '#94a3b8',
    'fundo':   '#f8fafc',
}

plt.rcParams.update({
    'font.family': 'sans-serif',
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.grid': True,
    'grid.alpha': 0.3,
    'figure.facecolor': 'white',
})


def _formula(turbidez_bruta, ph_bruto):
    if turbidez_bruta is None or turbidez_bruta <= 0:
        return None
    fator_ph = 1.0
    if ph_bruto is not None:
        if ph_bruto < 6.5:
            fator_ph = 1.2
        elif ph_bruto > 7.5:
            fator_ph = 1.15
    dose = turbidez_bruta * 1.0 * fator_ph
    return float(max(5.0, min(dose, 80.0)))


def carregar_dados():
    qs = LeituraSensor.objects.exclude(turbidez_bruta_ntu=None).exclude(ph_bruto=None)
    registros = []
    for l in qs:
        alvo = _formula(l.turbidez_bruta_ntu, l.ph_bruto)
        if alvo is None:
            continue
        linha = []
        for f in FEATURES:
            val = getattr(l, f, None)
            linha.append(float(val) if val is not None else np.nan)
        registros.append((linha, alvo))

    X = np.array([r[0] for r in registros])
    y = np.array([r[1] for r in registros])

    # Imputar medianas nas colunas com NaN
    for col in range(X.shape[1]):
        mask = np.isnan(X[:, col])
        if mask.any():
            X[mask, col] = np.nanmedian(X[:, col])

    return X, y


# ══════════════════════════════════════════════════════════════
# 1. MÉTRICAS DE REGRESSÃO (RandomForest com validação cruzada)
# ══════════════════════════════════════════════════════════════
print("Carregando dados...")
X, y = carregar_dados()
print(f"  {len(X)} registros com dados suficientes para avaliacao")

modelo = Pipeline([
    ('scaler', StandardScaler()),
    ('rf', RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)),
])

kf = KFold(n_splits=5, shuffle=True, random_state=42)
y_pred = cross_val_predict(modelo, X, y, cv=kf)

mae  = mean_absolute_error(y, y_pred)
rmse = np.sqrt(mean_squared_error(y, y_pred))
r2   = r2_score(y, y_pred)

print(f"\n=== METRICAS DE REGRESSAO (validacao cruzada k=5) ===")
print(f"  MAE  (Erro Medio Absoluto): {mae:.2f} mg/L")
print(f"  RMSE (Raiz do Erro Quad.):  {rmse:.2f} mg/L")
print(f"  R2   (Coef. Determinacao):  {r2:.4f}")


# ══════════════════════════════════════════════════════════════
# 2. TREINO COMPLETO — importância das features
# ══════════════════════════════════════════════════════════════
modelo.fit(X, y)
rf = modelo.named_steps['rf']
importancias = rf.feature_importances_
indices = np.argsort(importancias)[::-1]


# ══════════════════════════════════════════════════════════════
# 3. ISOLATION FOREST — scores de anomalia
# ══════════════════════════════════════════════════════════════
scaler_iso = StandardScaler()
X_scaled = scaler_iso.fit_transform(X)
iso = IsolationForest(contamination=0.05, random_state=42, n_estimators=100)
iso.fit(X_scaled)
scores_anomalia = iso.score_samples(X_scaled)
predicoes_iso   = iso.predict(X_scaled)
n_anomalas = (predicoes_iso == -1).sum()

print(f"\n=== ISOLATION FOREST ===")
print(f"  Total de registros:  {len(X)}")
print(f"  Anomalias detectadas: {n_anomalas} ({n_anomalas/len(X)*100:.1f}%)")
print(f"  Score medio: {scores_anomalia.mean():.4f}")
print(f"  Score min:   {scores_anomalia.min():.4f}")
print(f"  Score max:   {scores_anomalia.max():.4f}")


# ══════════════════════════════════════════════════════════════
# GRÁFICO 1 — Real vs Predito
# ══════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(7, 6))
normais  = predicoes_iso == 1
anomalas = predicoes_iso == -1

ax.scatter(y[normais],  y_pred[normais],  alpha=0.55, s=30,
           color=COLORS['azul'],    label='Normal', edgecolors='none')
ax.scatter(y[anomalas], y_pred[anomalas], alpha=0.85, s=50,
           color=COLORS['vermelho'], label='Anomalia (ISO Forest)',
           edgecolors='white', linewidths=0.5, zorder=5)

lim = [min(y.min(), y_pred.min()) - 2, max(y.max(), y_pred.max()) + 2]
ax.plot(lim, lim, '--', color=COLORS['cinza'], linewidth=1.5, label='Predição perfeita')
ax.set_xlim(lim); ax.set_ylim(lim)

ax.set_xlabel('Dosagem Real — Fórmula Especialista (mg/L)', fontsize=10)
ax.set_ylabel('Dosagem Predita — RandomForest (mg/L)', fontsize=10)
ax.set_title('Dosagem Real vs Predita\n(Validação cruzada k=5)', fontsize=12, fontweight='bold')
ax.legend(fontsize=9)

info = f'MAE={mae:.2f}  RMSE={rmse:.2f}  R²={r2:.3f}\nn={len(X)} registros'
ax.text(0.03, 0.97, info, transform=ax.transAxes, fontsize=9,
        va='top', ha='left',
        bbox=dict(boxstyle='round,pad=0.4', facecolor='#eff6ff', alpha=0.8))

plt.tight_layout()
plt.savefig('resultados/grafico_real_vs_predito.png', dpi=150, bbox_inches='tight')
plt.close()
print("\nSalvo: resultados/grafico_real_vs_predito.png")


# ══════════════════════════════════════════════════════════════
# GRÁFICO 2 — Importância das Features
# ══════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(8, 4.5))
labels = [FEATURES_LABELS.get(FEATURES[i], FEATURES[i]) for i in indices]
vals   = importancias[indices]
bars   = ax.barh(labels[::-1], vals[::-1],
                 color=[COLORS['azul'] if v == vals.max() else COLORS['cinza'] for v in vals[::-1]],
                 edgecolor='none', height=0.55)

for bar, val in zip(bars, vals[::-1]):
    ax.text(bar.get_width() + 0.002, bar.get_y() + bar.get_height()/2,
            f'{val*100:.1f}%', va='center', fontsize=9, color='#334155')

ax.set_xlabel('Importância relativa (%)', fontsize=10)
ax.set_title('Importância das Features — RandomForest\n(Predição de dosagem de coagulante)', fontsize=12, fontweight='bold')
ax.xaxis.set_major_formatter(ticker.PercentFormatter(xmax=1.0))
ax.set_xlim(0, vals.max() * 1.2)
plt.tight_layout()
plt.savefig('resultados/importancia_features.png', dpi=150, bbox_inches='tight')
plt.close()
print("Salvo: resultados/importancia_features.png")


# ══════════════════════════════════════════════════════════════
# GRÁFICO 3 — Distribuição de Scores de Anomalia
# ══════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(8, 4.5))
scores_norm = scores_anomalia[predicoes_iso ==  1]
scores_anom = scores_anomalia[predicoes_iso == -1]

ax.hist(scores_norm, bins=30, color=COLORS['azul'],    alpha=0.7, label=f'Normal ({len(scores_norm)})', edgecolor='none')
ax.hist(scores_anom, bins=10, color=COLORS['vermelho'], alpha=0.8, label=f'Anomalia ({len(scores_anom)})', edgecolor='none')

threshold = scores_anomalia[predicoes_iso == -1].max()
ax.axvline(threshold, color=COLORS['laranja'], linestyle='--', linewidth=1.5, label=f'Limiar de anomalia')

ax.set_xlabel('Score de Anomalia (Isolation Forest)', fontsize=10)
ax.set_ylabel('Frequência', fontsize=10)
ax.set_title('Distribuição de Scores — Isolation Forest\n(Detecção de anomalias nas leituras)', fontsize=12, fontweight='bold')
ax.legend(fontsize=9)
plt.tight_layout()
plt.savefig('resultados/distribuicao_anomalias.png', dpi=150, bbox_inches='tight')
plt.close()
print("Salvo: resultados/distribuicao_anomalias.png")


# ══════════════════════════════════════════════════════════════
# GRÁFICO 4 — Curva de Aprendizado
# ══════════════════════════════════════════════════════════════
train_sizes, train_scores, val_scores = learning_curve(
    modelo, X, y,
    cv=5, scoring='neg_mean_absolute_error',
    train_sizes=np.linspace(0.1, 1.0, 10),
    n_jobs=-1
)
train_mae = -train_scores.mean(axis=1)
val_mae   = -val_scores.mean(axis=1)
train_std = train_scores.std(axis=1)
val_std   = val_scores.std(axis=1)

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(train_sizes, train_mae, 'o-', color=COLORS['azul'],    label='Treino (MAE)',   linewidth=2)
ax.plot(train_sizes, val_mae,   's-', color=COLORS['laranja'], label='Validação (MAE)', linewidth=2)
ax.fill_between(train_sizes, train_mae - train_std, train_mae + train_std, alpha=0.15, color=COLORS['azul'])
ax.fill_between(train_sizes, val_mae   - val_std,   val_mae   + val_std,   alpha=0.15, color=COLORS['laranja'])

ax.set_xlabel('Número de amostras de treino', fontsize=10)
ax.set_ylabel('MAE (mg/L)', fontsize=10)
ax.set_title('Curva de Aprendizado — RandomForest\n(MAE em função do tamanho do conjunto de treino)', fontsize=12, fontweight='bold')
ax.legend(fontsize=9)
plt.tight_layout()
plt.savefig('resultados/curva_aprendizado.png', dpi=150, bbox_inches='tight')
plt.close()
print("Salvo: resultados/curva_aprendizado.png")


# ══════════════════════════════════════════════════════════════
# ARQUIVO DE TEXTO — resumo completo para o artigo
# ══════════════════════════════════════════════════════════════
with open('resultados/metricas_resumo.txt', 'w', encoding='utf-8') as f:
    f.write("=" * 60 + "\n")
    f.write("SIGUA — AVALIACAO DO MODELO DE ML\n")
    f.write("PSI — Projeto de Sistemas Inteligentes\n")
    f.write("ETA Julio Campos — DAE Varzea Grande/MT\n")
    f.write("=" * 60 + "\n\n")

    f.write("1. REGRESSAO — Predicao de Dosagem de Coagulante\n")
    f.write("-" * 45 + "\n")
    f.write(f"   Algoritmo:       RandomForestRegressor\n")
    f.write(f"   Validacao:       K-Fold (k=5, shuffle=True)\n")
    f.write(f"   N de registros:  {len(X)}\n")
    f.write(f"   Variavel alvo:   Dosagem de sulfato de aluminio (mg/L)\n")
    f.write(f"   Baseline:        Formula especialista (turbidez bruta x fator pH)\n\n")
    f.write(f"   MAE  (Erro Medio Absoluto):     {mae:.4f} mg/L\n")
    f.write(f"   RMSE (Raiz do Erro Quadratico): {rmse:.4f} mg/L\n")
    f.write(f"   R2   (Coef. de Determinacao):   {r2:.4f}\n\n")

    f.write("   Importancia das Features:\n")
    for i in indices:
        label = FEATURES_LABELS.get(FEATURES[i], FEATURES[i])
        f.write(f"   {label:<35} {importancias[i]*100:.2f}%\n")

    f.write("\n2. DETECCAO DE ANOMALIAS — Isolation Forest\n")
    f.write("-" * 45 + "\n")
    f.write(f"   Algoritmo:          IsolationForest\n")
    f.write(f"   Contamination:      5%\n")
    f.write(f"   N estimators:       100\n")
    f.write(f"   Total de registros: {len(X)}\n")
    f.write(f"   Anomalias detec.:   {n_anomalas} ({n_anomalas/len(X)*100:.1f}%)\n")
    f.write(f"   Score medio:        {scores_anomalia.mean():.4f}\n")
    f.write(f"   Score min:          {scores_anomalia.min():.4f}\n")
    f.write(f"   Score max:          {scores_anomalia.max():.4f}\n\n")

    f.write("3. GRAFICOS GERADOS\n")
    f.write("-" * 45 + "\n")
    f.write("   resultados/grafico_real_vs_predito.png\n")
    f.write("   resultados/importancia_features.png\n")
    f.write("   resultados/distribuicao_anomalias.png\n")
    f.write("   resultados/curva_aprendizado.png\n")

print("\nSalvo: resultados/metricas_resumo.txt")
print("\n=== CONCLUIDO ===")
print(f"Todos os arquivos estao na pasta 'resultados/'")
