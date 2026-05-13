import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import secrets

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Seindec Arapiraca - Sistema Integrado", layout="wide")

SESSION_HORAS = 5

# --- CONEXÃO COM GOOGLE SHEETS ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Erro na conexão com o Google Sheets. Verifique os Secrets.")
    st.stop()

# --- FUNÇÕES DE LEITURA E ESCRITA ---
def ler_aba(nome_aba):
    try:
        df = conn.read(worksheet=nome_aba, ttl=0)
        return df.dropna(how="all")
    except Exception:
        if nome_aba == "usuarios":
            return pd.DataFrame(columns=["id", "login", "senha"])
        elif nome_aba == "processos":
            return pd.DataFrame(columns=["id", "numero", "consumidor", "fornecedor", "tramitacao", "anotacoes"])
        elif nome_aba == "sessoes":
            return pd.DataFrame(columns=["token", "usuario", "expiry"])
        else:
            return pd.DataFrame(columns=["id", "processo_id", "tramitacao_texto", "usuario_responsavel", "data_mudanca"])

def salvar_dados(nome_aba, df_novo):
    try:
        conn.update(worksheet=nome_aba, data=df_novo)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erro ao salvar na planilha: {e}")

# --- FUNÇÕES DE SESSÃO (token na URL + registro no Google Sheets) ---
def criar_sessao(usuario):
    token = secrets.token_urlsafe(32)
    expiry = (datetime.now() + timedelta(hours=SESSION_HORAS)).strftime("%Y-%m-%d %H:%M:%S")
    df_s = ler_aba("sessoes")
    df_s = df_s[df_s["usuario"] != usuario]
    nova = pd.DataFrame([{"token": token, "usuario": usuario, "expiry": expiry}])
    salvar_dados("sessoes", pd.concat([df_s, nova], ignore_index=True))
    st.query_params["token"] = token
    st.session_state.logado = True
    st.session_state.usuario = usuario

