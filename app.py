import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta, timezone
import secrets
import re
import extra_streamlit_components as stx

# --- CONFIGURACAO DO FUSO HORARIO BRASILIA ---
FUSO_BR = timezone(timedelta(hours=-3))

# --- CONFIGURACAO DA PAGINA ---
st.set_page_config(page_title="Seindec Arapiraca", page_icon="⚖️", layout="wide")

# Inicialize o CookieManager SEM o @st.cache_resource
cookie_manager = stx.CookieManager()

# Tempo de sessão
SESSION_HORAS = 5

# --- CONEXAO COM GOOGLE SHEETS ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("❌ Erro na conexao com o Google Sheets. Verifique os Secrets.")
    st.stop()

# --- CACHE OTIMIZADO COM TTL ---
@st.cache_data(ttl=300)  # Cache por 5 minutos
def ler_aba(nome_aba):
    try:
        df = conn.read(worksheet=nome_aba, ttl=0)
        return df.dropna(how="all")
    except Exception:
        if nome_aba == "usuarios":
            return pd.DataFrame(columns=["id", "login", "senha"])
        elif nome_aba == "processos":
            return pd.DataFrame(columns=[
                "id", "numero", "consumidor", "cpf_consumidor",
                "nome_fantasia_fornecedor", "razao_social_fornecedor", "cnpj_fornecedor", "tramitacao", "anotacoes"
            ])
        elif nome_aba == "sessoes":
            return pd.DataFrame(columns=["token", "usuario", "expiry"])
        else:
            return pd.DataFrame(columns=["id", "processo_id", "tramitacao_texto",
                                         "usuario_responsavel", "data_mudanca"])

def salvar_dados(nome_aba, df_novo):
    try:
        conn.update(worksheet=nome_aba, data=df_novo)
        # Limpar APENAS o cache da aba específica
        st.cache_data.clear()
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {e}")

# --- HELPERS DE PESQUISA ---
def so_digitos(texto):
    return re.sub(r"\D", "", str(texto))

def filtro_texto(serie, termo):
    if not termo:
        return pd.Series([True] * len(serie), index=serie.index)
    return serie.astype(str).str.contains(termo.strip(), case=False, na=False)

def filtro_codigo(serie, termo):
    if not termo:
        return pd.Series([True] * len(serie), index=serie.index)
    d = so_digitos(termo)
    if not d:
        return filtro_texto(serie, termo)
    return serie.astype(str).apply(so_digitos).str.contains(d, na=False)

# --- SESSAO ---
chaves_obrigatorias = {
    "logado": False,
    "usuario": None,
    "nav_history": [],
    "pagina_atual": "Consultar Processos",
    "n_forn": 1
}

for chave, valor_padrao in chaves_obrigatorias.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor_padrao

def criar_sessao(usuario):
    token = secrets.token_urlsafe(32)
    agora = datetime.now(FUSO_BR)
    data_expira = agora + timedelta(hours=SESSION_HORAS)
    texto_expira = data_expira.strftime("%Y-%m-%d %H:%M:%S")

    df_s = ler_aba("sessoes")
    df_s = df_s[df_s["usuario"] != usuario]

    nova_linha = pd.DataFrame([{
        "token": token,
        "usuario": usuario,
        "expiry": texto_expira
    }])

    salvar_dados("sessoes", pd.concat([df_s, nova_linha], ignore_index=True))

    cookie_manager.set(
        "seindec_token",
        token,
        expires_at=data_expira
    )

    st.session_state.logado = True
    st.session_state.usuario = usuario

def verificar_sessao():
    if cookie_manager is None:
        return None

    token = cookie_manager.get("seindec_token")

    if not token:
        return None

    df_s = ler_aba("sessoes")
    if df_s.empty:
        return None

    linha = df_s[df_s["token"] == token]
    if linha.empty:
        return None

    try:
        expiry_str = str(linha.iloc[0]["expiry"])
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")

        if datetime.now(FUSO_BR).replace(tzinfo=None) > expiry:
            cookie_manager.delete("seindec_token")
            return None
    except Exception:
        return None

    return str(linha.iloc[0]["usuario"])

