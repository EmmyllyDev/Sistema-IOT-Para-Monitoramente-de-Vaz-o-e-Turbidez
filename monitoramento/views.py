from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import LeituraSensorSerializer
from django.shortcuts import render, redirect
from django.contrib import messages, auth
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
import csv
from datetime import datetime
from django.db.models import Avg, Count, Max, Min, Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import ConfiguracaoSistema, LeituraSensor
from .sugestoes import gerar_sugestoes
from .vazao import vazao_por_nivel, NIVEL_MAXIMO_CM
import json
import secrets


# Meta de amostragem da Portaria GM/MS nº 888/2021 para esta ETA.
# AMOSTRAS_PERIODO define sobre qual janela as amostras realizadas são contadas:
# 'ano' conta o ano corrente, 'mes' conta o mês corrente.
AMOSTRAS_EXIGIDAS = 360
AMOSTRAS_PERIODO = 'mes'


def avaliar_parametros(dados):
    """Avalia cada parâmetro da Portaria GM/MS nº 888/2021 contra seu limite.

    Devolve uma lista na ordem de exibição. 'conforme' é True, False, ou None
    quando o parâmetro não foi medido nesta leitura. Turbidez é obrigatória:
    se vier ausente, conta como não conforme.
    """
    def numero(v):
        if v is None or v == '':
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    turbidez   = numero(dados.get('turbidez_ntu'))
    ph         = numero(dados.get('ph'))
    cloro      = numero(dados.get('cloro_residual_mgl'))
    cor        = numero(dados.get('cor_uh'))
    coliformes = numero(dados.get('coliformes_ufc'))

    return [
        {'chave': 'turbidez', 'nome': 'Turbidez', 'unidade': 'NTU', 'casas': 2,
         'valor': turbidez, 'limite': 'até 5,0 NTU',
         'conforme': None if turbidez is None else turbidez <= 5.0},

        {'chave': 'ph', 'nome': 'pH', 'unidade': '', 'casas': 2,
         'valor': ph, 'limite': 'de 6,0 a 9,5',
         'conforme': None if ph is None else 6.0 <= ph <= 9.5},

        {'chave': 'cloro', 'nome': 'Cloro residual', 'unidade': 'mg/L', 'casas': 2,
         'valor': cloro, 'limite': 'de 0,2 a 5,0 mg/L',
         'conforme': None if cloro is None else 0.2 <= cloro <= 5.0},

        {'chave': 'cor', 'nome': 'Cor aparente', 'unidade': 'uH', 'casas': 1,
         'valor': cor, 'limite': 'até 15 uH',
         'conforme': None if cor is None else cor <= 15.0},

        {'chave': 'coliformes', 'nome': 'Coliformes totais', 'unidade': 'UFC/100mL', 'casas': 0,
         'valor': coliformes, 'limite': 'ausência',
         'conforme': None if coliformes is None else coliformes == 0},
    ]


def calcular_conformidade(dados):
    """Conforme quando há ao menos um parâmetro medido e nenhum fora do limite.

    Uma leitura sem nenhum parâmetro medido não pode ser declarada conforme.
    """
    medidos = [p for p in avaliar_parametros(dados) if p['conforme'] is not None]
    return bool(medidos) and all(p['conforme'] for p in medidos)


def _horario_da_leitura(enviado):
    """Horário do aparelho, se vier legível; senão o do servidor.

    O ESP32 pode estar sem relógio sincronizado, então um horário ausente ou
    malformado não pode impedir o registro.
    """
    if enviado:
        analisado = parse_datetime(str(enviado))
        if analisado is not None:
            if timezone.is_aware(analisado):
                analisado = timezone.make_naive(analisado, timezone.get_default_timezone())
            return analisado
    return datetime.now()


def _token_valido(request):
    """Confere o token do sensor no cabeçalho Authorization.

    Aceita 'Bearer <token>' ou o token puro, porque é fácil errar o prefixo
    no firmware. A comparação é feita em tempo constante.
    """
    enviado = request.headers.get('Authorization', '').strip()
    if enviado.lower().startswith('bearer '):
        enviado = enviado[7:].strip()
    if not enviado:
        return False
    esperado = ConfiguracaoSistema.obter().token_sensor
    return secrets.compare_digest(enviado, esperado)


