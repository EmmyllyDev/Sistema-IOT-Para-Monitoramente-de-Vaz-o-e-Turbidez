def gerar_sugestoes(leitura):
    sugestoes = []

    # Turbidez
    if leitura.turbidez_ntu > 5.0:
        sugestoes.append({
            'parametro': 'Turbidez',
            'valor': f'{leitura.turbidez_ntu:.2f} NTU',
            'status': 'critico',
            'mensagem': (
                f'Turbidez de {leitura.turbidez_ntu:.2f} NTU está acima do limite de 5,0 NTU (Portaria 888/2021). '
                'Verifique a dosagem de coagulante (sulfato de alumínio) e inspecione os filtros.'
            ),
        })
    elif leitura.turbidez_ntu > 1.0:
        sugestoes.append({
            'parametro': 'Turbidez',
            'valor': f'{leitura.turbidez_ntu:.2f} NTU',
            'status': 'alerta',
            'mensagem': (
                f'Turbidez de {leitura.turbidez_ntu:.2f} NTU está elevada. '
                'Considere aumentar a dosagem de coagulante e intensifique o monitoramento nas próximas coletas.'
            ),
        })
    else:
        sugestoes.append({
            'parametro': 'Turbidez',
            'valor': f'{leitura.turbidez_ntu:.2f} NTU',
            'status': 'ok',
            'mensagem': 'Turbidez dentro do padrão aceitável.',
        })

    # pH
    if leitura.ph is not None:
        if leitura.ph < 6.0:
            sugestoes.append({
                'parametro': 'pH',
                'valor': f'{leitura.ph:.2f}',
                'status': 'critico',
                'mensagem': (
                    f'pH de {leitura.ph:.2f} está abaixo do mínimo permitido (6,0). '
                    'Aplique cal hidratada para elevar o pH à faixa de 6,0 – 9,5.'
                ),
            })
        elif leitura.ph > 9.5:
            sugestoes.append({
                'parametro': 'pH',
                'valor': f'{leitura.ph:.2f}',
                'status': 'critico',
                'mensagem': (
                    f'pH de {leitura.ph:.2f} está acima do máximo permitido (9,5). '
                    'Aplique CO₂ ou ácido para reduzir o pH à faixa de 6,0 – 9,5.'
                ),
            })
        else:
            sugestoes.append({
                'parametro': 'pH',
                'valor': f'{leitura.ph:.2f}',
                'status': 'ok',
                'mensagem': 'pH dentro da faixa permitida (6,0 – 9,5).',
            })

    # Cloro residual livre
    if leitura.cloro_residual_mgl is not None:
        if leitura.cloro_residual_mgl < 0.2:
            sugestoes.append({
                'parametro': 'Cloro Residual',
                'valor': f'{leitura.cloro_residual_mgl:.2f} mg/L',
                'status': 'critico',
                'mensagem': (
                    f'Cloro residual de {leitura.cloro_residual_mgl:.2f} mg/L está abaixo do mínimo (0,2 mg/L). '
                    'Realize recloração imediata para garantir a desinfecção da água distribuída.'
                ),
            })
        elif leitura.cloro_residual_mgl > 5.0:
            sugestoes.append({
                'parametro': 'Cloro Residual',
                'valor': f'{leitura.cloro_residual_mgl:.2f} mg/L',
                'status': 'critico',
                'mensagem': (
                    f'Cloro residual de {leitura.cloro_residual_mgl:.2f} mg/L está acima do limite máximo (5,0 mg/L). '
                    'Reduza a dosagem de cloro para evitar riscos à saúde.'
                ),
            })
        else:
            sugestoes.append({
                'parametro': 'Cloro Residual',
                'valor': f'{leitura.cloro_residual_mgl:.2f} mg/L',
                'status': 'ok',
                'mensagem': 'Cloro residual dentro da faixa permitida (0,2 – 5,0 mg/L).',
            })

    # Cor aparente
    if leitura.cor_uh is not None:
        if leitura.cor_uh > 15.0:
            sugestoes.append({
                'parametro': 'Cor Aparente',
                'valor': f'{leitura.cor_uh:.1f} uH',
                'status': 'critico',
                'mensagem': (
                    f'Cor aparente de {leitura.cor_uh:.1f} uH está acima do limite de 15 uH. '
                    'Verifique o processo de coagulação/floculação e a eficiência dos filtros.'
                ),
            })
        else:
            sugestoes.append({
                'parametro': 'Cor Aparente',
                'valor': f'{leitura.cor_uh:.1f} uH',
                'status': 'ok',
                'mensagem': 'Cor aparente dentro do padrão permitido (≤ 15 uH).',
            })

    # Coliformes totais
    if leitura.coliformes_ufc is not None:
        if leitura.coliformes_ufc > 0:
            sugestoes.append({
                'parametro': 'Coliformes Totais',
                'valor': f'{leitura.coliformes_ufc:.0f} UFC/100mL',
                'status': 'critico',
                'mensagem': (
                    f'Presença de coliformes totais detectada ({leitura.coliformes_ufc:.0f} UFC/100mL). '
                    'Notifique o responsável técnico imediatamente, reforce a desinfecção e colete nova amostra confirmatória.'
                ),
            })
        else:
            sugestoes.append({
                'parametro': 'Coliformes Totais',
                'valor': '0 UFC/100mL',
                'status': 'ok',
                'mensagem': 'Ausência de coliformes totais. Resultado dentro do padrão.',
            })

    # Evento crítico — múltiplos parâmetros fora do padrão
    n_criticos = sum(1 for s in sugestoes if s['status'] == 'critico')
    if n_criticos >= 2:
        sugestoes.insert(0, {
            'parametro': 'Evento Crítico',
            'valor': f'{n_criticos} parâmetros',
            'status': 'critico',
            'mensagem': (
                f'{n_criticos} parâmetros fora do padrão foram identificados simultaneamente. '
                'Acione o responsável técnico da ETA imediatamente e suspenda a distribuição se necessário.'
            ),
        })

    return sugestoes