def encerrar_sessao():
    token = cookie_manager.get("seindec_token")
    if token:
        df_s = ler_aba("sessoes")
        salvar_dados("sessoes", df_s[df_s["token"] != token])

    cookie_manager.delete("seindec_token")
    st.session_state.logado = False
    st.session_state.usuario = None
    st.rerun()

# --- INITIALIZE SESSION STATE ---
if "logado" not in st.session_state:
    st.session_state.logado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = None

if not st.session_state.logado:
    token_do_cookie = cookie_manager.get("seindec_token")

    if token_do_cookie:
        usuario_recuperado = verificar_sessao()
        if usuario_recuperado:
            st.session_state.logado = True
            st.session_state.usuario = usuario_recuperado
            st.rerun()
    else:
        st.title("⚖️ Sistema Seindec Arapiraca")

        tab_login, tab_cadastro = st.tabs(["🔐 Login", "📝 Cadastrar Usuário"])
        
        with tab_login:
            with st.form("form_login"):
                u_log = st.text_input("Usuário")
                s_log = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar"):
                    df_u = ler_aba("usuarios")
                    user_valido = df_u[(df_u["login"] == u_log) & (df_u["senha"].astype(str) == s_log)]
                    if not user_valido.empty:
                        criar_sessao(u_log)
                        st.success("Login realizado!")
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")

        with tab_cadastro:
            with st.form("form_registro"):
                st.info("Crie uma conta para acessar o sistema.")
                u_reg = st.text_input("Novo Usuário (sem espaços)")
                s_reg = st.text_input("Nova Senha", type="password")
                s_conf = st.text_input("Confirme a Senha", type="password")
                if st.form_submit_button("Cadastrar"):
                    df_u = ler_aba("usuarios")
                    if not u_reg or not s_reg:
                        st.warning("Preencha todos os campos.")
                    elif u_reg in df_u["login"].values:
                        st.error("Este usuário já existe.")
                    elif s_reg != s_conf:
                        st.error("As senhas não coincidem.")
                    else:
                        novo_id = int(df_u["id"].max() + 1) if not df_u.empty else 1
                        novo_u = pd.DataFrame([{"id": novo_id, "login": u_reg, "senha": s_reg}])
                        salvar_dados("usuarios", pd.concat([df_u, novo_u], ignore_index=True))
                        st.success("Usuário cadastrado com sucesso! Agora faça login.")

    st.stop()

# =====================================================================
# AREA LOGADA - NAVEGACAO
# =====================================================================
def navegar_para(destino):
    if st.session_state.pagina_atual != destino:
        st.session_state.nav_history.append(st.session_state.pagina_atual)
        st.session_state.pagina_atual = destino

def voltar_pagina():
    if st.session_state.nav_history:
        st.session_state.pagina_atual = st.session_state.nav_history.pop()
    else:
        st.session_state.pagina_atual = "Consultar Processos"

# SIDEBAR
st.sidebar.title(f"👤 Olá, {st.session_state.usuario}")
st.sidebar.markdown("---")

if st.session_state.nav_history:
    if st.sidebar.button("⬅️ Voltar"):
        voltar_pagina()
        st.rerun()

st.sidebar.subheader("📌 Navegação")
for label, pagina in [
    ("🔍 Consultar Processos", "Consultar Processos"),
    ("🔎 Pesquisa Avançada", "Pesquisa Avancada"),
    ("📄 Cadastrar Processo", "Cadastrar Processo"),
]:
    if st.sidebar.button(label):
        navegar_para(pagina)
        st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("🚪 Sair"):
    encerrar_sessao()
    st.rerun()

