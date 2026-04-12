<div align="center">

<!-- Badges -->
![IoT](https://img.shields.io/badge/Tecnologia-IoT-1D9E75?style=flat-square&logoColor=white)
![Status](https://img.shields.io/badge/Status-Protótipo%20Funcional-0F6E56?style=flat-square)
![Portaria](https://img.shields.io/badge/Portaria-GM%2FMS%20888%2F2021-185FA5?style=flat-square)
![Disciplina](https://img.shields.io/badge/Disciplina-Extensão%20II-534AB7?style=flat-square)

<br/>

# 💧 SIGUA - Sistema IoT para Monitoramento de Vazão e Turbidez

**ETA Júlio Campos – DAE Várzea Grande, Mato Grosso**

> Coleta automática · Validação legislativa · Relatórios técnicos

<br/>

| 👩‍💻 Aluna | 📚 Disciplina | 🏷️ Tipo | 📍 Local |
|:---:|:---:|:---:|:---:|
| Emmylly Maria dos Santos Oliveira | Extensão II | Protótipo funcional em ambiente operacional | ETA Júlio Campos – DAE Várzea Grande |

</div>

---

## 📌 Visão de Produto

Para os **responsáveis técnicos da ETA Júlio Campos** do DAE de Várzea Grande, que precisam monitorar continuamente a vazão e a turbidez da água distribuída e verificar sua conformidade com a legislação, o **Sistema de Monitoramento de Vazão e Turbidez da Água** é um sistema integrado composto por um dispositivo IoT com sensores e uma plataforma web de gestão, que realiza a **coleta automática e periódica** dos dados de vazão e turbidez da água tratada, valida os valores conforme a **Portaria GM/MS nº 888/2021** e gera **relatórios técnicos de acompanhamento**.

> **Diferente de** processos manuais baseados em formulários e planilhas, nosso produto **automatiza a aquisição dos dados**, organiza as informações de monitoramento e consolida relatórios de conformidade, garantindo rastreabilidade das medições, maior confiabilidade dos registros e apoio à tomada de decisão operacional.

---

## ❌ Problema vs ✅ Solução

| ❌ Processo Atual | ✅ Com o Sistema |
|:---|:---|
| Coleta manual com formulários | Aquisição automática e periódica |
| Registros em planilhas desconexas | Dados centralizados na plataforma web |
| Baixa rastreabilidade das medições | Rastreabilidade total das medições |
| Risco de falha humana nos registros | Validação automática conforme legislação |
| Relatórios elaborados manualmente | Relatórios técnicos gerados automaticamente |

---

## 📊 Métricas do Relatório Gerado

| 🔢 Amostras exigidas | ✅ Amostras realizadas | 📋 Em conformidade | 📈 Média mensal |
|:---:|:---:|:---:|:---:|
| Quantidade prevista pela Portaria GM/MS nº 888/2021 | Total coletado no período | Percentual dentro do padrão | Valor médio + limite permitido |

Cada relatório consolidado contém:

- 🔢 **Quantidade de amostras exigidas** pela Portaria GM/MS nº 888/2021
- ✅ **Amostras realizadas** no período
- 📋 **Amostras em conformidade** com o padrão de qualidade
- 📈 **Média mensal** do parâmetro monitorado
- 📏 **Valor permitido** do parâmetro conforme legislação vigente

---

## 🏗️ Arquitetura do Sistema

```mermaid
flowchart LR
    subgraph F["⚙️ Camada Física"]
        A[💧 Sensor de Vazão]
        B[🌊 Sensor de Turbidez]
    end

    subgraph B2["📡 Camada de Borda"]
        C[🔌 Dispositivo IoT\nEmbarcado]
    end

    subgraph G["🖥️ Camada de Gestão"]
        D[🌐 Plataforma Web]
        E[📊 Relatórios]
        F2[✅ Validação\nPortaria 888/2021]
    end

    A --> C
    B --> C
    C --> D
    D --> E
    D --> F2
```

### Camada Física — Sensores
- **Sensor de vazão**: mede o volume de água distribuída por unidade de tempo
- **Sensor de turbidez**: mede a quantidade de partículas suspensas na água tratada

### Camada de Borda — Dispositivo IoT
- Coleta periódica e automática dos dados dos sensores
- Processamento local e transmissão para a plataforma central

### Camada de Gestão — Plataforma Web
- Visualização em tempo real dos parâmetros monitorados
- Validação automática dos valores conforme Portaria GM/MS nº 888/2021
- Geração de relatórios técnicos de acompanhamento
- Apoio à tomada de decisão operacional

---

## ⚖️ Base Legal

<div align="center">

**📜 Portaria GM/MS nº 888/2021 – Ministério da Saúde**

</div>

Estabelece os procedimentos e responsabilidades relativos ao controle e vigilância da qualidade da água para consumo humano, incluindo:

- Padrões de **turbidez** para água distribuída
- Requisitos de **monitoramento de vazão** em sistemas de abastecimento
- Frequência mínima de **coleta de amostras** por porte do sistema
- Parâmetros de **conformidade** e notificação obrigatória

---

## 🛠️ Tecnologias e Componentes

![IoT Embarcado](https://img.shields.io/badge/-IoT%20Embarcado-1D9E75?style=flat-square)
![Sensor de Vazão](https://img.shields.io/badge/-Sensor%20de%20Vazão-0F6E56?style=flat-square)
![Sensor de Turbidez](https://img.shields.io/badge/-Sensor%20de%20Turbidez-085041?style=flat-square)
![Plataforma Web](https://img.shields.io/badge/-Plataforma%20Web-185FA5?style=flat-square)
![Relatórios Automáticos](https://img.shields.io/badge/-Relatórios%20Automáticos-534AB7?style=flat-square)
![Conformidade Legislativa](https://img.shields.io/badge/-Conformidade%20Legislativa-854F0B?style=flat-square)

---

## 📂 Estrutura do Projeto

```
SistEMA-IOT-Para-Monitoramento-de-Vaz-o-e-Turbidez
├── core/                       # Configurações centrais do Django (settings, urls)
├── monitoramento/              # App principal (US13 e US14)
│   ├── migrations/
│   ├── templates/              # HTML do Dashboard (US14)
│   │   └── dashboard.html
│   ├── api/                    # Lógica da API de recebimento (US13)
│   │   └── views_api.py
│   ├── admin.py                # Interface administrativa
│   ├── models.py               # Definição das tabelas (US07 e US13)
│   ├── urls.py                 # Rotas do App
│   └── views.py                # Lógica de exibição do Dashboard (US14)
├── static/                     # CSS, JS e Imagens (Bootstrap)
├── manage.py
├── .env                        # Credenciais do PostgreSQL
└── requirements.txt
```


<div align="center">

**Emmylly Maria dos Santos Oliveira** · Extensão II  
ETA Júlio Campos – DAE Várzea Grande · Mato Grosso, Brasil

<br/>

🟢 *Protótipo funcional em ambiente operacional*

</div>
