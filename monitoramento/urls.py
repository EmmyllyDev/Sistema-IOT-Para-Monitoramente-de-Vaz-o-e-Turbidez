from django.urls import path
from .views import ReceberDadosESP32, dashboard 

urlpatterns = [
    path('api/sensor/', ReceberDadosESP32.as_view(), name='receber_dados'),
    path('dashboard/', dashboard, name='dashboard'), 
]