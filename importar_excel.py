"""
Script de importação do Relatório de Produção ETAI 2025.xlsx para o banco.
Uso: python importar_excel.py
"""

import os
import sys
import django
import pandas as pd
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from monitoramento.models import LeituraSensor

ARQUIVO = r'C:\Users\memmy\Downloads\relatorio_eta.xlsx'

# Índices das colunas (baseado na linha 9 do Excel, 0-indexado)
COL_DATA               = 2
COL_VAZAO_M3           = 3
COL_SULFATO_KG         = 6
COL_POLICLORETO_L      = 7
COL_HIPOCLORITO_KG     = 8
COL_COR_BRUTA          = 9
COL_TURBIDEZ_BRUTA     = 10
COL_COR_TRATADA        = 11
COL_TURBIDEZ_TRATADA   = 12
COL_PH_BRUTO           = 13
COL_ALCALINIDADE_BRUTA = 14
COL_PH_TRATADO         = 15
COL_ALCALINIDADE_TRAT  = 16
COL_CLORO              = 17
COL_COLI_TRATADA       = 21


def to_float(val):
    try:
        f = float(val)
        return f if not pd.isna(f) else None
    except (TypeError, ValueError):
        return None


def calcular_conformidade(turbidez, ph, cloro, coliformes, cor):
    if turbidez is None:
        return False
    ok = turbidez <= 5.0
    if ph is not None:
        ok = ok and 6.0 <= ph <= 9.5
    if cloro is not None:
        ok = ok and 0.2 <= cloro <= 5.0
    if coliformes is not None:
        ok = ok and coliformes == 0
    if cor is not None:
        ok = ok and cor <= 15.0
    return ok


def importar():
    print("Limpando dados existentes...")
    deletados, _ = LeituraSensor.objects.all().delete()
    print(f"  {deletados} registros removidos.")

    xl = pd.ExcelFile(ARQUIVO)
    total = 0
    ignorados = 0

    for aba in xl.sheet_names:
        print(f"\nImportando aba: {aba}")
        df = pd.read_excel(ARQUIVO, sheet_name=aba, header=None)

        # Dados começam na linha 11 (índice 10)
        for idx, row in df.iterrows():
            if idx < 10:
                continue

            data_val = row[COL_DATA]

            # Pula linhas sem data válida ou com "parada"
            if pd.isna(data_val):
                continue
            if isinstance(data_val, str):
                ignorados += 1
                continue
            if not isinstance(data_val, (datetime, pd.Timestamp)):
                ignorados += 1
                continue

            turbidez_tratada = to_float(row[COL_TURBIDEZ_TRATADA])
            if turbidez_tratada is None:
                ignorados += 1
                continue

            ph_tratado    = to_float(row[COL_PH_TRATADO])
            cloro         = to_float(row[COL_CLORO])
            coliformes    = to_float(row[COL_COLI_TRATADA])
            cor_tratada   = to_float(row[COL_COR_TRATADA])

            conformidade = calcular_conformidade(
                turbidez_tratada, ph_tratado, cloro, coliformes, cor_tratada
            )

            LeituraSensor.objects.create(
                horario               = data_val,
                turbidez_ntu          = turbidez_tratada,
                cor_uh                = cor_tratada,
                ph                    = ph_tratado,
                cloro_residual_mgl    = cloro,
                coliformes_ufc        = coliformes,
                alcalinidade_tratada  = to_float(row[COL_ALCALINIDADE_TRAT]),
                turbidez_bruta_ntu    = to_float(row[COL_TURBIDEZ_BRUTA]),
                cor_bruta_uh          = to_float(row[COL_COR_BRUTA]),
                ph_bruto              = to_float(row[COL_PH_BRUTO]),
                alcalinidade_bruta    = to_float(row[COL_ALCALINIDADE_BRUTA]),
                sulfato_aluminio_kg   = to_float(row[COL_SULFATO_KG]),
                policloreto_aluminio_l= to_float(row[COL_POLICLORETO_L]),
                hipoclorito_sodio_kg  = to_float(row[COL_HIPOCLORITO_KG]),
                vazao_m3_dia          = to_float(row[COL_VAZAO_M3]),
                ponto_coleta          = 'saida_filtro',
                status_conformidade   = conformidade,
            )
            total += 1

    print(f"\n✅ Importação concluída: {total} registros importados, {ignorados} linhas ignoradas.")


if __name__ == '__main__':
    importar()
