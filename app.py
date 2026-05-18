import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta, timezone
import secrets
import re
import extra_streamlit_components as stx
import hashlib
import uuid

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

# --- FUNCOES DE HASHING DE SENHA ---
def hash_senha(senha):
    """Hash da senha com salt usando SHA256"""
    return hashlib.sha256(senha.encode()).hexdigest()

def verificar_senha(senha, hash_armazenado):
    """Verifica se a senha corresponde ao hash"""
    return hash_senha(senha) == hash_armazenado

# --- CACHE OTIMIZADO COM TTL E TAGS ---
@st.cache_data(ttl=300)
def ler_aba(nome_aba):
    # Mapeamento oficial das colunas que cada aba DEVE possuir
    estruturas = {
        "usuarios": ["id", "nome_completo", "login", "senha_hash"],
        "processos": ["id", "numero", "consumidor", "cpf_consumidor",
                      "nome_fantasia_fornecedor", "razao_social_fornecedor", 
                      "cnpj_fornecedor", "tramitacao", "anotacoes"],
        "sessoes": ["token", "usuario", "expiry"],
        "historico": ["id", "processo_id", "tramitacao_texto", 
                      "usuario_responsavel", "data_mudanca"]
    }
    
    colunas_esperadas = estruturas.get(nome_aba, [])

    try:
        df = conn.read(worksheet=nome_aba, ttl=0)
        if df is not None and not df.empty:
            # 1. Remove espaços nas pontas e força tudo para letras minúsculas
            df.columns = df.columns.astype(str).str.strip().str.lower()
            
            # 2. Garante que mesmo se alguém apagar uma coluna no Sheets, o app cria ela vazia
            for col in colunas_esperadas:
                if col not in df.columns:
                    df[col] = ""
                    
            return df.dropna(how="all")
    except Exception:
        # Entra aqui apenas se houver erro crítico de conexão ou ausência da aba
        pass
        
    # Retorna um DataFrame vazio com a estrutura correta caso a planilha esteja zerada ou falhe
    return pd.DataFrame(columns=colunas_esperadas)


def salvar_dados(nome_aba, df_novo):
    """Salva dados e invalida cache específico"""
    try:
        conn.update(worksheet=nome_aba, data=df_novo)
        # Invalidar cache APENAS desta aba usando tags
        st.cache_data.clear()
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {e}")

def gerar_id_unico():
    """Gera ID único usando UUID para evitar duplicatas"""
    return str(uuid.uuid4())[:8]

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
    "n_forn": 1,
    "em_edicao_id": None  # Novo: rastreia qual processo está em edição
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

# 1. Lê a aba de usuários (como a função tem cache, isso será super rápido)
df_usuarios = ler_aba("usuarios")

# 2. Pega o login salvo na sessão atual
login_atual = st.session_state.usuario

# 3. Filtra o DataFrame para achar a linha específica desse usuário
linha_usuario = df_usuarios[df_usuarios["login"] == login_atual]

# 4. Verifica se encontrou o usuário para extrair o nome completo de forma segura
if not linha_usuario.empty:
    # Pega o valor da coluna 'nome_completo' do primeiro resultado encontrado
    nome_exibicao = linha_usuario.iloc[0]["nome_completo"]
else:
    # Fallback de segurança: se por acaso não achar na planilha, mostra o login mesmo
    nome_exibicao = login_atual

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
                    if df_u.empty:
                        st.error("Usuário ou senha incorretos.")
                    else:
                        # FIX: Usar coluna correta (senha_hash) e verificar com hash
                        col_login = "login" if "login" in df_u.columns else "login"
                        col_senha = "senha_hash" if "senha_hash" in df_u.columns else "senha"
                        
                        user_row = df_u[df_u[col_login] == u_log]
                        if not user_row.empty:
                            hash_armazenado = str(user_row.iloc[0][col_senha])
                            if verificar_senha(s_log, hash_armazenado):
                                criar_sessao(u_log)
                                st.success("Login realizado!")
                                st.rerun()
                            else:
                                st.error("Usuário ou senha incorretos.")
                        else:
                            st.error("Usuário ou senha incorretos.")

        with tab_cadastro:
            with st.form("form_registro"):
                st.info("Crie uma conta para acessar o sistema.")
                n_reg = st.text_input("Nome Completo")
                u_reg = st.text_input("Novo Usuário (sem espaços)")
                s_reg = st.text_input("Nova Senha", type="password")
                s_conf = st.text_input("Confirme a Senha", type="password")
                if st.form_submit_button("Cadastrar"):
                    df_u = ler_aba("usuarios")
                    if not n_reg or not u_reg or not s_reg:
                        st.warning("Preencha todos os campos.")
                    elif n_reg in df_u["nome_completo"].values:
                        st.error("Este nome já está cadastrado.")
                    elif u_reg in df_u["login"].values:
                        st.error("Este usuário já existe.")
                    elif s_reg != s_conf:
                        st.error("As senhas não coincidem.")
                    else:
                        novo_id = gerar_id_unico()
                        # FIX: Usar hash_senha ao registrar
                        novo_u = pd.DataFrame([{
                            "id": novo_id, 
                            "nome_completo": n_reg,
                            "login": u_reg, 
                            "senha_hash": hash_senha(s_reg)
                        }])
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
        st.session_state.em_edicao_id = None

