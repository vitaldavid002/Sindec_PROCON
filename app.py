import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta, timezone
import secrets
import re

# --- CONFIGURACAO DO FUSO HORARIO BRASILIA ---
FUSO_BR = timezone(timedelta(hours=-3))

st.set_page_config(page_title="Seindec Arapiraca - Sistema Integrado", page_icon="⚖️", layout="wide")
SESSION_HORAS = 5

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("❌ Erro na conexao com o Google Sheets.")
    st.stop()

# --- FUNÇÕES DE APOIO ---
def ler_aba(nome_aba):
    try:
        df = conn.read(worksheet=nome_aba, ttl=0)
        return df.dropna(how="all")
    except Exception:
        if nome_aba == "usuarios": return pd.DataFrame(columns=["id", "login", "senha"])
        elif nome_aba == "processos": return pd.DataFrame(columns=["id", "numero", "consumidor", "cpf_consumidor", "fornecedor", "cnpj_fornecedor", "tramitacao", "anotacoes"])
        elif nome_aba == "sessoes": return pd.DataFrame(columns=["token", "usuario", "expiry"])
        else: return pd.DataFrame(columns=["id", "processo_id", "tramitacao_texto", "usuario_responsavel", "data_mudanca"])

def salvar_dados(nome_aba, df_novo):
    try:
        conn.update(worksheet=nome_aba, data=df_novo)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {e}")

def so_digitos(texto): return re.sub(r"\D", "", str(texto))
def filtro_texto(serie, termo): return serie.astype(str).str.contains(termo.strip(), case=False, na=False) if termo else pd.Series([True] * len(serie), index=serie.index)

def filtro_codigo(serie, termo):
    if not termo: return pd.Series([True] * len(serie), index=serie.index)
    d = so_digitos(termo)
    return serie.astype(str).apply(so_digitos).str.contains(d, na=False) if d else filtro_texto(serie, termo)

# --- SESSÃO E LOGIN (Mantidos conforme original) ---
def criar_sessao(usuario):
    token = secrets.token_urlsafe(32)
    expiry = (datetime.now(FUSO_BR) + timedelta(hours=SESSION_HORAS)).strftime("%Y-%m-%d %H:%M:%S")
    df_s = ler_aba("sessoes")
    df_s = df_s[df_s["usuario"] != usuario]
    nova = pd.DataFrame([{"token": token, "usuario": usuario, "expiry": expiry}])
    salvar_dados("sessoes", pd.concat([df_s, nova], ignore_index=True))
    st.query_params["token"] = token
    st.session_state.logado = True
    st.session_state.usuario = usuario

def verificar_sessao():
    token = st.query_params.get("token")
    if not token: return None
    df_s = ler_aba("sessoes")
    if df_s.empty: return None
    linha = df_s[df_s["token"] == token]
    if linha.empty: return None
    try:
        expiry = datetime.strptime(str(linha.iloc[0]["expiry"]), "%Y-%m-%d %H:%M:%S")
        if datetime.now(FUSO_BR).replace(tzinfo=None) > expiry: return None
    except: return None
    return str(linha.iloc[0]["usuario"])

def encerrar_sessao():
    token = st.query_params.get("token")
    if token:
        df_s = ler_aba("sessoes")
        salvar_dados("sessoes", df_s[df_s["token"] != token])
    st.query_params.clear()
    st.session_state.logado = False
    st.session_state.usuario = None
    st.session_state.nav_history = []
    st.session_state.pagina_atual = "Consultar Processos"

for chave, padrao in [("logado", False), ("usuario", None), ("nav_history", []), ("pagina_atual", "Consultar Processos")]:
    if chave not in st.session_state: st.session_state[chave] = padrao

if not st.session_state.logado:
    rec = verificar_sessao()
    if rec:
        st.session_state.logado = True
        st.session_state.usuario = rec

if not st.session_state.logado:
    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        st.title("⚖️ Sistema Seindec")
        aba_l, aba_c = st.tabs(["🔐 Acessar", "📝 Criar Conta"])
        with aba_l:
            u = st.text_input("👤 Usuário", key="login_user")
            s = st.text_input("🔑 Senha", type="password", key="login_pass")
            if st.button("✅ Entrar"):
                df_u = ler_aba("usuarios")
                ok = df_u[(df_u["login"] == u) & (df_u["senha"].astype(str) == str(s))]
                if not ok.empty: criar_sessao(u); st.rerun()
                else: st.error("⚠️ Login ou senha inválidos.")
        with aba_c:
            nu = st.text_input("👤 Novo Usuário", key="reg_user")
            ns = st.text_input("🔑 Nova Senha", type="password", key="reg_pass")
            if st.button("💾 Registrar"):
                df_u = ler_aba("usuarios")
                if nu in df_u["login"].values: st.error("⚠️ Usuário já existe.")
                else:
                    novo_u = pd.DataFrame([{"id": len(df_u)+1, "login": nu, "senha": ns}])
                    salvar_dados("usuarios", pd.concat([df_u, novo_u], ignore_index=True))
                    st.success("🎉 Conta criada!")
    st.stop()

