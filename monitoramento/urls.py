from django.urls import path
from .views import ReceberDadosESP32, dashboard, nova_leitura, login_view, logout_view, resultado_leitura, registrar_feedback, relatorio, exportar_csv

urlpatterns = [
    path('api/sensor/', ReceberDadosESP32.as_view(), name='receber_dados'),
    path('dashboard/', dashboard, name='dashboard'),
    path('nova-leitura/', nova_leitura, name='nova_leitura'),
    path('resultado/<int:pk>/', resultado_leitura, name='resultado_leitura'),
    path('resultado/<int:pk>/feedback/', registrar_feedback, name='registrar_feedback'),
    path('relatorio/', relatorio, name='relatorio'),
    path('relatorio/exportar-csv/', exportar_csv, name='exportar_csv'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
]