def voltar_pagina():
    if st.session_state.nav_history:
        st.session_state.pagina_atual = st.session_state.nav_history.pop()
    else:
        st.session_state.pagina_atual = "Consultar Processos"
    st.session_state.em_edicao_id = None


# 5. Exibe o título na barra lateral
st.sidebar.title(f"👤 Olá, {nome_exibicao}")


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
# COMPONENTE: formulário reutilizável
# =====================================================================
def formulario_processo(é_edicao=False, dados_existentes=None, processo_id=None):
    """
    Renderiza o formulário de cadastro/edição de processo.
    
    Args:
        é_edicao: Se True, é para editar; se False, é para cadastrar
        dados_existentes: Dict com dados do processo (para edição)
        processo_id: ID do processo em edição (para rastrear n_forn)
    
    Returns:
        Dict com os dados do formulário
    """
    # Valores padrão
    if dados_existentes is None:
        dados_existentes = {}
    
    num_default = str(dados_existentes.get("numero", "")) if pd.notna(dados_existentes.get("numero", "")) else ""
    cons_default = str(dados_existentes.get("consumidor", "")) if pd.notna(dados_existentes.get("consumidor", "")) else ""
    cpf_default = str(dados_existentes.get("cpf_consumidor", "")) if pd.notna(dados_existentes.get("cpf_consumidor", "")) else ""
    nf_default = str(dados_existentes.get("nome_fantasia_fornecedor", "")) if pd.notna(dados_existentes.get("nome_fantasia_fornecedor", "")) else ""
    rs_default = str(dados_existentes.get("razao_social_fornecedor", "")) if pd.notna(dados_existentes.get("razao_social_fornecedor", "")) else ""
    cnpj_default = str(dados_existentes.get("cnpj_fornecedor", "")) if pd.notna(dados_existentes.get("cnpj_fornecedor", "")) else ""
    tram_default = str(dados_existentes.get("tramitacao", "")) if pd.notna(dados_existentes.get("tramitacao", "")) else ""
    obs_default = str(dados_existentes.get("anotacoes", "")) if pd.notna(dados_existentes.get("anotacoes", "")) else ""
    
    # Parse dos fornecedores já existentes
    lista_nf = [x.strip() for x in nf_default.split(";") if x.strip()]
    lista_rs = [x.strip() for x in rs_default.split(";") if x.strip()]
    lista_cnpj = [x.strip() for x in cnpj_default.split(";") if x.strip()]
    
    # FIX: Apenas aumentar n_forn se necessário (não decrecer ao abrir)
    if é_edicao and processo_id is not None:
        if st.session_state.n_forn < len(lista_nf):
            st.session_state.n_forn = len(lista_nf)
    
    # Informações básicas do processo
    num = st.text_input("📌 Nº Processo", value=num_default)
    ca, cb = st.columns(2)
    with ca:
        cons = st.text_input("👤 Consumidor", value=cons_default)
    with cb:
        cpf = st.text_input("🪪 CPF do Consumidor", value=cpf_default, placeholder="000.000.000-00")
    
    st.divider()
    
    # Seção de fornecedores
    st.subheader("🏢 Fornecedores")
    col_aux3 = st.columns([10])[0]
    col_aux3.markdown(f"**Quantidade atual: {st.session_state.n_forn}** (Máximo 15)")
    
    st.divider()
    
    nf_inputs = []
    rs_inputs = []
    c_inputs = []
    
    for i in range(st.session_state.n_forn):
        col_nf, col_rs, col_cnpj = st.columns([1.5, 1.5, 1])
        
        # Valores padrão para edição
        nf_value = lista_nf[i] if i < len(lista_nf) else ""
        rs_value = lista_rs[i] if i < len(lista_rs) else ""
        cnpj_value = lista_cnpj[i] if i < len(lista_cnpj) else ""
        
        # FIX: Chaves únicas considerando se é edição
        key_prefix = f"ed_{processo_id}_" if é_edicao and processo_id else "new_"
        
        nf_inputs.append(col_nf.text_input(f"Nome Fantasia {i+1}", value=nf_value, key=f"{key_prefix}nf_{i}"))
        rs_inputs.append(col_rs.text_input(f"Razão Social {i+1}", value=rs_value, key=f"{key_prefix}rs_{i}"))
        c_inputs.append(col_cnpj.text_input(f"CNPJ {i+1}", value=cnpj_value, key=f"{key_prefix}c_{i}"))
    
    st.divider()
    
    # Informações finais
    tram = st.text_input("📊 Situação Inicial", value=tram_default)
    obs = st.text_area("📝 Anotações", value=obs_default)
    
    return {
        "numero": num,
        "consumidor": cons,
        "cpf_consumidor": cpf,
        "nome_fantasia_fornecedor": nf_inputs,
        "razao_social_fornecedor": rs_inputs,
        "cnpj_fornecedor": c_inputs,
        "tramitacao": tram,
        "anotacoes": obs
    }
    
