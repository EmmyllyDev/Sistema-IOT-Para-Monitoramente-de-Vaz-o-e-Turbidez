import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine
from backend.models import LeituraSensor
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(
    page_title="SIGUÁ - Monitoramento ETA",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. FUNÇÃO PARA BUSCAR DADOS DO POSTGRESQL
@st.cache_data(ttl=10) # Atualiza o cache a cada 10 segundos
def carregar_dados():
    db = SessionLocal()
    try:
        # Busca todas as leituras ordenadas por horário
        query = db.query(LeituraSensor).order_by(LeituraSensor.horario.asc()).all()
        
        # Converte para DataFrame do Pandas
        df = pd.DataFrame([
            {
                "ID": l.id,
                "Horário": l.horario,
                "Turbidez (NTU)": l.turbidez_ntu,
                "Vazão (L/s)": l.vazao_ls,
                "Nível (cm)": l.nivel_cm,
                "Conformidade": "✅ Conforme" if l.conformidade else "❌ Alerta"
            } for l in query
        ])
        return df
    finally:
        db.close()

# 3. SIDEBAR (LOGOTIPO E IDENTIFICAÇÃO IFMT)
with st.sidebar:
    st.image("docs/Logo_sigua.png", use_container_width=True) 
    st.title("SIGUÁ")
    st.markdown("---")
    st.markdown("### 🎓 IFMT - Cuiabá")
    st.info(f"**Aluna:** Emmylly Oliveira\n\n**Projeto:** Extensão II")
    st.markdown("---")
    
    menu = st.radio("Navegação", ["Dashboard Real-time", "Relatórios Históricos", "Configurações"])
    
    if st.button("🚪 Sair"):
        st.stop()

# 4. DASHBOARD PRINCIPAL
if menu == "Dashboard Real-time":
    st.header("📊 Monitoramento ETA Júlio Campos")
    st.caption("DAE Várzea Grande - Portaria GM/MS nº 888/2021")

    df = carregar_dados()

    if not df.empty:
        # Pega a última leitura para os KPIs
        ultima_leitura = df.iloc[-1]

        # --- LINHA 1: KPIs ---
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Turbidez Atual", f"{ultima_leitura['Turbidez (NTU)']} NTU")
        with col2:
            st.metric("Vazão Atual", f"{ultima_leitura['Vazão (L/s)']} L/s")
        with col3:
            st.metric("Nível na Calha", f"{ultima_leitura['Nível (cm)']} cm")
        with col4:
            st.metric("Status Legal", ultima_leitura['Conformidade'])

        st.divider()

        # --- LINHA 2: GRÁFICOS ---
        c_graf1, c_graf2 = st.columns(2)

        with c_graf1:
            st.subheader("Tendência de Turbidez")
            fig_t = px.area(df.tail(30), x="Horário", y="Turbidez (NTU)", 
                             color_discrete_sequence=['#00d4ff'])
            # Linha de limite da Portaria 888
            fig_t.add_hline(y=5.0, line_dash="dash", line_color="red", annotation_text="Limite 5.0 NTU")
            st.plotly_chart(fig_t, use_container_width=True)
            

        with c_graf2:
            st.subheader("Histórico de Vazão (L/s)")
            fig_v = px.line(df.tail(30), x="Horário", y="Vazão (L/s)", 
                             color_discrete_sequence=['#7a5195'])
            st.plotly_chart(fig_v, use_container_width=True)

        # --- LINHA 3: TABELA DE DADOS ---
        st.subheader("📋 Últimas Amostras Registradas")
        st.dataframe(df.sort_values(by="Horário", ascending=False).head(10), use_container_width=True)

    else:
        st.warning("Nenhum dado encontrado no banco. Execute o script de seed para popular.")

elif menu == "Relatórios Históricos":
    st.header("📑 Gerador de Relatórios Técnicos")
    st.write("Selecione o período para exportar os dados em conformidade com a Portaria 888.")
    # Aqui você pode implementar filtros por data no futuro