# --- NAVEGAÇÃO ---
def navegar_para(destino):
    if st.session_state.pagina_atual != destino:
        st.session_state.nav_history.append(st.session_state.pagina_atual)
        st.session_state.pagina_atual = destino

def voltar_pagina():
    if st.session_state.nav_history: st.session_state.pagina_atual = st.session_state.nav_history.pop()
    else: st.session_state.pagina_atual = "Consultar Processos"

st.sidebar.title(f"👤 Olá, {st.session_state.usuario}")
if st.session_state.nav_history:
    if st.sidebar.button("⬅️ Voltar"): voltar_pagina(); st.rerun()

for label, pagina in [("🔍 Consultar Processos", "Consultar Processos"), ("🔎 Pesquisa Avançada", "Pesquisa Avancada"), ("📄 Cadastrar Processo", "Cadastrar Processo")]:
    if st.sidebar.button(label): navegar_para(pagina); st.rerun()

if st.sidebar.button("🚪 Sair"): encerrar_sessao(); st.rerun()

# =====================================================================
# COMPONENTE: CARD DE PROCESSO (ATUALIZADO PARA MÚLTIPLOS FORNECEDORES)
# =====================================================================
def exibir_processo(p, df_p_master, df_h_master, chave):
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**👤 Consumidor:** {p.get('consumidor','')} | **🪪 CPF:** `{p.get('cpf_consumidor','')}`")
        st.write(f"**📊 Situação Atual:** {p.get('tramitacao','')}")
    with c2:
        # Exibe fornecedores como lista se houver o delimitador ";"
        forns = str(p.get('fornecedor','')).split(';')
        cnpjs = str(p.get('cnpj_fornecedor','')).split(';')
        st.write("**🏢 Fornecedor(es):**")
        for f, c in zip(forns, cnpjs):
            st.write(f"- {f.strip()} (CNPJ: `{c.strip()}`)")
        st.write(f"**📝 Anotações:** {p.get('anotacoes','')}")

    st.divider()
    edit_key = f"edit_{chave}"
    if edit_key not in st.session_state: st.session_state[edit_key] = False

    if st.button("✏️ Editar Processo" if not st.session_state[edit_key] else "❌ Fechar Edição", key=f"toggle_{chave}"):
        st.session_state[edit_key] = not st.session_state[edit_key]; st.rerun()

    if st.session_state[edit_key]:
        with st.form(f"form_ed_{chave}"):
            e_num = st.text_input("Nº Processo", value=str(p.get("numero","")))
            ca, cb = st.columns(2)
            with ca: e_cons = st.text_input("👤 Consumidor", value=str(p.get("consumidor","")))
            with cb: e_cpf = st.text_input("🪪 CPF", value=str(p.get("cpf_consumidor","")))
            
            st.markdown("---")
            st.caption("🏢 Dados dos Fornecedores (Use ';' para separar múltiplos)")
            e_forn = st.text_area("Fornecedores", value=str(p.get("fornecedor","")), help="Ex: Empresa A; Empresa B")
            e_cnpj = st.text_area("CNPJs", value=str(p.get("cnpj_fornecedor","")), help="Ex: 00.000/0001-01; 00.000/0001-02")
            
            e_tram = st.text_input("📊 Tramitação", value=str(p.get("tramitacao","")))
            e_obs = st.text_area("📝 Anotações", value=str(p.get("anotacoes","")))
            
            if st.form_submit_button("💾 Salvar Alterações"):
                idx = df_p_master[df_p_master["id"] == p["id"]].index
                df_p_master.loc[idx, ["numero", "consumidor", "cpf_consumidor", "fornecedor", "cnpj_fornecedor", "tramitacao", "anotacoes"]] = [e_num, e_cons, e_cpf, e_forn, e_cnpj, e_tram, e_obs]
                salvar_dados("processos", df_p_master)
                st.session_state[edit_key] = False
                st.success("✅ Atualizado!"); st.rerun()

    # Histórico e Nova Tramitação (Mantidos)
    st.subheader("📜 Andamento")
    hist_p = df_h_master[df_h_master["processo_id"].astype(str) == str(p["id"])]
    if not hist_p.empty:
        st.dataframe(hist_p[["data_mudanca","tramitacao_texto","usuario_responsavel"]].sort_index(ascending=False), use_container_width=True, hide_index=True)
    
    nova_t = st.text_input("🔄 Adicionar Nova Tramitação", key=f"in_{chave}")
    if st.button("✅ Confirmar Atualização", key=f"btn_{chave}"):
        if nova_t:
            df_p_master.loc[df_p_master["id"] == p["id"], "tramitacao"] = nova_t
            n_h = pd.DataFrame([{"id": len(df_h_master)+1, "processo_id": p["id"], "tramitacao_texto": nova_t, "usuario_responsavel": st.session_state.usuario, "data_mudanca": datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M")}])
            salvar_dados("processos", df_p_master)
            salvar_dados("historico", pd.concat([df_h_master, n_h], ignore_index=True))
            st.success("✅ Sucesso!"); st.rerun()

# =====================================================================
# PÁGINAS: CADASTRAR PROCESSO (ATUALIZADO)
# =====================================================================
menu = st.session_state.pagina_atual

if menu == "Cadastrar Processo":
    st.header("📄 Novo Cadastro de Processo")
    
    # Gerenciamento de múltiplos fornecedores na UI
    if "qtd_forn" not in st.session_state: st.session_state.qtd_forn = 1
    
    with st.form("novo_processo"):
        num = st.text_input("📌 Nº Processo")
        c_cons, c_cpf = st.columns(2)
        cons = c_cons.text_input("👤 Consumidor")
        cpf = c_cpf.text_input("🪪 CPF")
        
        st.markdown("### 🏢 Fornecedores")
        num_fornecedores = st.number_input("Quantos fornecedores?", min_value=1, max_value=10, value=st.session_state.qtd_forn)
        
        lista_forn = []
        lista_cnpj = []
        
        for i in range(int(num_fornecedores)):
            f_col, c_col = st.columns([2, 1])
            f = f_col.text_input(f"Fornecedor {i+1}", key=f"f_{i}")
            c = c_col.text_input(f"CNPJ {i+1}", key=f"c_{i}")
            lista_forn.append(f)
            lista_cnpj.append(c)
            
        st.markdown("---")
        tram = st.text_input("📊 Situação Inicial")
        obs = st.text_area("📝 Anotações")

        if st.form_submit_button("💾 Salvar Novo Processo"):
            # Une os fornecedores com ponto e vírgula para salvar em uma única célula
            forn_final = "; ".join([x for x in lista_forn if x])
            cnpj_final = "; ".join([x for x in lista_cnpj if x])
            
            df_p = ler_aba("processos")
            df_h = ler_aba("historico")
            p_id = int(df_p["id"].max()+1) if not df_p.empty else 1
            
            novo_p = pd.DataFrame([{"id": p_id, "numero": num, "consumidor": cons, "cpf_consumidor": cpf, "fornecedor": forn_final, "cnpj_fornecedor": cnpj_final, "tramitacao": tram, "anotacoes": obs}])
            novo_h = pd.DataFrame([{"id": len(df_h)+1, "processo_id": p_id, "tramitacao_texto": tram, "usuario_responsavel": st.session_state.usuario, "data_mudanca": datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M")}])
            
            salvar_dados("processos", pd.concat([df_p, novo_p], ignore_index=True))
            salvar_dados("historico", pd.concat([df_h, novo_h], ignore_index=True))
            st.success("✅ Processo cadastrado com múltiplos fornecedores!")

# --- CONSULTA E PESQUISA (Permanecem iguais, agora lidando com strings separadas por ;) ---
elif menu == "Consultar Processos":
    st.header("🔍 Consultar Processos")
    df_p_master = ler_aba("processos")
    df_h_master = ler_aba("historico")
    busca = st.text_input("🔎 Buscar por consumidor ou número...")
    if busca.strip():
        d = so_digitos(busca)
        f_nome = df_p_master["consumidor"].astype(str).str.contains(busca.strip(), case=False, na=False)
        f_num = df_p_master["numero"].astype(str).apply(so_digitos).str.contains(d, na=False) if d else df_p_master["numero"].astype(str).str.contains(busca.strip(), case=False, na=False)
        df_ex = df_p_master[f_nome | f_num]
        for _, p in df_ex.iterrows():
            with st.expander(f"📁 {p['numero']} - {p['consumidor']}"):
                exibir_processo(p, df_p_master, df_h_master, chave=str(p["id"]))

elif menu == "Pesquisa Avancada":
    st.header("🔎 Pesquisa Avançada")
    df_p_master = ler_aba("processos")
    df_h_master = ler_aba("historico")
    with st.form("pesquisa_avancada"):
        col1, col2 = st.columns(2)
        f_numero = col1.text_input("📌 Número")
        f_consumidor = col1.text_input("👤 Consumidor")
        f_fornecedor = col2.text_input("🏢 Fornecedor")
        f_tramitacao = col2.text_input("📊 Tramitação")
        if st.form_submit_button("🚀 Pesquisar"):
            df_res = df_p_master.copy()
            if f_numero: df_res = df_res[filtro_codigo(df_res["numero"], f_numero)]
            if f_consumidor: df_res = df_res[filtro_texto(df_res["consumidor"], f_consumidor)]
            if f_fornecedor: df_res = df_res[filtro_texto(df_res["fornecedor"], f_fornecedor)]
            if f_tramitacao: df_res = df_res[filtro_texto(df_res["tramitacao"], f_tramitacao)]
            for _, p in df_res.iterrows():
                with st.expander(f"📁 {p['numero']} - {p['consumidor']}"):
                    exibir_processo(p, df_p_master, df_h_master, chave=f"adv_{p['id']}")

st.markdown("<div style='text-align:center; color:#888; font-size:12px;'>Seindec AL - Arapiraca</div>", unsafe_allow_html=True)
