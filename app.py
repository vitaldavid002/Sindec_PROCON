import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Seindec Arapiraca - Sistema Integrado", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Erro na conexão com o Google Sheets. Verifique os Secrets.")
    st.stop()

def ler_aba(nome_aba):
    try:
        df = conn.read(worksheet=nome_aba, ttl=0)
        return df.dropna(how="all")
    except Exception as e:
        if nome_aba == "usuarios":
            return pd.DataFrame(columns=["id", "login", "senha"])
        elif nome_aba == "processos":
            return pd.DataFrame(columns=["id", "numero", "consumidor", "fornecedor", "tramitacao", "anotacoes"])
        else:
            return pd.DataFrame(columns=["id", "processo_id", "tramitacao_texto", "usuario_responsavel", "data_mudanca"])

def salvar_dados(nome_aba, df_novo):
    try:
        conn.update(worksheet=nome_aba, data=df_novo)
        st.cache_data.clear() 
    except Exception as e:
        st.error(f"Erro ao salvar na planilha: {e}")

# --- CONTROLE DE ACESSO ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
if 'usuario' not in st.session_state:
    st.session_state.usuario = None

# --- TELAS DE LOGIN E CADASTRO ---
if not st.session_state.logado:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("⚖️ Sistema Seindec - PROCON Arapiraca")
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
    df_p_master = ler_aba("processos")
    df_h_master = ler_aba("historico")
    
    busca = st.text_input("Buscar por nome ou número")
    
    df_exibicao = df_p_master.copy()
    if busca:
        # --- LÓGICA DE PESQUISA POR ALGORITMOS (IGNORANDO PONTUAÇÃO) ---
        # Extrai apenas os dígitos da busca do usuário
        busca_numerica = "".join(filter(str.isdigit, busca))
        
        # Filtro por nome (Consumidor) - comportamento padrão
        filtro_nome = df_exibicao['consumidor'].str.contains(busca, case=False, na=False)
        
        if busca_numerica:
            # Se houver números na busca, limpa a coluna 'numero' da planilha (remove \D = não dígitos)
            # e compara com a busca numérica
            filtro_numero = df_exibicao['numero'].astype(str).str.replace(r'\D', '', regex=True).str.contains(busca_numerica, na=False)
            df_exibicao = df_exibicao[filtro_nome | filtro_numero]
        else:
            # Se não houver números na busca, filtra apenas pelo nome ou busca textual no número
            filtro_numero_textual = df_exibicao['numero'].astype(str).str.contains(busca, case=False, na=False)
            df_exibicao = df_exibicao[filtro_nome | filtro_numero_textual]

    for _, p in df_exibicao.iterrows():
        with st.expander(f"📦 {p['numero']} - {p['consumidor']}"):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Fornecedor:** {p['fornecedor']}")
                st.write(f"**Status Atual:** {p['tramitacao']}")
            with c2:
                st.write(f"**Anotações:** {p['anotacoes']}")
            
            st.divider()
            
            st.subheader("📜 Histórico de Tramitações")
            hist_p = df_h_master[df_h_master['processo_id'].astype(str) == str(p['id'])]
            if not hist_p.empty:
                st.dataframe(
                    hist_p[['data_mudanca', 'tramitacao_texto', 'usuario_responsavel']].sort_index(ascending=False), 
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Nenhum histórico encontrado.")

            st.divider()

            nova_t = st.text_input("Nova Tramitação", key=f"in_{p['id']}")
            if st.button("Confirmar Atualização", key=f"btn_{p['id']}"):
                if nova_t:
                    df_p_master.loc[df_p_master['id'] == p['id'], 'tramitacao'] = nova_t
                    n_h = pd.DataFrame([{
                        "id": len(df_h_master) + 1,
                        "processo_id": p['id'],
                        "tramitacao_texto": nova_t,
                        "usuario_responsavel": st.session_state.usuario,
                        "data_mudanca": datetime.now().strftime("%d/%m/%Y %H:%M")
                    }])
                    salvar_dados("processos", df_p_master)
                    salvar_dados("historico", pd.concat([df_h_master, n_h], ignore_index=True))
                    st.success("Atualizado!")
                    st.rerun()

# --- RODAPÉ PERSONALIZADO ---
st.markdown(
    """
    <style>
    .footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: transparent;
        color: #888;
        text-align: center;
        padding: 10px;
        font-size: 12px;
        font-weight: light;
    }
    </style>
    <div class="footer">
        Seindec AL - Sistema Extinto de Informações de Defesa do Consumidor de Alagoas - Unidade Arapiraca
    </div>
    """,
    unsafe_allow_html=True
)