# =====================================================================
# COMPONENTE: card de processo - ATUALIZADO
# =====================================================================
def exibir_processo(p, df_p_master, df_h_master, chave):
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**👤 Consumidor:** {p.get('consumidor','')}  |  **🪪 CPF:** `{p.get('cpf_consumidor','')}`")
        st.write(f"**📊 Situação Atual:** {p.get('tramitacao','')}")
    with c2:
        lista_nf = str(p.get('nome_fantasia_fornecedor','')).split(';')
        lista_rs = str(p.get('razao_social_fornecedor','')).split(';')
        lista_c = str(p.get('cnpj_fornecedor','')).split(';')
        st.write("**🏢 Fornecedor(es):**")
        for nf, rs, cnpj in zip(lista_nf, lista_rs, lista_c):
            if nf.strip():
                st.write(f"- {nf.strip()} ({rs.strip()}) | CNPJ: `{cnpj.strip()}`")
        st.write(f"**📝 Anotações:** {p.get('anotacoes','')}")

    st.divider()
    edit_key = f"edit_{chave}"
    if edit_key not in st.session_state:
        st.session_state[edit_key] = False

    btn_label = "✏️ Editar Processo" if not st.session_state[edit_key] else "❌ Fechar Edição"
    if st.button(btn_label, key=f"toggle_{chave}"):
        st.session_state[edit_key] = not st.session_state[edit_key]
        st.rerun()

    if st.session_state[edit_key]:
        with st.form(f"form_ed_{chave}"):
            e_num = st.text_input("Nº Processo", value=str(p.get("numero","")))
            ca, cb = st.columns(2)
            with ca:
                e_cons = st.text_input("👤 Consumidor", value=str(p.get("consumidor","")))
            with cb:
                e_cpf = st.text_input("🪪 CPF do Consumidor", value=str(p.get("cpf_consumidor","")))
            
            st.divider()
            st.subheader("🏢 Fornecedores")
            
            cc, cd, ce = st.columns([1.5, 1.5, 1])
            with cc:
                e_nf = st.text_area("Nome Fantasia", value=str(p.get("nome_fantasia_fornecedor","")), help="Separe por ponto e vírgula")
            with cd:
                e_rs = st.text_area("Razão Social", value=str(p.get("razao_social_fornecedor","")), help="Separe por ponto e vírgula")
            with ce:
                e_cnpj = st.text_area("CNPJ(s)", value=str(p.get("cnpj_fornecedor","")), help="Separe por ponto e vírgula")
            
            st.divider()
            e_tram = st.text_input("📊 Tramitação Atual", value=str(p.get("tramitacao","")))
            e_obs  = st.text_area("📝 Anotações", value=str(p.get("anotacoes","")))
            if st.form_submit_button("💾 Salvar Alterações"):
                idx = df_p_master[df_p_master["id"] == p["id"]].index
                df_p_master.loc[idx, ["numero", "consumidor", "cpf_consumidor", "nome_fantasia_fornecedor", "razao_social_fornecedor", "cnpj_fornecedor", "tramitacao", "anotacoes"]] = [e_num, e_cons, e_cpf, e_nf, e_rs, e_cnpj, e_tram, e_obs]
                salvar_dados("processos", df_p_master)
                st.session_state[edit_key] = False
                st.success("✅ Processo atualizado!")
                st.rerun()

    st.subheader("📜 Andamento")
    hist_p = df_h_master[df_h_master["processo_id"].astype(str) == str(p["id"])]
    if not hist_p.empty:
        st.dataframe(hist_p[["data_mudanca","tramitacao_texto","usuario_responsavel"]].sort_index(ascending=False), use_container_width=True, hide_index=True)

    st.divider()
    nova_t = st.text_input("🔄 Adicionar Nova Tramitação", key=f"in_{chave}")
    if st.button("✅ Confirmar Atualização", key=f"btn_{chave}"):
        if nova_t:
            df_p_master.loc[df_p_master["id"] == p["id"], "tramitacao"] = nova_t
            n_h = pd.DataFrame([{
                "id": len(df_h_master)+1,
                "processo_id": p["id"],
                "tramitacao_texto": nova_t,
                "usuario_responsavel": st.session_state.usuario,
                "data_mudanca": datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M")
            }])
            salvar_dados("processos", df_p_master)
            salvar_dados("historico", pd.concat([df_h_master, n_h], ignore_index=True))
            st.success("✅ Tramitação atualizada!")
            st.rerun()

