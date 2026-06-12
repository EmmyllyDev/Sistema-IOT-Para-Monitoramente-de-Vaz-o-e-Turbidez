from django.urls import path
from .views import ReceberDadosESP32, dashboard, nova_leitura

urlpatterns = [
    path('api/sensor/', ReceberDadosESP32.as_view(), name='receber_dados'),
    path('dashboard/', dashboard, name='dashboard'),
    path('nova-leitura/', nova_leitura, name='nova_leitura'),
]