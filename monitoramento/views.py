from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import LeituraSensorSerializer
from django.shortcuts import render, redirect
from django.contrib import messages, auth
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
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
    # Busca as últimas 30 leituras ordenadas da mais recente para a mais antiga
    leituras = LeituraSensor.objects.order_by('-horario')[:30]
    
    # Pega a última leitura para os KPIs (Cards superiores)
    ultima_leitura = leituras.first() if leituras else None

    # Prepara os dados para os gráficos (precisamos inverter para o gráfico ir da esq. p/ dir.)
    leituras_grafico = reversed(leituras)
    horarios = []
    turbidez = []
    vazao = []

    for l in leituras_grafico:
        horarios.append(l.horario.strftime("%H:%M:%S"))
        turbidez.append(l.turbidez_ntu)
        vazao.append(l.vazao_ls)

    contexto = {
        'ultima_leitura': ultima_leitura,
        'leituras': leituras[:10], # Mandamos só as 10 últimas para a tabela
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
            'turbidez_ntu':       get_float('turbidez_ntu'),
            'vazao_ls':           get_float('vazao_ls'),
            'nivel_cm':           get_float('nivel_cm'),
            'ph':                 get_float('ph'),
            'cloro_residual_mgl': get_float('cloro_residual_mgl'),
            'coliformes_ufc':     get_float('coliformes_ufc'),
            'cor_uh':             get_float('cor_uh'),
            'ponto_coleta':       request.POST.get('ponto_coleta', '').strip() or None,
            'operador':           request.POST.get('operador', '').strip() or request.user.get_full_name() or request.user.username,
        }

        if dados['turbidez_ntu'] is None or dados['vazao_ls'] is None or dados['nivel_cm'] is None:
            messages.error(request, 'Turbidez, Vazão e Nível são obrigatórios.')
            return render(request, 'monitoramento/nova_leitura.html', {'form_data': request.POST})

        dados['status_conformidade'] = calcular_conformidade(dados)
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