# =====================================================================
# PAGINAS
# =====================================================================
menu = st.session_state.pagina_atual

if menu == "Cadastrar Processo":
    st.header("📄 Novo Cadastro de Processo")

    with st.form("novo_processo", clear_on_submit=True):
        num = st.text_input("📌 Nº Processo")
        ca, cb = st.columns(2)
        with ca:
            cons = st.text_input("👤 Consumidor")
        with cb:
            cpf  = st.text_input("🪪 CPF do Consumidor", placeholder="000.000.000-00")

        st.divider()

        st.subheader("🏢 Fornecedores")
        
        # Controles de quantidade DENTRO do form
        col_aux1, col_aux2, col_aux3 = st.columns([1, 1, 10])
        
        if col_aux1.form_submit_button("➕", help="Adicionar Fornecedor"):
            if st.session_state.n_forn < 15:
                st.session_state.n_forn += 1
                st.rerun()

        if col_aux2.form_submit_button("➖", help="Remover Fornecedor"):
            if st.session_state.n_forn > 1:
                st.session_state.n_forn -= 1
                st.rerun()

        col_aux3.markdown(f"**Quantidade atual: {st.session_state.n_forn}** (Máximo 15)")

        st.divider()

        nf_inputs = []
        rs_inputs = []
        c_inputs = []

        for i in range(st.session_state.n_forn):
            col_nf, col_rs, col_cnpj = st.columns([1.5, 1.5, 1])
            nf_inputs.append(col_nf.text_input(f"Nome Fantasia {i+1}", key=f"nf_{i}"))
            rs_inputs.append(col_rs.text_input(f"Razão Social {i+1}", key=f"rs_{i}"))
            c_inputs.append(col_cnpj.text_input(f"CNPJ {i+1}", key=f"c_{i}"))

        st.divider()
        tram = st.text_input("📊 Situação Inicial")
        obs  = st.text_area("📝 Anotações")

        if st.form_submit_button("💾 Salvar Novo Processo"):
            if not num or not cons:
                st.error("⚠️ Por favor, preencha ao menos o número do processo e o nome do consumidor.")
            else:
                nf_final = ";".join([nf for nf in nf_inputs if nf.strip()])
                rs_final = ";".join([rs for rs in rs_inputs if rs.strip()])
                cnpj_final = ";".join([c for c in c_inputs if c.strip()])

                df_p = ler_aba("processos")
                df_h = ler_aba("historico")
                p_id = int(df_p["id"].max()+1) if not df_p.empty else 1

                novo_p = pd.DataFrame([{
                    "id": p_id, "numero": num, "consumidor": cons, "cpf_consumidor": cpf,
                    "nome_fantasia_fornecedor": nf_final, "razao_social_fornecedor": rs_final, 
                    "cnpj_fornecedor": cnpj_final,
                    "tramitacao": tram, "anotacoes": obs
                }])
                novo_h = pd.DataFrame([{
                    "id": len(df_h)+1, "processo_id": p_id, "tramitacao_texto": tram,
                    "usuario_responsavel": st.session_state.usuario,
                    "data_mudanca": datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M")
                }])

                salvar_dados("processos", pd.concat([df_p, novo_p], ignore_index=True))
                salvar_dados("historico", pd.concat([df_h, novo_h], ignore_index=True))
                st.success("✅ Processo salvo com sucesso!")
                st.session_state.n_forn = 1
                st.rerun()

elif menu == "Consultar Processos":
    st.header("🔍 Consultar Processos")
    df_p_master = ler_aba("processos")
    df_h_master = ler_aba("historico")
    busca = st.text_input("🔎 Digite o nome do consumidor ou número do processo para buscar...")

    if busca.strip():
        d = so_digitos(busca)
        f_nome = df_p_master["consumidor"].astype(str).str.contains(busca.strip(), case=False, na=False)
        f_num = df_p_master["numero"].astype(str).apply(so_digitos).str.contains(d, na=False) if d else df_p_master["numero"].astype(str).str.contains(busca.strip(), case=False, na=False)
        df_ex = df_p_master[f_nome | f_num]

        if df_ex.empty:
            st.warning("⚠️ Nenhum processo encontrado.")
        else:
            st.success(f"📋 Exibindo {len(df_ex)} resultado(s).")
            for _, p in df_ex.iterrows():
                with st.expander(f"📁 {p['numero']} - {p['consumidor']}"):
                    exibir_processo(p, df_p_master, df_h_master, chave=str(p["id"]))
    else:
        st.info("💡 Digite algo acima para pesquisar os processos cadastrados.")