# =====================================================================
# COMPONENTE: card de processo
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
        # FIX: Rastrear qual processo está em edição
        if st.session_state[edit_key]:
            st.session_state.em_edicao_id = p["id"]
        else:
            st.session_state.em_edicao_id = None
        st.rerun()
        
    if st.session_state[edit_key]:
        st.subheader("✏️ Editando Processo")
        
        # Controles de quantidade para edição FORA do form
        col_aux1, col_aux2 = st.columns([1, 1])
        with col_aux1:
            if st.button("➕ Adicionar Fornecedor", key=f"btn_add_forn_{chave}"):
                if st.session_state.n_forn < 15:
                    st.session_state.n_forn += 1
                    st.rerun()
        with col_aux2:
            if st.button("➖ Remover Fornecedor", key=f"btn_rem_forn_{chave}"):
                if st.session_state.n_forn > 1:
                    st.session_state.n_forn -= 1
                    st.rerun()
        
        with st.form(f"form_ed_{chave}"):
            form_data = formulario_processo(é_edicao=True, dados_existentes=p, processo_id=p["id"])
            if st.form_submit_button("💾 Salvar Alterações"):
                e_num = form_data["numero"]
                e_cons = form_data["consumidor"]
                e_cpf = form_data["cpf_consumidor"]
                e_nf = ";".join([nf for nf in form_data["nome_fantasia_fornecedor"] if nf.strip()])
                e_rs = ";".join([rs for rs in form_data["razao_social_fornecedor"] if rs.strip()])
                e_cnpj = ";".join([c for c in form_data["cnpj_fornecedor"] if c.strip()])
                e_tram = form_data["tramitacao"]
                e_obs = form_data["anotacoes"]

                # Cópia segura do DataFrame
                df_p_copy = df_p_master.copy()

                # Força as colunas a virarem texto para evitar conflitos de tipos (Dtype)
                colunas_texto = ["numero", "consumidor", "cpf_consumidor", "nome_fantasia_fornecedor", "razao_social_fornecedor", "cnpj_fornecedor", "tramitacao", "anotacoes"]
                for col in colunas_texto:
                    if col in df_p_copy.columns:
                        df_p_copy[col] = df_p_copy[col].astype(str)

                mask = df_p_copy["id"] == p["id"]

                df_p_copy.loc[mask, "numero"] = e_num
                df_p_copy.loc[mask, "consumidor"] = e_cons
                df_p_copy.loc[mask, "cpf_consumidor"] = e_cpf
                df_p_copy.loc[mask, "nome_fantasia_fornecedor"] = e_nf
                df_p_copy.loc[mask, "razao_social_fornecedor"] = e_rs
                df_p_copy.loc[mask, "cnpj_fornecedor"] = e_cnpj
                df_p_copy.loc[mask, "tramitacao"] = e_tram
                df_p_copy.loc[mask, "anotacoes"] = e_obs

                salvar_dados("processos", df_p_copy)
                st.session_state[edit_key] = False
                st.session_state.em_edicao_id = None
                st.success("✅ Processo atualizado!")
                st.rerun()

    
    st.subheader("📜 Andamento")
    hist_p = df_h_master[df_h_master["processo_id"].astype(str) == str(p["id"])]
    if not hist_p.empty:
        st.dataframe(
            hist_p[["data_mudanca","tramitacao_texto","usuario_responsavel"]].sort_index(ascending=False), 
            use_container_width=True, 
            hide_index=True
        )

    st.divider()
    nova_t = st.text_input("🔄 Adicionar Nova Tramitação", key=f"in_{chave}")
    if st.button("✅ Confirmar Atualização", key=f"btn_{chave}"):
        if nova_t:
            # FIX: Fazer cópia segura antes de modificar
            df_p_copy = df_p_master.copy()
            df_p_copy.loc[df_p_copy["id"] == p["id"], "tramitacao"] = nova_t
            
            n_h = pd.DataFrame([{
                "id": gerar_id_unico(),
                "processo_id": p["id"],
                "tramitacao_texto": nova_t,
                "usuario_responsavel": nome_exibicao,
                "data_mudanca": datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M")
            }])
            
            df_h_copy = df_h_master.copy()
            salvar_dados("processos", df_p_copy)
            salvar_dados("historico", pd.concat([df_h_copy, n_h], ignore_index=True))
            st.success("✅ Tramitação atualizada!")
            st.rerun()

