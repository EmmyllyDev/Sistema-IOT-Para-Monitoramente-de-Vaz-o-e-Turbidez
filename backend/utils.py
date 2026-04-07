import numpy as np

# --- CONSTANTES DA CALHA PARSHALL-----
NIVEIS_REFERENCIA = [
    10.0, 15.0, 20.0, 22.5, 25.0, 27.5, 30.0, 32.5, 35.0, 37.5, 40.0, 
    42.5, 45.0, 47.5, 50.0, 52.5, 55.0, 57.5, 60.0, 62.5, 65.0, 67.5, 
    70.0, 72.5, 75.0, 77.5, 80.0
]

VAZOES_REFERENCIA = [
    10, 30, 50, 60, 70, 80, 90, 105, 115, 130, 140, 
    155, 170, 185, 200, 215, 230, 250, 265, 280, 295, 
    315, 330, 350, 370, 390, 410
]

def converter_distancia_para_nivel(distancia_lida_cm, altura_sensor_fundo=80.0):
    """
    Converte a distância medida pelo sensor ultrassônico JSN-SR04M-2 em lâmina d'água (h).
    Fórmula: $$h = h_{ref} - d_{medido}$$
    """
    nivel = altura_sensor_fundo - distancia_lida_cm
    return max(0.0, round(nivel, 2))

def calcular_vazao_interpolada(nivel_cm):
    """
    Aplica interpolação linear para encontrar a vazão (L/s) baseada no nível (cm).
    Utiliza a biblioteca NumPy para precisão matemática.
    """
    vazao = np.interp(nivel_cm, NIVEIS_REFERENCIA, VAZOES_REFERENCIA)
    return round(float(vazao), 2)

def validar_conformidade_portaria_888(turbidez_ntu):
    """
    Valida se a turbidez está dentro do padrão de potabilidade (Portaria GM/MS nº 888/2021).
    Limite máximo permitido para distribuição: 5.0 NTU.
    """
    return turbidez_ntu <= 5.0

def processar_leitura_completa(distancia_bruta, turbidez_bruta):
    """
    Função principal de tratamento que integra todas as validações da US06.
    """
    nivel = converter_distancia_para_nivel(distancia_bruta)
    vazao = calcular_vazao_interpolada(nivel)
    esta_conforme = validar_conformidade_portaria_888(turbidez_bruta)
    
    return {
        "nivel_cm": nivel,
        "vazao_ls": vazao,
        "turbidez_ntu": turbidez_bruta,
        "conformidade": esta_conforme
    }