def verificar_sessao():
    token = st.query_params.get("token")
    if not token:
        return None
    df_s = ler_aba("sessoes")
    if df_s.empty:
        return None
    linha = df_s[df_s["token"] == token]
    if linha.empty:
        return None
    try:
        expiry = datetime.strptime(str(linha.iloc[0]["expiry"]), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None
    if datetime.now() > expiry:
        return None
    return str(linha.iloc[0]["usuario"])

def encerrar_sessao():
    token = st.query_params.get("token")
    if token:
        df_s = ler_aba("sessoes")
        df_s = df_s[df_s["token"] != token]
        salvar_dados("sessoes", df_s)
    st.query_params.clear()
    st.session_state.logado = False
    st.session_state.usuario = None
    st.session_state.nav_history = []
    st.session_state.pagina_atual = "Listar Processos"

# --- INICIALIZAÇÃO DO SESSION STATE ---
if "logado" not in st.session_state:
    st.session_state.logado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "nav_history" not in st.session_state:
    st.session_state.nav_history = []
if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "Listar Processos"

# Recupera sessão do token na URL (sobrevive a refresh de página)
if not st.session_state.logado:
    usuario_recuperado = verificar_sessao()
    if usuario_recuperado:
        st.session_state.logado = True
        st.session_state.usuario = usuario_recuperado

# =====================================================================
# TELA DE LOGIN / CADASTRO
# =====================================================================
if not st.session_state.logado:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("⚖️ Sistema Seindec - PROCON Arapiraca")
        aba_l, aba_c = st.tabs(["Acessar", "Criar Conta"])

        with aba_l:
            u = st.text_input("Usuário", key="login_user")
            s = st.text_input("Senha", type="password", key="login_pass")
            if st.button("Entrar"):
                df_u = ler_aba("usuarios")
                user = df_u[(df_u["login"] == u) & (df_u["senha"].astype(str) == str(s))]
                if not user.empty:
                    criar_sessao(u)
                    st.rerun()
                else:
                    st.error("Login ou senha inválidos.")

        with aba_c:
            nu = st.text_input("Novo Usuário", key="reg_user")
            ns = st.text_input("Nova Senha", type="password", key="reg_pass")
            if st.button("Registrar"):
                df_u = ler_aba("usuarios")
                if nu in df_u["login"].values:
                    st.error("Usuário já existe.")
                else:
                    novo_u = pd.DataFrame([{"id": len(df_u) + 1, "login": nu, "senha": ns}])
                    salvar_dados("usuarios", pd.concat([df_u, novo_u], ignore_index=True))
                    st.success("Conta criada! Agora faça login.")
    st.stop()

# =====================================================================
# ÁREA LOGADA
# =====================================================================

def navegar_para(destino):
    if st.session_state.pagina_atual != destino:
        st.session_state.nav_history.append(st.session_state.pagina_atual)
        st.session_state.pagina_atual = destino

def voltar_pagina():
    if st.session_state.nav_history:
        st.session_state.pagina_atual = st.session_state.nav_history.pop()
    else:
        st.session_state.pagina_atual = "Listar Processos"

# --- SIDEBAR ---
st.sidebar.title(f"👤 {st.session_state.usuario}")
st.sidebar.markdown("---")

if st.session_state.nav_history:
    if st.sidebar.button("◀️ Voltar"):
        voltar_pagina()
        st.rerun()

if st.sidebar.button("🔍 Listar Processos"):
    navegar_para("Listar Processos")
    st.rerun()

if st.sidebar.button("📄 Cadastrar Processo"):
    navegar_para("Cadastrar Processo")
    st.rerun()

st.sidebar.markdown("---")

if st.sidebar.button("🚪 Sair"):
    encerrar_sessao()
    st.rerun()

st.sidebar.caption(f"Sessão ativa por até {SESSION_HORAS}h após o login.")

# =====================================================================
# CADASTRAR PROCESSO
# =====================================================================
menu = st.session_state.pagina_atual

if menu == "Cadastrar Processo":
    st.header("📄 Novo Cadastro")
    with st.form("novo_processo"):
        num  = st.text_input("Nº Processo")
        cons = st.text_input("Consumidor")
        forn = st.text_input("Fornecedor")
        tram = st.text_input("Tramitação Atual")
        obs  = st.text_area("Anotações")

        if st.form_submit_button("💾 Salvar"):
            df_p = ler_aba("processos")
            df_h = ler_aba("historico")
            p_id = int(df_p["id"].max() + 1) if not df_p.empty else 1

            novo_p = pd.DataFrame([{
                "id": p_id, "numero": num, "consumidor": cons,
                "fornecedor": forn, "tramitacao": tram, "anotacoes": obs
            }])
            novo_h = pd.DataFrame([{
                "id": len(df_h) + 1, "processo_id": p_id,
                "tramitacao_texto": tram,
                "usuario_responsavel": st.session_state.usuario,
                "data_mudanca": datetime.now().strftime("%d/%m/%Y %H:%M")
            }])

            salvar_dados("processos", pd.concat([df_p, novo_p], ignore_index=True))
            salvar_dados("historico", pd.concat([df_h, novo_h], ignore_index=True))
            st.success("✅ Processo salvo com sucesso!")

# =====================================================================
# LISTAR PROCESSOS
# =====================================================================
elif menu == "Listar Processos":
    st.header("🔍 Consulta de Processos")

    df_p_master = ler_aba("processos")
    df_h_master = ler_aba("historico")

    busca = st.text_input("Buscar por nome ou número")

    df_exibicao = df_p_master.copy()
    if busca:
        busca_numerica = "".join(filter(str.isdigit, busca))
        filtro_nome = df_exibicao["consumidor"].str.contains(busca, case=False, na=False)

        if busca_numerica:
            filtro_numero = (
                df_exibicao["numero"]
                .astype(str)
                .str.replace(r"\D", "", regex=True)
                .str.contains(busca_numerica, na=False)
            )
            df_exibicao = df_exibicao[filtro_nome | filtro_numero]
        else:
            filtro_numero_textual = df_exibicao["numero"].astype(str).str.contains(busca, case=False, na=False)
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

            # ── Botão para alternar modo de edição ──────────────────────
            edit_key = f"edit_mode_{p['id']}"
            if edit_key not in st.session_state:
                st.session_state[edit_key] = False

            label_btn = "✏️ Editar Processo" if not st.session_state[edit_key] else "✖️ Fechar Edição"
            if st.button(label_btn, key=f"toggle_{p['id']}"):
                st.session_state[edit_key] = not st.session_state[edit_key]
                st.rerun()

            # ── Formulário de edição ─────────────────────────────────────
            if st.session_state[edit_key]:
                st.subheader("✏️ Editar dados do processo")
                with st.form(f"form_edicao_{p['id']}"):
                    e_num  = st.text_input("Nº Processo",     value=str(p["numero"]))
                    e_cons = st.text_input("Consumidor",       value=str(p["consumidor"]))
                    e_forn = st.text_input("Fornecedor",       value=str(p["fornecedor"]))
                    e_tram = st.text_input("Tramitação Atual", value=str(p["tramitacao"]))
                    e_obs  = st.text_area ("Anotações",        value=str(p["anotacoes"]))

                    col_s, col_c = st.columns(2)
                    with col_s:
                        salvar_edicao = st.form_submit_button("💾 Salvar Alterações")
                    with col_c:
                        cancelar_edicao = st.form_submit_button("❌ Cancelar")

                    if salvar_edicao:
                        idx = df_p_master[df_p_master["id"] == p["id"]].index
                        df_p_master.loc[idx, "numero"]     = e_num
                        df_p_master.loc[idx, "consumidor"] = e_cons
                        df_p_master.loc[idx, "fornecedor"] = e_forn
                        df_p_master.loc[idx, "tramitacao"] = e_tram
                        df_p_master.loc[idx, "anotacoes"]  = e_obs
                        salvar_dados("processos", df_p_master)
                        st.session_state[edit_key] = False
                        st.success("✅ Processo atualizado com sucesso!")
                        st.rerun()

                    if cancelar_edicao:
                        st.session_state[edit_key] = False
                        st.rerun()

                st.divider()

            # ── Histórico de tramitações ─────────────────────────────────
            st.subheader("📜 Histórico de Tramitações")
            hist_p = df_h_master[df_h_master["processo_id"].astype(str) == str(p["id"])]
            if not hist_p.empty:
                st.dataframe(
                    hist_p[["data_mudanca", "tramitacao_texto", "usuario_responsavel"]]
                    .sort_index(ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Nenhum histórico encontrado.")

            st.divider()

            # ── Atualizar tramitação ─────────────────────────────────────
            nova_t = st.text_input("Nova Tramitação", key=f"in_{p['id']}")
            if st.button("✅ Confirmar Atualização", key=f"btn_{p['id']}"):
                if nova_t:
                    df_p_master.loc[df_p_master["id"] == p["id"], "tramitacao"] = nova_t
                    n_h = pd.DataFrame([{
                        "id": len(df_h_master) + 1,
                        "processo_id": p["id"],
                        "tramitacao_texto": nova_t,
                        "usuario_responsavel": st.session_state.usuario,
                        "data_mudanca": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    }])
                    salvar_dados("processos", df_p_master)
                    salvar_dados("historico", pd.concat([df_h_master, n_h], ignore_index=True))
                    st.success("✅ Tramitação atualizada!")
                    st.rerun()

# --- RODAPÉ ---
st.markdown(
    """
    <style>
    .footer {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: transparent; color: #888;
        text-align: center; padding: 10px;
        font-size: 12px;
    }
    </style>
    <div class="footer">
        Seindec AL — Sistema Extinto de Informações de Defesa do Consumidor de Alagoas — Unidade Arapiraca
    </div>
    """,
    unsafe_allow_html=True,
)