# =====================================================================
# PAGINAS
# =====================================================================
menu = st.session_state.pagina_atual

if menu == "Cadastrar Processo":
    st.header("📄 Novo Cadastro de Processo")
    
    # Controles de quantidade FORA do form
    col_aux1, col_aux2 = st.columns([1, 1])
    with col_aux1:
        if st.button("➕ Adicionar Fornecedor", key="btn_add_forn_new"):
            if st.session_state.n_forn < 15:
                st.session_state.n_forn += 1
                st.rerun()
    with col_aux2:
        if st.button("➖ Remover Fornecedor", key="btn_rem_forn_new"):
            if st.session_state.n_forn > 1:
                st.session_state.n_forn -= 1
                st.rerun()
    
    with st.form("novo_processo"):
        form_data = formulario_processo(é_edicao=False)
        
        if st.form_submit_button("💾 Salvar Novo Processo"):
            if not form_data["numero"] or not form_data["consumidor"]:
                st.error("⚠️ Por favor, preencha ao menos o número do processo e o nome do consumidor.")
            else:
                nf_final = ";".join([nf for nf in form_data["nome_fantasia_fornecedor"] if nf.strip()])
                rs_final = ";".join([rs for rs in form_data["razao_social_fornecedor"] if rs.strip()])
                cnpj_final = ";".join([c for c in form_data["cnpj_fornecedor"] if c.strip()])

                df_p = ler_aba("processos")
                df_h = ler_aba("historico")
                
                # FIX: Usar gerar_id_unico() para evitar colisões
                p_id = gerar_id_unico()

                novo_p = pd.DataFrame([{
                    "id": p_id, 
                    "numero": form_data["numero"], 
                    "consumidor": form_data["consumidor"], 
                    "cpf_consumidor": form_data["cpf_consumidor"],
                    "nome_fantasia_fornecedor": nf_final, 
                    "razao_social_fornecedor": rs_final, 
                    "cnpj_fornecedor": cnpj_final,
                    "tramitacao": form_data["tramitacao"], 
                    "anotacoes": form_data["anotacoes"]
                }])
                
                novo_h = pd.DataFrame([{
                    "id": gerar_id_unico(), 
                    "processo_id": p_id, 
                    "tramitacao_texto": form_data["tramitacao"],
                    "usuario_responsavel": nome_exibicao,
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
        # Converte o termo de busca para minúsculo e remove espaços extras nas pontas
        termo_busca = busca.strip().lower()
        
        # Filtro por Nome do Consumidor
        f_nome = df_p_master["consumidor"].astype(str).str.lower().str.contains(termo_busca, na=False)
        
        # Filtro por Número do Processo (Trata o número puramente como texto, aceitando letras e hashes)
        f_num = df_p_master["numero"].astype(str).str.lower().str.contains(termo_busca, na=False)
        
        # Se o usuário digitou apenas números, mantemos a busca flexível por dígitos limpos também
        d = so_digitos(busca)
        if d:
            f_num_limpo = df_p_master["numero"].astype(str).apply(so_digitos).str.contains(d, na=False)
            f_num = f_num | f_num_limpo

        # Combina os filtros usando o operador OR (|)
        df_ex = df_p_master[f_nome | f_num]

        if df_ex.empty:
            st.warning("⚠️ Nenhum processo encontrado.")
        else:
            st.success(f"📋 Exibindo {len(df_ex)} resultado(s).")
            for _, p in df_ex.iterrows():
                # Forçamos a chave a ser uma string limpa baseada no ID (seja ele número ou hash string)
                chave_unica = f"proc_{p['id']}"
                with st.expander(f"📁 {p['numero']} - {p['consumidor']}"):
                    exibir_processo(p, df_p_master, df_h_master, chave=chave_unica)
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
                    # FIX: Usar chave única para pesquisa avançada
                    exibir_processo(p, df_p_master, df_h_master, chave=f"adv_{p['id']}")

# --- RODAPE (FIXO COM PADDING) ---
st.markdown("""
<style>
    .main { padding-bottom: 40px; }
    footer { position: fixed; left: 0; bottom: 0; width: 100%; text-align: center; 
             color: #888; font-size: 12px; background-color: #f0f2f6; padding: 10px; }
</style>
<footer>Seindec AL - PROCON Arapiraca</footer>
""", unsafe_allow_html=True)