elif menu == "Pesquisa Avancada":
    st.header("🔎 Pesquisa Avançada")
    st.caption("💡 Preencha um ou mais campos. Todos os filtros preenchidos serão aplicados juntos.")

    df_p_master = ler_aba("processos")
    df_h_master = ler_aba("historico")

    with st.form("pesquisa_avancada"):
        st.subheader("⚙️ Filtros de Busca")
        col1, col2 = st.columns(2)
        with col1:
            f_numero     = st.text_input("📌 Número do Processo",
                                         placeholder="Ex: 0001/2024 (Pontuação ignorada)")
            f_consumidor = st.text_input("👤 Nome do Consumidor")
            f_cpf        = st.text_input("🪪 CPF do Consumidor",
                                         placeholder="Ex: 123.456.789-00 (Pontuação ignorada)")
        with col2:
            f_nome_fantasia = st.text_input("🏢 Nome Fantasia do Fornecedor")
            f_razao_social  = st.text_input("📊 Razão Social do Fornecedor")
            f_cnpj       = st.text_input("📄 CNPJ do Fornecedor",
                                         placeholder="Ex: 00.000.000/0000-00 (Pontuação ignorada)")

        st.divider()
        f_tramitacao = st.text_input("📊 Tramitação Atual")

        pesquisar = st.form_submit_button("🚀 Pesquisar")

    if pesquisar:
        df_res = df_p_master.copy()

        if f_numero:
            df_res = df_res[filtro_codigo(df_res["numero"], f_numero)]
        if f_cpf:
            col_cpf = df_res["cpf_consumidor"] if "cpf_consumidor" in df_res.columns else pd.Series([""] * len(df_res), index=df_res.index)
            df_res = df_res[filtro_codigo(col_cpf, f_cpf)]
        if f_cnpj:
            col_cnpj = df_res["cnpj_fornecedor"] if "cnpj_fornecedor" in df_res.columns else pd.Series([""] * len(df_res), index=df_res.index)
            df_res = df_res[filtro_codigo(col_cnpj, f_cnpj)]
        if f_consumidor:
            df_res = df_res[filtro_texto(df_res["consumidor"], f_consumidor)]
        if f_nome_fantasia:
            col_nf = df_res["nome_fantasia_fornecedor"] if "nome_fantasia_fornecedor" in df_res.columns else pd.Series([""] * len(df_res), index=df_res.index)
            df_res = df_res[filtro_texto(col_nf, f_nome_fantasia)]
        if f_razao_social:
            col_rs = df_res["razao_social_fornecedor"] if "razao_social_fornecedor" in df_res.columns else pd.Series([""] * len(df_res), index=df_res.index)
            df_res = df_res[filtro_texto(col_rs, f_razao_social)]
        if f_tramitacao:
            df_res = df_res[filtro_texto(df_res["tramitacao"], f_tramitacao)]

        total = len(df_res)
        if total > 0:
            st.success(f"🎯 **{total} processo(s) encontrado(s)**")
        st.divider()

        if df_res.empty:
            st.warning("⚠️ Nenhum processo encontrado com os filtros informados.")
        else:
            for _, p in df_res.iterrows():
                with st.expander(f"📁 {p['numero']} - {p['consumidor']}"):
                    exibir_processo(p, df_p_master, df_h_master, chave=f"adv_{p['id']}")

# --- RODAPE ---
st.markdown("""<div style='position: fixed; left: 0; bottom: 0; width: 100%; text-align: center; color: #888; font-size: 12px;'>Seindec AL - PROCON Arapiraca</div>""", unsafe_allow_html=True)
