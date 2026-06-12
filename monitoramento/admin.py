from django.contrib import admin
from .models import LeituraSensor, SugestaoLog


@admin.register(LeituraSensor)
class LeituraSensorAdmin(admin.ModelAdmin):
    list_display = ('horario', 'turbidez_ntu', 'vazao_ls', 'nivel_cm', 'status_conformidade', 'operador', 'ponto_coleta')
    list_filter  = ('status_conformidade', 'ponto_coleta')
    ordering     = ('-horario',)


@admin.register(SugestaoLog)
class SugestaoLogAdmin(admin.ModelAdmin):
    list_display  = ('horario', 'leitura', 'parametro', 'status', 'feedback', 'operador')
    list_filter   = ('status', 'feedback', 'parametro')
    ordering      = ('-horario',)
    readonly_fields = ('leitura', 'parametro', 'status', 'mensagem', 'operador', 'horario')
