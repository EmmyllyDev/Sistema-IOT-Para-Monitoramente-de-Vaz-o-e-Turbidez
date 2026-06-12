from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import LeituraSensorSerializer
from django.shortcuts import render
from .models import LeituraSensor
import json


class ReceberDadosESP32(APIView):
    def post(self, request):
        dados = request.data.copy() 
        
        turbidez = float(dados.get('turbidez_ntu', 99.0))
        
        status_ok = True if turbidez <= 5.0 else False
        
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