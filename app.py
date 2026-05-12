import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="PROCON Arapiraca - Google Sheets DB", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def ler_aba(nome_aba):
    # Lê os dados da aba específica, ignorando cache para ser em tempo real
    return conn.read(worksheet=nome_aba, ttl=0).dropna(how="all")

def salvar_dados(nome_aba, df_novo):
    # Atualiza a aba inteira com o novo DataFrame
    conn.update(worksheet=nome_aba, data=df_novo)

# --- FUNÇÕES DE LÓGICA DE BANCO ---

def realizar_login(login, senha):
    df_usuarios = ler_aba("usuarios")
    # Verifica se existe a combinação na planilha
    user = df_usuarios[(df_usuarios['login'] == login) & (df_usuarios['senha'].astype(str) == str(senha))]
    
    if not user.empty:
        st.session_state.logado = True
        st.session_state.usuario = login
        st.rerun()
    else:
        st.error("Usuário ou senha incorretos.")

def registrar_usuario(login, senha):
    df_usuarios = ler_aba("usuarios")
    if login in df_usuarios['login'].values:
        st.error("Este usuário já existe.")
    else:
        novo_id = len(df_usuarios) + 1
        novo_user = pd.DataFrame([{"id": novo_id, "login": login, "senha": senha}])
        df_final = pd.concat([df_usuarios, novo_user], ignore_index=True)
        salvar_dados("usuarios", df_final)
        st.success("Usuário criado!")

# --- FUNÇÕES DE PROCESSOS ---

def cadastrar_processo_sheet(num, cons, forn, tram, obs):
    df_proc = ler_aba("processos")
    df_hist = ler_aba("historico")
    
    novo_id = int(df_proc['id'].max() + 1) if not df_proc.empty else 1
    
    # Novo Processo
    novo_p = pd.DataFrame([{
        "id": novo_id, "numero": num, "consumidor": cons, 
        "fornecedor": forn, "tramitacao": tram, "anotacoes": obs
    }])
    
    # Novo Histórico
    novo_h = pd.DataFrame([{
        "id": len(df_hist) + 1, "processo_id": novo_id, 
        "tramitacao_texto": tram, "usuario_responsavel": st.session_state.usuario, 
        "data_mudanca": datetime.now().strftime("%d/%m/%Y %H:%M")
    }])
    
    salvar_dados("processos", pd.concat([df_proc, novo_p], ignore_index=True))
    salvar_dados("historico", pd.concat([df_hist, novo_h], ignore_index=True))
    st.success("Processo salvo no Google Sheets!")

def atualizar_tramitacao_sheet(p_id, nova_tram):
    df_proc = ler_aba("processos")
    df_hist = ler_aba("historico")
    
    # Atualiza na tabela de processos
    df_proc.loc[df_proc['id'] == p_id, 'tramitacao'] = nova_tram
    
    # Adiciona ao histórico
    novo_h = pd.DataFrame([{
        "id": len(df_hist) + 1, "processo_id": p_id, 
        "tramitacao_texto": nova_tram, "usuario_responsavel": st.session_state.usuario, 
        "data_mudanca": datetime.now().strftime("%d/%m/%Y %H:%M")
    }])
    
    salvar_dados("processos", df_proc)
    salvar_dados("historico", pd.concat([df_hist, novo_h], ignore_index=True))
    st.success("Tramitação atualizada!")
    st.rerun()

# --- (O RESTANTE DA INTERFACE SE MANTÉM IGUAL, CHAMANDO AS FUNÇÕES ACIMA) ---