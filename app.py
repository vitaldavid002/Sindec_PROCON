import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="PROCON Arapiraca - Sistema Integrado", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
# Certifique-se de que o link da planilha está nos Secrets do Streamlit Cloud
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Erro na conexão com o Google Sheets. Verifique os Secrets.")
    st.stop()

def ler_aba(nome_aba):
    return conn.read(worksheet=nome_aba, ttl=0).dropna(how="all")

def salvar_dados(nome_aba, df_novo):
    conn.update(worksheet=nome_aba, data=df_novo)

# --- CONTROLE DE ACESSO ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
if 'usuario' not in st.session_state:
    st.session_state.usuario = None

# --- TELAS DE LOGIN E CADASTRO ---
if not st.session_state.logado:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("⚖️ Sistema PROCON")
        aba_l, aba_c = st.tabs(["Acessar", "Criar Conta"])
        
        with aba_l:
            u = st.text_input("Usuário")
            s = st.text_input("Senha", type="password")
            if st.button("Entrar"):
                df_u = ler_aba("usuarios")
                user = df_u[(df_u['login'] == u) & (df_u['senha'].astype(str) == str(s))]
                if not user.empty:
                    st.session_state.logado = True
                    st.session_state.usuario = u
                    st.rerun()
                else:
                    st.error("Login ou senha inválidos.")
        
        with aba_c:
            nu = st.text_input("Novo Usuário")
            ns = st.text_input("Nova Senha", type="password")
            if st.button("Registrar"):
                df_u = ler_aba("usuarios")
                if nu in df_u['login'].values:
                    st.error("Usuário já existe.")
                else:
                    novo_u = pd.DataFrame([{"id": len(df_u)+1, "login": nu, "senha": ns}])
                    salvar_dados("usuarios", pd.concat([df_u, novo_u], ignore_index=True))
                    st.success("Conta criada!")
    st.stop()

# --- ÁREA LOGADA ---
st.sidebar.title(f"👤 {st.session_state.usuario}")
if st.sidebar.button("Sair"):
    st.session_state.logado = False
    st.rerun()

menu = st.sidebar.radio("Navegação", ["Listar Processos", "Cadastrar Processo"])

if menu == "Cadastrar Processo":
    st.header("📄 Novo Cadastro")
    with st.form("novo_p"):
        num = st.text_input("Nº Processo")
        cons = st.text_input("Consumidor")
        forn = st.text_input("Fornecedor")
        tram = st.text_input("Tramitação Atual")
        obs = st.text_area("Anotações")
        if st.form_submit_button("Salvar"):
            df_p = ler_aba("processos")
            df_h = ler_aba("historico")
            p_id = int(df_p['id'].max() + 1) if not df_p.empty else 1
            
            novo_p = pd.DataFrame([{"id": p_id, "numero": num, "consumidor": cons, "fornecedor": forn, "tramitacao": tram, "anotacoes": obs}])
            novo_h = pd.DataFrame([{"id": len(df_h)+1, "processo_id": p_id, "tramitacao_texto": tram, "usuario_responsavel": st.session_state.usuario, "data_mudanca": datetime.now().strftime("%d/%m/%Y %H:%M")}])
            
            salvar_dados("processos", pd.concat([df_p, novo_p], ignore_index=True))
            salvar_dados("historico", pd.concat([df_h, novo_h], ignore_index=True))
            st.success("Processo salvo!")

elif menu == "Listar Processos":
    st.header("🔍 Consulta")
    df_p = ler_aba("processos")
    df_h = ler_aba("historico")
    
    busca = st.text_input("Buscar por nome ou número")
    if busca:
        df_p = df_p[df_p['numero'].str.contains(busca, case=False) | df_p['consumidor'].str.contains(busca, case=False)]

    for _, p in df_p.iterrows():
        with st.expander(f"📦 {p['numero']} - {p['consumidor']}"):
            st.write(f"**Status:** {p['tramitacao']}")
            st.write(f"**Obs:** {p['anotacoes']}")
            
            # Atualizar Status
            nova_t = st.text_input("Atualizar Tramitação", key=f"in_{p['id']}")
            if st.button("Confirmar", key=f"btn_{p['id']}"):
                df_p.loc[df_p['id'] == p['id'], 'tramitacao'] = nova_t
                n_h = pd.DataFrame([{"id": len(df_h)+1, "processo_id": p['id'], "tramitacao_texto": nova_t, "usuario_responsavel": st.session_state.usuario, "data_mudanca": datetime.now().strftime("%d/%m/%Y %H:%M")}])
                salvar_dados("processos", df_p)
                salvar_dados("historico", pd.concat([df_h, n_h], ignore_index=True))
                st.rerun()
