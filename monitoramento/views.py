from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import LeituraSensorSerializer
from django.shortcuts import render, redirect
from django.contrib import messages, auth
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
import csv
from datetime import datetime
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from .models import LeituraSensor
from .sugestoes import gerar_sugestoes
import json


def calcular_conformidade(dados):
    turbidez = float(dados.get('turbidez_ntu') or 99.0)
    ph = dados.get('ph')
    cloro = dados.get('cloro_residual_mgl')
    coliformes = dados.get('coliformes_ufc')
    cor = dados.get('cor_uh')

    ok = turbidez <= 5.0
    if ph is not None:
        ok = ok and 6.0 <= float(ph) <= 9.5
    if cloro is not None:
        ok = ok and 0.2 <= float(cloro) <= 5.0
    if coliformes is not None:
        ok = ok and float(coliformes) == 0
    if cor is not None:
        ok = ok and float(cor) <= 15.0
    return ok


class ReceberDadosESP32(APIView):
    def post(self, request):
        dados = request.data.copy()

        status_ok = calcular_conformidade(dados)
        dados['status_conformidade'] = status_ok

        # Passamos para o tradutor (Serializer)
        serializer = LeituraSensorSerializer(data=dados)
        
        if serializer.is_valid():
            serializer.save() # Salva no PostgreSQL
            return Response({
                "message": "Dados recebidos com sucesso!", 
                "status_conformidade": status_ok
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
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
    horarios = []
    turbidez = []
    vazao = []

    for l in leituras_grafico:
        horarios.append(l.horario.strftime("%d/%m/%Y") if l.horario else "")
        turbidez.append(l.turbidez_ntu)
        vazao.append(l.vazao_ls or 0)

    contexto = {
        'ultima_leitura': ultima_leitura,
        'ultima_horario_local': ultima_leitura.horario if ultima_leitura else None,
        'leituras': leituras[:10],
        'horarios_json': json.dumps(horarios),
        'turbidez_json': json.dumps(turbidez),
        'vazao_json': json.dumps(vazao),
    }

    return render(request, 'monitoramento/dashboard.html', contexto)


@login_required
def nova_leitura(request):
    if request.method == 'POST':
        def get_float(key):
            val = request.POST.get(key, '').strip()
            return float(val) if val else None

        dados = {
            # Água tratada
            'turbidez_ntu':         get_float('turbidez_ntu'),
            'vazao_ls':             get_float('vazao_ls'),
            'nivel_cm':             get_float('nivel_cm'),
            'ph':                   get_float('ph'),
            'cloro_residual_mgl':   get_float('cloro_residual_mgl'),
            'coliformes_ufc':       get_float('coliformes_ufc'),
            'cor_uh':               get_float('cor_uh'),
            'alcalinidade_tratada': get_float('alcalinidade_tratada'),
            # Água bruta
            'turbidez_bruta_ntu':   get_float('turbidez_bruta_ntu'),
            'cor_bruta_uh':         get_float('cor_bruta_uh'),
            'ph_bruto':             get_float('ph_bruto'),
            'alcalinidade_bruta':   get_float('alcalinidade_bruta'),
            # Dosagens
            'sulfato_aluminio_kg':    get_float('sulfato_aluminio_kg'),
            'policloreto_aluminio_l': get_float('policloreto_aluminio_l'),
            'hipoclorito_sodio_kg':   get_float('hipoclorito_sodio_kg'),
            'vazao_m3_dia':           get_float('vazao_m3_dia'),
            # Identificação
            'ponto_coleta': request.POST.get('ponto_coleta', '').strip() or None,
            'operador':     request.POST.get('operador', '').strip() or request.user.get_full_name() or request.user.username,
        }

        if dados['turbidez_ntu'] is None or dados['vazao_ls'] is None or dados['nivel_cm'] is None:
            messages.error(request, 'Turbidez, Vazão e Nível são obrigatórios.')
            return render(request, 'monitoramento/nova_leitura.html', {'form_data': request.POST})

        dados['status_conformidade'] = calcular_conformidade(dados)
        dados['horario'] = datetime.now()
        leitura = LeituraSensor.objects.create(**dados)
        return redirect('resultado_leitura', pk=leitura.pk)

    return render(request, 'monitoramento/nova_leitura.html')


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

    dosagem = request.POST.get('dosagem_aplicada_mgl', '').strip()
    leitura.dosagem_aplicada_mgl = float(dosagem) if dosagem else None
    leitura.sugestao_aceita = request.POST.get('sugestao_aceita') == 'sim'
    leitura.observacao_operador = request.POST.get('observacao_operador', '').strip() or None
    leitura.save()

    messages.success(request, 'Feedback registrado com sucesso.')
    return redirect('dashboard')


# ── Campos exibidos no relatório ────────────────────────────
CAMPOS_RELATORIO = [
    ('horario',               'Data/Hora'),
    ('operador',              'Operador'),
    ('turbidez_ntu',          'Turbidez Tratada (NTU)'),
    ('cor_uh',                'Cor Tratada (uH)'),
    ('ph',                    'pH Tratado'),
    ('cloro_residual_mgl',    'Cloro Residual (mg/L)'),
    ('coliformes_ufc',        'Coliformes (UFC/100mL)'),
    ('alcalinidade_tratada',  'Alcalinidade Tratada (mg/L)'),
    ('turbidez_bruta_ntu',    'Turbidez Bruta (NTU)'),
    ('cor_bruta_uh',          'Cor Bruta (uH)'),
    ('ph_bruto',              'pH Bruto'),
    ('alcalinidade_bruta',    'Alcalinidade Bruta (mg/L)'),
    ('vazao_ls',              'Vazão (L/s)'),
    ('vazao_m3_dia',          'Vazão Entrada (M³/dia)'),
    ('sulfato_aluminio_kg',   'Sulfato Al. (Kg)'),
    ('policloreto_aluminio_l','PAC (L)'),
    ('hipoclorito_sodio_kg',  'Hipoclorito (Kg)'),
    ('status_conformidade',   'Conformidade'),
]

CAMPOS_MEDIA = [
    'turbidez_ntu', 'cor_uh', 'ph', 'cloro_residual_mgl',
    'coliformes_ufc', 'alcalinidade_tratada',
    'turbidez_bruta_ntu', 'cor_bruta_uh', 'ph_bruto', 'alcalinidade_bruta',
    'vazao_ls', 'vazao_m3_dia',
    'sulfato_aluminio_kg', 'policloreto_aluminio_l', 'hipoclorito_sodio_kg',
]


def _calcular_medias(qs):
    agg = {f: Avg(f) for f in CAMPOS_MEDIA}
    resultado = qs.aggregate(**agg)
    medias = {}
    for campo in CAMPOS_MEDIA:
        val = resultado.get(campo)
        medias[campo] = round(val, 2) if val is not None else None
    return medias


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