class ReceberDadosESP32(APIView):
    # O endpoint é público na rede: quem autentica é o token do sensor.
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        if not _token_valido(request):
            return Response(
                {"erro": "Token do sensor ausente ou inválido."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        dados = request.data.copy()

        # O ultrassônico sobre a calha Parshall entrega a altura; a vazão sai
        # da tabela da ETA. Se o aparelho já mandar a vazão, ela é respeitada.
        if not dados.get('vazao_ls') and dados.get('nivel_cm') is not None:
            convertida = vazao_por_nivel(dados.get('nivel_cm'))
            if convertida is not None:
                dados['vazao_ls'] = convertida

        serializer = LeituraSensorSerializer(data=dados)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # horario, status_conformidade e origem são read-only no serializer:
        # quem os define é o servidor, não o aparelho. Sem isso a leitura
        # entraria sem horário e ficaria invisível em todas as telas.
        status_ok = calcular_conformidade(dados)
        leitura = serializer.save(
            horario=_horario_da_leitura(dados.get('horario')),
            status_conformidade=status_ok,
            origem=LeituraSensor.ORIGEM_SENSOR,
        )

        return Response(
            {
                "message": "Leitura registrada.",
                "id": leitura.pk,
                "horario": leitura.horario,
                "vazao_ls": leitura.vazao_ls,
                "status_conformidade": status_ok,
            },
            status=status.HTTP_201_CREATED,
        )
    
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Usuário ou senha incorretos.')

    return render(request, 'monitoramento/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    leituras = LeituraSensor.objects.exclude(horario=None).order_by('-horario')[:30]
    ultima_leitura = leituras.first() if leituras else None

    leituras_grafico = list(reversed(list(leituras)))

    # Série temporal para os gráficos interativos. O eixo X vai como datetime
    # real (não como texto) para o Plotly permitir zoom, pan e range slider.
    serie = []
    for l in leituras_grafico:
        serie.append({
            'id': l.id,
            'x': l.horario.strftime('%Y-%m-%d %H:%M:%S'),
            'rotulo': l.horario.strftime('%d/%m/%Y %H:%M'),
            'turbidez': l.turbidez_ntu,
            'turbidez_bruta': l.turbidez_bruta_ntu,
            'vazao': l.vazao_ls,
            'nivel': l.nivel_cm,
            'ph': l.ph,
            'cloro': l.cloro_residual_mgl,
            'cor': l.cor_uh,
            'conforme': l.status_conformidade,
        })

    def resumo(chave, casas=2):
        vals = [p[chave] for p in serie if p[chave] is not None]
        if not vals:
            return {'media': None, 'minimo': None, 'maximo': None, 'ultimo': None, 'n': 0}
        return {
            'media': round(sum(vals) / len(vals), casas),
            'minimo': round(min(vals), casas),
            'maximo': round(max(vals), casas),
            'ultimo': round(vals[-1], casas),
            'n': len(vals),
        }

    resumo_turbidez = resumo('turbidez')
    resumo_vazao = resumo('vazao')
    resumo_nivel = resumo('nivel', 1)

    # O cartão de vazão mostra número e legenda da MESMA leitura: a mais
    # recente que tem vazão. Sem isso, o valor viria de uma leitura e a
    # altura na calha de outra.
    fonte_vazao = next(
        (ponto for ponto in reversed(serie) if ponto['vazao'] is not None),
        None,
    )
    fonte_vazao_antiga = bool(
        fonte_vazao and serie and fonte_vazao['id'] != serie[-1]['id']
    )

    total = len(serie)
    conformes = sum(1 for p in serie if p['conforme'])
    alertas = total - conformes
    taxa_conformidade = round(conformes / total * 100, 1) if total else None

    # Controle de amostragem: quantas amostras foram feitas no período
    # contra a meta da portaria.
    # A meta da portaria é a amostragem do operador. As leituras do sensor
    # chegam a cada 30 min e entrariam quatro vezes acima da meta, tornando
    # o contador inútil, por isso não entram nesta conta.
    hoje = datetime.now()
    amostras_qs = LeituraSensor.objects.filter(origem=LeituraSensor.ORIGEM_OPERADOR)
    if AMOSTRAS_PERIODO == 'mes':
        amostras_realizadas = amostras_qs.filter(
            horario__year=hoje.year, horario__month=hoje.month).count()
        amostras_rotulo = 'no mês'
    else:
        amostras_realizadas = amostras_qs.filter(horario__year=hoje.year).count()
        amostras_rotulo = 'no ano'

    amostras_restantes = max(AMOSTRAS_EXIGIDAS - amostras_realizadas, 0)
    amostras_pct = round(
        min(amostras_realizadas / AMOSTRAS_EXIGIDAS, 1) * 100, 1
    ) if AMOSTRAS_EXIGIDAS else 0

    # Avaliação parâmetro a parâmetro da última leitura, para o hero dizer
    # exatamente o que está fora em vez de falar só de turbidez.
    if ultima_leitura:
        parametros = avaliar_parametros({
            'turbidez_ntu':       ultima_leitura.turbidez_ntu,
            'ph':                 ultima_leitura.ph,
            'cloro_residual_mgl': ultima_leitura.cloro_residual_mgl,
            'cor_uh':             ultima_leitura.cor_uh,
            'coliformes_ufc':     ultima_leitura.coliformes_ufc,
        })
    else:
        parametros = []

    medidos = [p for p in parametros if p['conforme'] is not None]
    fora = [p for p in medidos if not p['conforme']]

    def juntar(nomes):
        if not nomes:
            return ''
        if len(nomes) == 1:
            return nomes[0]
        return ', '.join(nomes[:-1]) + ' e ' + nomes[-1]

    nomes_fora = juntar([p['nome'] for p in fora])

    contexto = {
        'ultima_leitura': ultima_leitura,
        'ultima_horario_local': ultima_leitura.horario if ultima_leitura else None,
        'nomes_fora': nomes_fora,
        'qtd_medidos': len(medidos),
        'qtd_fora': len(fora),
        'qtd_ok': len(medidos) - len(fora),
        'tudo_conforme': bool(medidos) and not fora,
        'amostras_exigidas': AMOSTRAS_EXIGIDAS,
        'amostras_realizadas': amostras_realizadas,
        'amostras_restantes': amostras_restantes,
        'amostras_pct': amostras_pct,
        'amostras_rotulo': amostras_rotulo,
        'amostras_ano': hoje.year,
        'leituras': leituras[:10],
        'serie_json': json.dumps(serie),
        'resumo_turbidez': resumo_turbidez,
        'resumo_vazao': resumo_vazao,
        'resumo_nivel': resumo_nivel,
        'nivel_maximo_cm': NIVEL_MAXIMO_CM,
        'fonte_vazao': fonte_vazao,
        'fonte_vazao_antiga': fonte_vazao_antiga,
        'resumo_json': json.dumps({
            'turbidez': resumo_turbidez,
            'vazao': resumo_vazao,
            'nivel': resumo_nivel,
            'nivel_maximo': NIVEL_MAXIMO_CM,
            'fonte_vazao': fonte_vazao,
        }),
        'total_leituras': total,
        'conformes': conformes,
        'alertas': alertas,
        'taxa_conformidade': taxa_conformidade,
    }

    return render(request, 'monitoramento/dashboard.html', contexto)


@login_required
def nova_leitura(request):
    if request.method == 'POST':
        def get_float(key):
            val = request.POST.get(key, '').strip().replace(',', '.')
            if not val:
                return None
            try:
                return float(val)
            except ValueError:
                return None

        tipo_reservatorio = request.POST.get('tipo_reservatorio', '').strip() or None
        validos = dict(LeituraSensor.RESERVATORIO_CHOICES)
        if tipo_reservatorio not in validos:
            tipo_reservatorio = None

        dados = {
            # Água tratada
            'turbidez_ntu':         get_float('turbidez_ntu'),
            'cor_uh':               get_float('cor_uh'),
            'cloro_residual_mgl':   get_float('cloro_residual_mgl'),
            'ph':                   get_float('ph'),
            'coliformes_ufc':       get_float('coliformes_ufc'),
            'alcalinidade_tratada': get_float('alcalinidade_tratada'),
            # Água bruta
            'turbidez_bruta_ntu':   get_float('turbidez_bruta_ntu'),
            'cor_bruta_uh':         get_float('cor_bruta_uh'),
            'ph_bruto':             get_float('ph_bruto'),
            'alcalinidade_bruta':   get_float('alcalinidade_bruta'),
            # Vazão — virá do sensor ultrassônico na calha Parshall
            'vazao_ls':             get_float('vazao_ls'),
            # Dosagens
            'sulfato_aluminio_kg':    get_float('sulfato_aluminio_kg'),
            'policloreto_aluminio_l': get_float('policloreto_aluminio_l'),
            'hipoclorito_sodio_kg':   get_float('hipoclorito_sodio_kg'),
            # Identificação
            'tipo_reservatorio': tipo_reservatorio,
            'operador': (request.POST.get('operador', '').strip()
                         or request.user.get_full_name()
                         or request.user.username),
        }

        # Nenhuma medição é obrigatória isoladamente, mas uma leitura vazia
        # não registra nada útil.
        medicoes = [
            'turbidez_ntu', 'cor_uh', 'cloro_residual_mgl', 'ph',
            'coliformes_ufc', 'alcalinidade_tratada',
            'turbidez_bruta_ntu', 'cor_bruta_uh', 'ph_bruto', 'alcalinidade_bruta',
            'vazao_ls', 'sulfato_aluminio_kg', 'policloreto_aluminio_l',
            'hipoclorito_sodio_kg',
        ]
        if all(dados[c] is None for c in medicoes):
            messages.error(request, 'Preencha ao menos uma medição para registrar a leitura.')
            return render(request, 'monitoramento/nova_leitura.html', {
                'form_data': request.POST,
                'reservatorios': LeituraSensor.RESERVATORIO_CHOICES,
            })

        dados['status_conformidade'] = calcular_conformidade(dados)
        dados['horario'] = datetime.now()
        leitura = LeituraSensor.objects.create(**dados)
        return redirect('resultado_leitura', pk=leitura.pk)

    return render(request, 'monitoramento/nova_leitura.html', {
        'reservatorios': LeituraSensor.RESERVATORIO_CHOICES,
    })


@login_required
def resultado_leitura(request, pk):
    leitura = LeituraSensor.objects.get(pk=pk)
    sugestoes = gerar_sugestoes(leitura)
    tem_critico = any(s['status'] == 'critico' for s in sugestoes)
    return render(request, 'monitoramento/resultado_leitura.html', {
        'leitura': leitura,
        'sugestoes': sugestoes,
        'tem_critico': tem_critico,
    })


@login_required
def registrar_feedback(request, pk):
    if request.method != 'POST':
        return redirect('resultado_leitura', pk=pk)

    leitura = LeituraSensor.objects.get(pk=pk)

    # Aceita vírgula decimal e ignora texto não numérico em vez de estourar.
    dosagem = request.POST.get('dosagem_aplicada_mgl', '').strip().replace(',', '.')
    try:
        leitura.dosagem_aplicada_mgl = float(dosagem) if dosagem else None
    except ValueError:
        leitura.dosagem_aplicada_mgl = None

    # Sem resposta, o feedback continua pendente em vez de virar "não segui".
    resposta = request.POST.get('sugestao_aceita')
    leitura.sugestao_aceita = (resposta == 'sim') if resposta in ('sim', 'nao') else None

    leitura.observacao_operador = request.POST.get('observacao_operador', '').strip() or None
    leitura.save()

    messages.success(request, 'Feedback registrado com sucesso.')
    return redirect('dashboard')


# ── Campos exibidos no relatório ────────────────────────────
# ── Parâmetros do relatório ─────────────────────────────────
# Fonte única: a tabela, os cartões de média e o CSV saem toda daqui.
# 'media' traz o rótulo já concordado (turbidez média, cloro médio), para a
# leitura não confundir a média do período com uma leitura isolada.
# 'regra' None significa que o parâmetro não é avaliado pela portaria —
# a água bruta entra antes do tratamento.
PARAMETROS_RELATORIO = [
    {'campo': 'turbidez_ntu',       'nome': 'Turbidez',          'media': 'Turbidez média',
     'unidade': 'NTU',       'casas': 2, 'agua': 'tratada', 'limite': 'até 5,0 NTU',       'regra': 'turbidez'},
    {'campo': 'cor_uh',             'nome': 'Cor aparente',      'media': 'Cor aparente média',
     'unidade': 'uH',        'casas': 1, 'agua': 'tratada', 'limite': 'até 15 uH',         'regra': 'cor'},
    {'campo': 'ph',                 'nome': 'pH',                'media': 'pH médio',
     'unidade': '',          'casas': 2, 'agua': 'tratada', 'limite': 'de 6,0 a 9,5',      'regra': 'ph'},
    {'campo': 'cloro_residual_mgl', 'nome': 'Cloro residual',    'media': 'Cloro residual médio',
     'unidade': 'mg/L',      'casas': 2, 'agua': 'tratada', 'limite': 'de 0,2 a 5,0 mg/L', 'regra': 'cloro'},
    {'campo': 'coliformes_ufc',     'nome': 'Coliformes totais', 'media': 'Coliformes totais médios',
     'unidade': 'UFC/100mL', 'casas': 0, 'agua': 'tratada', 'limite': 'ausência',          'regra': 'coliformes'},

    {'campo': 'turbidez_bruta_ntu', 'nome': 'Turbidez',          'media': 'Turbidez bruta média',
     'unidade': 'NTU',       'casas': 2, 'agua': 'bruta',   'limite': 'sem limite legal',  'regra': None},
    {'campo': 'cor_bruta_uh',       'nome': 'Cor aparente',      'media': 'Cor bruta média',
     'unidade': 'uH',        'casas': 1, 'agua': 'bruta',   'limite': 'sem limite legal',  'regra': None},
    {'campo': 'ph_bruto',           'nome': 'pH',                'media': 'pH bruto médio',
     'unidade': '',          'casas': 2, 'agua': 'bruta',   'limite': 'sem limite legal',  'regra': None},
]

# Colunas da tabela, derivadas da lista acima.
COLUNAS_TRATADA = [p for p in PARAMETROS_RELATORIO if p['agua'] == 'tratada']
COLUNAS_BRUTA   = [p for p in PARAMETROS_RELATORIO if p['agua'] == 'bruta']

CAMPOS_MEDIA = [p['campo'] for p in PARAMETROS_RELATORIO]

# Parâmetros que ganham cartão de destaque no topo do relatório.
DESTAQUES_RELATORIO = ['cor_uh', 'turbidez_ntu', 'cloro_residual_mgl', 'ph']

CAMPOS_RELATORIO = (
    [('horario', 'Data/Hora'), ('operador', 'Operador'), ('tipo_reservatorio', 'Reservatório')]
    + [
        (p['campo'],
         f"{p['nome']} — água {p['agua']}" + (f" ({p['unidade']})" if p['unidade'] else ''))
        for p in PARAMETROS_RELATORIO
    ]
    + [('status_conformidade', 'Conformidade')]
)


def _calcular_medias(qs):
    """Média de cada parâmetro no período, achatada por campo."""
    resultado = qs.aggregate(**{f: Avg(f) for f in CAMPOS_MEDIA})
    return {
        campo: (round(valor, 2) if valor is not None else None)
        for campo, valor in resultado.items()
    }


def _resumo_parametros(qs):
    """Média, mínimo e máximo de cada parâmetro, com o limite da portaria.

    É o quadro que o órgão transcreve para a conta do consumidor, conforme
    o Decreto nº 5.440/2005.
    """
    agregados = {}
    for campo in CAMPOS_MEDIA:
        agregados[f'{campo}__avg'] = Avg(campo)
        agregados[f'{campo}__min'] = Min(campo)
        agregados[f'{campo}__max'] = Max(campo)
        # Count ignora nulos, então conta exatamente quantas amostras
        # daquele parâmetro foram de fato coletadas.
        agregados[f'{campo}__n'] = Count(campo)
        agregados[f'{campo}__n_sensor'] = Count(
            campo, filter=Q(origem=LeituraSensor.ORIGEM_SENSOR)
        )

    bruto = qs.aggregate(**agregados)

    def arredondar(valor, casas):
        return round(valor, casas) if valor is not None else None

    linhas = []
    for par in PARAMETROS_RELATORIO:
        campo, casas, regra = par['campo'], par['casas'], par['regra']
        media = arredondar(bruto.get(f'{campo}__avg'), casas)

        # A média está dentro do limite legal? Só vale para a água tratada.
        dentro = None
        if regra is not None and media is not None:
            avaliacao = avaliar_parametros({campo: media})
            encontrado = next(
                (p for p in avaliacao if p['chave'] == regra and p['conforme'] is not None),
                None,
            )
            dentro = encontrado['conforme'] if encontrado else None

        coletadas = bruto.get(f'{campo}__n') or 0
        do_sensor = bruto.get(f'{campo}__n_sensor') or 0

        linha = dict(par)
        linha.update({
            'rotulo_media': par['media'],
            'media': media,
            'minimo': arredondar(bruto.get(f'{campo}__min'), casas),
            'maximo': arredondar(bruto.get(f'{campo}__max'), casas),
            'dentro': dentro,
            'medido': media is not None,
            'amostras': coletadas,
            'amostras_sensor': do_sensor,
            'amostras_operador': coletadas - do_sensor,
            'meta': AMOSTRAS_EXIGIDAS,
            'meta_cumprida': coletadas >= AMOSTRAS_EXIGIDAS,
        })
        linhas.append(linha)

    return linhas


@login_required
def configuracoes(request):
    """Token do sensor e operadores com acesso ao sistema."""
    config = ConfiguracaoSistema.obter()

    if request.method == 'POST':
        acao = request.POST.get('acao', '')

        # Só quem administra mexe em token e em contas.
        if not request.user.is_superuser:
            messages.error(request, 'Apenas administradores podem alterar configurações.')
            return redirect('configuracoes')

        if acao == 'regerar_token':
            config.regerar_token()
            messages.success(request, 'Token regerado. Atualize o firmware do ESP32 com o novo valor.')

        elif acao == 'criar_operador':
            username = request.POST.get('username', '').strip()
            nome = request.POST.get('nome', '').strip()
            senha = request.POST.get('senha', '')
            admin = request.POST.get('admin') == 'sim'

            if not username or not senha:
                messages.error(request, 'Usuário e senha são obrigatórios.')
            elif len(senha) < 8:
                messages.error(request, 'A senha precisa de ao menos 8 caracteres.')
            elif User.objects.filter(username__iexact=username).exists():
                messages.error(request, f'Já existe um usuário chamado "{username}".')
            else:
                novo = User.objects.create_user(username=username, password=senha)
                if nome:
                    partes = nome.split(' ', 1)
                    novo.first_name = partes[0]
                    novo.last_name = partes[1] if len(partes) > 1 else ''
                novo.is_staff = admin
                novo.is_superuser = admin
                novo.save()
                messages.success(request, f'Operador "{username}" criado.')

        elif acao in ('ativar', 'desativar'):
            alvo = User.objects.filter(pk=request.POST.get('user_id')).first()
            if not alvo:
                messages.error(request, 'Usuário não encontrado.')
            elif alvo == request.user:
                messages.error(request, 'Você não pode desativar a própria conta.')
            else:
                alvo.is_active = (acao == 'ativar')
                alvo.save(update_fields=['is_active'])
                messages.success(
                    request,
                    f'Acesso de "{alvo.username}" {"liberado" if alvo.is_active else "bloqueado"}.'
                )

        elif acao == 'nova_senha':
            alvo = User.objects.filter(pk=request.POST.get('user_id')).first()
            senha = request.POST.get('senha', '')
            if not alvo:
                messages.error(request, 'Usuário não encontrado.')
            elif len(senha) < 8:
                messages.error(request, 'A senha precisa de ao menos 8 caracteres.')
            else:
                alvo.set_password(senha)
                alvo.save()
                messages.success(request, f'Senha de "{alvo.username}" atualizada.')

        return redirect('configuracoes')

    # Quantas leituras cada operador registrou — mostra quem está ativo de fato.
    por_operador = {
        r['operador']: r['n']
        for r in LeituraSensor.objects
        .filter(origem=LeituraSensor.ORIGEM_OPERADOR)
        .values('operador').annotate(n=Count('id'))
    }

    operadores = []
    for u in User.objects.order_by('-is_active', 'username'):
        nome = u.get_full_name() or u.username
        operadores.append({
            'obj': u,
            'nome': nome,
            'leituras': por_operador.get(nome, 0) + por_operador.get(u.username, 0),
            'eu': u == request.user,
        })

    ultima_sensor = (
        LeituraSensor.objects
        .filter(origem=LeituraSensor.ORIGEM_SENSOR)
        .exclude(horario=None)
        .order_by('-horario')
        .first()
    )

    return render(request, 'monitoramento/configuracoes.html', {
        'config': config,
        'operadores': operadores,
        'total_sensor': LeituraSensor.objects.filter(origem=LeituraSensor.ORIGEM_SENSOR).count(),
        'total_operador': LeituraSensor.objects.filter(origem=LeituraSensor.ORIGEM_OPERADOR).count(),
        'ultima_sensor': ultima_sensor,
        'pode_editar': request.user.is_superuser,
        'url_api': request.build_absolute_uri('/monitoramento/api/sensor/'),
    })


@login_required
def relatorio(request):
    qs = LeituraSensor.objects.exclude(horario=None).order_by('-horario')

    # Filtros — padrão: mês e ano atuais
    agora = datetime.now()
    mes      = request.GET.get('mes', str(agora.month))
    ano      = request.GET.get('ano', str(agora.year))
    operador = request.GET.get('operador', '').strip()

    if ano and ano.isdigit():
        qs = qs.filter(horario__year=int(ano))
    if mes and mes.isdigit():
        qs = qs.filter(horario__month=int(mes))
    if operador:
        qs = qs.filter(operador__icontains=operador)

    # Médias do período filtrado
    medias = _calcular_medias(qs)

    # Os quatro parâmetros em destaque, na ordem definida acima.
    parametros = _resumo_parametros(qs)
    por_campo = {p['campo']: p for p in parametros}
    destaques = [por_campo[c] for c in DESTAQUES_RELATORIO if c in por_campo]

    # Total e conformidade
    total = qs.count()
    conformes = qs.filter(status_conformidade=True).count()

    # Média de amostras por mês
    meses_com_dados = qs.dates('horario', 'month').count()
    media_mes = round(total / meses_com_dados, 1) if meses_com_dados > 0 else total

    # Anos disponíveis para o filtro
    anos_disponiveis = (
        LeituraSensor.objects.exclude(horario=None)
        .dates('horario', 'year')
    )
    anos = [d.year for d in anos_disponiveis]

    meses = [
        (1,'Janeiro'),(2,'Fevereiro'),(3,'Março'),(4,'Abril'),
        (5,'Maio'),(6,'Junho'),(7,'Julho'),(8,'Agosto'),
        (9,'Setembro'),(10,'Outubro'),(11,'Novembro'),(12,'Dezembro'),
    ]

    return render(request, 'monitoramento/relatorio.html', {
        'leituras':      qs[:500],
        'medias':        medias,
        'campos':        CAMPOS_RELATORIO,
        'colunas_tratada': COLUNAS_TRATADA,
        'colunas_bruta':   COLUNAS_BRUTA,
        'destaques':     destaques,
        'parametros':    parametros,
        'meta_amostras': AMOSTRAS_EXIGIDAS,
        'total':         total,
        'conformes':     conformes,
        'media_mes':     media_mes,
        'mes_sel':       mes,
        'ano_sel':       ano,
        'operador_sel':  operador,
        'anos':          anos,
        'meses':         meses,
        'campos_media':  CAMPOS_MEDIA,
    })


@login_required
def exportar_csv(request):
    qs = LeituraSensor.objects.exclude(horario=None).order_by('-horario')

    mes      = request.GET.get('mes', '')
    ano      = request.GET.get('ano', '')
    operador = request.GET.get('operador', '').strip()

    if ano and ano.isdigit():
        qs = qs.filter(horario__year=int(ano))
    if mes and mes.isdigit():
        qs = qs.filter(horario__month=int(mes))
    if operador:
        qs = qs.filter(operador__icontains=operador)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="relatorio_sigua.csv"'
    response.write('﻿')  # BOM para Excel abrir corretamente

    writer = csv.writer(response, delimiter=';')

    # Cabeçalho
    cabecalho = [label for _, label in CAMPOS_RELATORIO]
    writer.writerow(cabecalho)

    # Dados
    for l in qs:
        linha = []
        for campo, _ in CAMPOS_RELATORIO:
            val = getattr(l, campo, '')
            if campo == 'horario' and val:
                val = val.strftime('%d/%m/%Y %H:%M')
            elif campo == 'tipo_reservatorio':
                val = l.get_tipo_reservatorio_display() or ''
            elif campo == 'status_conformidade':
                val = 'Conforme' if val else 'Não conforme'
            elif val is None:
                val = ''
            linha.append(val)
        writer.writerow(linha)

    # Linha em branco + médias
    writer.writerow([])
    medias = _calcular_medias(qs)
    media_linha = ['MÉDIA DO PERÍODO', '']
    for campo, _ in CAMPOS_RELATORIO[2:]:  # pula horario e operador
        if campo in medias:
            val = medias[campo]
            media_linha.append(val if val is not None else '')
        elif campo == 'status_conformidade':
            total = qs.count()
            conformes = qs.filter(status_conformidade=True).count()
            media_linha.append(f'{conformes}/{total} conformes')
        else:
            media_linha.append('')
    writer.writerow(media_linha)

    return response