from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from datetime import datetime, date, timedelta
import os, json, random, math, base64
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__, static_folder='static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.secret_key = os.environ.get('SECRET_KEY', 'cd-gestao-2026-secret')
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_taxa_vigente(data=None):
    """Retorna a taxa vigente para uma data específica (ou hoje)."""
    conn = get_db(); cur = conn.cursor()
    if data is None:
        data = date.today()
    cur.execute("""SELECT * FROM taxas_pagamento
                   WHERE vigencia_em <= %s
                   ORDER BY vigencia_em DESC LIMIT 1""", (data,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if row:
        return dict(row)
    return {'credito_vista':2.06,'credito_parcelado':2.70,'debito':1.59,'link':0.0,'antecipacao':0.0}

def calcular_liquido(valor_bruto, forma_pagamento, taxa):
    """Calcula valor líquido após taxas da operadora + antecipação."""
    if not taxa: return valor_bruto, 0, 0
    taxa_op = 0
    fp = forma_pagamento or ''
    if fp == 'credito_vista':     taxa_op = float(taxa.get('credito_vista', 0))
    elif fp == 'credito_parcelado': taxa_op = float(taxa.get('credito_parcelado', 0))
    elif fp == 'debito':           taxa_op = float(taxa.get('debito', 0))
    elif fp == 'link':             taxa_op = float(taxa.get('link', 0))
    taxa_ant = float(taxa.get('antecipacao', 0))
    taxa_total = taxa_op + taxa_ant
    desconto = round(valor_bruto * taxa_total / 100, 2)
    liquido = round(valor_bruto - desconto, 2)
    return liquido, desconto, taxa_total

def parse_brl(val, default=0):
    """Converte valor BRL (1.000,00) ou americano (1000.00) para float."""
    try:
        if not val: return default
        s = str(val).strip().replace('R$','').replace(' ','')
        # Formato americano: tem ponto como decimal (ex: 120.00, 1000.50)
        # Formato BRL: tem vírgula como decimal (ex: 120,00 ou 1.000,00)
        if ',' in s and '.' in s:
            # Ex: 1.000,00 → BRL
            return float(s.replace('.','').replace(',','.'))
        elif ',' in s:
            # Ex: 120,00 → BRL sem milhar
            return float(s.replace(',','.'))
        else:
            # Ex: 120.00 ou 1000 → americano ou inteiro
            return float(s)
    except:
        return default


CLIENTE = {
    'nome': 'CD Gestao Empresarial',
    'loja': 'By Carol Duarte',
    'sigla': 'CD GESTAO',
    'tagline': 'Gestao inteligente para sua loja.',
    'cor_primaria': '#1a1a2e',
    'cor_secundaria': '#f4f4f6',
    'cor_botao': '#2e7d32'
}
CORES = ['#2e7d32','#1565c0','#6a1b9a','#c62828','#e65100','#00695c','#283593']

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10),
        nome VARCHAR(200) NOT NULL, senha_hash VARCHAR(300),
        perfil VARCHAR(20) DEFAULT 'vendedor',
        permissoes TEXT DEFAULT 'visao_geral,clientes,vendas,estoque',
        ativo BOOLEAN DEFAULT TRUE,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS clientes (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10),
        nome VARCHAR(200) NOT NULL, cpf VARCHAR(20),
        data_nascimento DATE, telefone VARCHAR(30), telefone2 VARCHAR(30),
        cep VARCHAR(10), logradouro VARCHAR(200), numero VARCHAR(20),
        complemento VARCHAR(100), bairro VARCHAR(100), cidade VARCHAR(100), uf VARCHAR(2),
        promocoes BOOLEAN DEFAULT TRUE, crediario BOOLEAN DEFAULT FALSE,
        ativo BOOLEAN DEFAULT TRUE, cor_avatar VARCHAR(10) DEFAULT '#2e7d32',
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS modelos_estoque (
        id SERIAL PRIMARY KEY, nome VARCHAR(100) UNIQUE NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS tamanhos_estoque (
        id SERIAL PRIMARY KEY, nome VARCHAR(20) UNIQUE NOT NULL)""")
    for m in ['Vestido','Calca','Blusa','Bolsa','Saia','Macacao','Conjunto','Short','Blazer']:
        cur.execute("INSERT INTO modelos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING",(m,))
    for t in ['PP','P','M','G','GG','EG','EGG','38','40','42','44','46','48','50','52','54','56','58','60','UNICO']:
        cur.execute("INSERT INTO tamanhos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING",(t,))
    cur.execute("""CREATE TABLE IF NOT EXISTS estoque (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE NOT NULL,
        modelo VARCHAR(100), descricao TEXT, tamanho VARCHAR(20),
        quantidade INTEGER DEFAULT 1, estoque_inicial INTEGER DEFAULT 1,
        custo_unitario NUMERIC(10,2) DEFAULT 0, markup NUMERIC(10,2) DEFAULT 0,
        valor_venda NUMERIC(10,2) DEFAULT 0, margem_lucro NUMERIC(10,2) DEFAULT 0,
        ativo BOOLEAN DEFAULT TRUE, ultima_venda DATE,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS estoque_entradas (
        id SERIAL PRIMARY KEY,
        estoque_id INTEGER NOT NULL,
        quantidade INTEGER NOT NULL,
        custo_unitario NUMERIC(10,2) DEFAULT 0,
        valor_venda NUMERIC(10,2) DEFAULT 0,
        markup NUMERIC(10,2) DEFAULT 0,
        margem_lucro NUMERIC(10,2) DEFAULT 0,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS vendas (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE,
        usuario_id INTEGER, vendedora_nome VARCHAR(200),
        cliente_id INTEGER, cliente_nome VARCHAR(200),
        valor_total NUMERIC(10,2) DEFAULT 0,
        desconto NUMERIC(10,2) DEFAULT 0,
        pct_desconto NUMERIC(6,2) DEFAULT 0,
        forma_pagamento VARCHAR(50), parcelas INTEGER DEFAULT 1,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS venda_itens (
        id SERIAL PRIMARY KEY,
        venda_id INTEGER REFERENCES vendas(id) ON DELETE CASCADE,
        produto_id INTEGER, codigo_produto VARCHAR(10),
        modelo VARCHAR(100), descricao TEXT, tamanho VARCHAR(20),
        valor_unitario NUMERIC(10,2) DEFAULT 0,
        quantidade INTEGER DEFAULT 1, valor_total NUMERIC(10,2) DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS crediarios (
        id SERIAL PRIMARY KEY,
        venda_id INTEGER REFERENCES vendas(id) ON DELETE CASCADE,
        cliente_id INTEGER, cliente_nome VARCHAR(200),
        valor_total NUMERIC(10,2) DEFAULT 0, entrada NUMERIC(10,2) DEFAULT 0,
        saldo_devedor NUMERIC(10,2) DEFAULT 0, status VARCHAR(20) DEFAULT 'aberto',
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS crediario_parcelas (
        id SERIAL PRIMARY KEY,
        crediario_id INTEGER REFERENCES crediarios(id) ON DELETE CASCADE,
        numero_parcela INTEGER, data_vencimento DATE,
        valor NUMERIC(10,2) DEFAULT 0,
        pago BOOLEAN DEFAULT FALSE, data_pagamento DATE)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS taxas_pagamento (
        id SERIAL PRIMARY KEY,
        vigencia_em DATE NOT NULL DEFAULT CURRENT_DATE,
        credito_vista NUMERIC(5,2) DEFAULT 2.06,
        credito_parcelado NUMERIC(5,2) DEFAULT 2.70,
        debito NUMERIC(5,2) DEFAULT 1.59,
        link NUMERIC(5,2) DEFAULT 0.00,
        antecipacao NUMERIC(5,2) DEFAULT 0.00,
        usuario_id INTEGER,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    # Inserir taxa padrão se não existir
    cur.execute("SELECT COUNT(*) as t FROM taxas_pagamento")
    if cur.fetchone()['t'] == 0:
        cur.execute("""INSERT INTO taxas_pagamento (vigencia_em,credito_vista,credito_parcelado,debito,link,antecipacao)
                       VALUES (CURRENT_DATE,2.06,2.70,1.59,0.00,0.00)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS caixa (
        id SERIAL PRIMARY KEY, descricao TEXT,
        valor NUMERIC(10,2) DEFAULT 0, tipo VARCHAR(20) DEFAULT 'entrada',
        forma_pagamento VARCHAR(50), venda_id INTEGER, crediario_id INTEGER,
        despesa_id INTEGER, usuario_id INTEGER, vendedora_nome VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS despesas (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE,
        descricao TEXT NOT NULL, categoria VARCHAR(100),
        valor NUMERIC(10,2) DEFAULT 0, data_despesa DATE DEFAULT CURRENT_DATE,
        forma_pagamento VARCHAR(50), usuario_id INTEGER, usuario_nome VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS despesa_categorias (
        id SERIAL PRIMARY KEY, nome VARCHAR(120) UNIQUE NOT NULL,
        ativo BOOLEAN DEFAULT TRUE, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS despesa_parcelas (
        id SERIAL PRIMARY KEY, despesa_id INTEGER, numero INTEGER,
        valor NUMERIC(10,2) DEFAULT 0, data_vencimento DATE,
        pago BOOLEAN DEFAULT FALSE, data_pagamento DATE,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS condicionais (
        id SERIAL PRIMARY KEY, codigo VARCHAR(12) UNIQUE,
        tipo VARCHAR(14) DEFAULT 'condicional',
        cliente_id INTEGER, cliente_nome VARCHAR(200),
        usuario_id INTEGER, vendedora_nome VARCHAR(200),
        valor_total NUMERIC(10,2) DEFAULT 0,
        status VARCHAR(20) DEFAULT 'aberta',
        venda_id INTEGER, observacao TEXT,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finalizado_em TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS condicional_itens (
        id SERIAL PRIMARY KEY,
        condicional_id INTEGER REFERENCES condicionais(id) ON DELETE CASCADE,
        produto_id INTEGER, codigo_produto VARCHAR(10),
        modelo VARCHAR(100), descricao TEXT, tamanho VARCHAR(20),
        valor_unitario NUMERIC(10,2) DEFAULT 0,
        quantidade INTEGER DEFAULT 1,
        status VARCHAR(20) DEFAULT 'pendente')""")
    conn.commit()
    # ── MIGRAÇÕES — adiciona colunas novas em tabelas existentes ──
    migracoes = [
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS reservado INTEGER DEFAULT 0",
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS foto TEXT",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS foto TEXT",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS desconto NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS pct_desconto NUMERIC(6,2) DEFAULT 0",
        "ALTER TABLE vendas ALTER COLUMN pct_desconto TYPE NUMERIC(6,2)",
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS dias_estoque INTEGER DEFAULT 0",
        "ALTER TABLE estoque_entradas ADD COLUMN IF NOT EXISTS markup NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE estoque_entradas ADD COLUMN IF NOT EXISTS margem_lucro NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS tipo VARCHAR(10) DEFAULT 'avulsa'",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS parcelado BOOLEAN DEFAULT FALSE",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS num_parcelas INTEGER DEFAULT 1",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS local_retirada VARCHAR(20)",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS obs_retirada TEXT",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS status VARCHAR(12) DEFAULT 'pago'",
        "ALTER TABLE despesas ALTER COLUMN descricao DROP NOT NULL",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS data_vencimento DATE",
    ]
    for sql in migracoes:
        try:
            cur.execute(sql)
        except Exception:
            conn.rollback()
    conn.commit()
    # ── PERFIS: converte 'admin' legado em 'admin_n1' (bloco isolado e commitado à parte) ──
    try:
        cur.execute("UPDATE usuarios SET perfil='admin_n1' WHERE perfil IN ('admin','administrador','Administrador')")
        conn.commit()
    except Exception:
        conn.rollback()
    # ── SEED de categorias de despesa (só insere o que faltar) ──
    CATEGORIAS_PADRAO = ['Salário','Aluguel','IPTU','Água','Luz','Imposto','Contador','MEI',
        'Internet','Empréstimo','Holerite','Modelo','Marketing','Publicidade',
        'Vale para funcionário','Costureira','Motoboy','Compra de Sacolas',
        'Produto de Limpeza','Degustação','Manutenção em geral','Aquisição de equipamentos',
        'Assinaturas','Cartão de Crédito']
    try:
        for nome in CATEGORIAS_PADRAO:
            cur.execute("INSERT INTO despesa_categorias (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING",(nome,))
        conn.commit()
    except Exception:
        conn.rollback()
    try:
        for cod, nome, senha in [('F1','Renan Barcellos','renan123'),('F2','Carol Duarte','carol123')]:
            cur.execute("SELECT id FROM usuarios WHERE nome=%s",(nome,))
            if not cur.fetchone():
                perms = 'visao_geral,clientes,vendas,estoque,condicionais,caixa,crediarios,despesas,taxas,dashboards'
                cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes) VALUES (%s,%s,%s,'admin_n1',%s)",
                    (cod,nome,generate_password_hash(senha),perms))
        conn.commit()
    except Exception as e:
        print(f"usuarios padrao: {e}"); conn.rollback()
    cur.close(); conn.close()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'uid' not in session: return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ══════════════ PERFIS E PERMISSÕES ══════════════
# Abas controláveis (id, rótulo). 'usuarios' é sempre acessível (troca de senha).
ABAS = [
    ('visao_geral', 'Visão Geral'),
    ('clientes',    'Clientes'),
    ('estoque',     'Estoque'),
    ('vendas',      'Vendas'),
    ('condicionais','Condicional'),
    ('caixa',       'Caixa'),
    ('crediarios',  'Crediários'),
    ('despesas',    'Despesas'),
    ('taxas',       'Taxas'),
    ('dashboards',  'Dashboards'),
]
ABAS_DICT = dict(ABAS)
# Primeiro segmento da URL -> aba
SEG_ABA = {
    'visao-geral':'visao_geral', 'clientes':'clientes', 'estoque':'estoque',
    'vendas':'vendas', 'condicionais':'condicionais', 'caixa':'caixa',
    'crediarios':'crediarios', 'despesas':'despesas', 'taxas':'taxas',
    'dashboard':'dashboards', 'usuarios':'usuarios',
}
# aba -> endpoint (para montar a home dinâmica)
ABA_ROUTE = {
    'visao_geral':'visao_geral', 'clientes':'clientes', 'estoque':'estoque',
    'vendas':'vendas', 'condicionais':'condicionais', 'caixa':'caixa',
    'crediarios':'crediarios', 'despesas':'despesas', 'taxas':'taxas',
    'dashboards':'dashboard_view',
}
# Endpoints liberados para qualquer logado (helpers e utilitários compartilhados)
ALLOW_ENDPOINTS = {'index','login','logout','setup','reset_usuarios','minha_senha',
    'versao','buscar_ref','buscar_cliente','usuarios_trocar_senha','limpar_caixa_orfaos'}
PERFIL_LABELS = {'admin_n1':'Administrador (a) N1','admin_n2':'Administrador (a) N2','vendedor':'Vendedor (a)'}

def norm_perfil(p):
    """Compatibilidade: o perfil legado 'admin' (antes da v85) equivale a Administrador N1."""
    if p == 'admin' or p == 'administrador': return 'admin_n1'
    return p or 'vendedor'

def perfil_label(p): p = norm_perfil(p); return PERFIL_LABELS.get(p, p or '—')
def is_admin(p=None): return norm_perfil(p if p is not None else session.get('perfil')) in ('admin_n1','admin_n2')
def pode_excluir(p=None): return norm_perfil(p if p is not None else session.get('perfil')) == 'admin_n1'
def pode_gerenciar_usuarios(p=None): return norm_perfil(p if p is not None else session.get('perfil')) == 'admin_n1'

def tem_acesso_aba(aba, perfil=None, permissoes=None):
    perfil = norm_perfil(perfil if perfil is not None else session.get('perfil','vendedor'))
    if perfil in ('admin_n1','admin_n2'): return True
    if aba == 'usuarios': return True   # todos podem entrar p/ trocar a própria senha
    perms = permissoes if permissoes is not None else (session.get('permissoes') or '')
    return aba in [x.strip() for x in perms.split(',') if x.strip()]

def home_url():
    """Primeira aba que o usuário pode acessar (evita cair numa aba bloqueada no login)."""
    perfil = norm_perfil(session.get('perfil'))
    if perfil in ('admin_n1','admin_n2'): return url_for('visao_geral')
    perms = [x.strip() for x in (session.get('permissoes') or '').split(',') if x.strip()]
    for aba in [a for a,_ in ABAS]:
        if aba in perms and aba in ABA_ROUTE:
            return url_for(ABA_ROUTE[aba])
    return url_for('usuarios')   # nada liberado: só troca de senha

def get_ctx():
    p = norm_perfil(session.get('perfil'))
    return dict(nome=session.get('nome'), perfil=p, cliente=CLIENTE,
                permissoes=session.get('permissoes',''),
                pode_excluir=(p == 'admin_n1'),
                pode_gerenciar_usuarios=(p == 'admin_n1'),
                is_admin_user=(p in ('admin_n1','admin_n2')),
                perfil_nome=perfil_label(p),
                usuario_foto=session.get('usuario_foto', False),
                avatar_v=session.get('foto_v', 0))

@app.before_request
def _controle_acesso_abas():
    if 'uid' not in session:
        return  # rotas públicas / login_required cuida do redirect
    ep = request.endpoint
    if ep is None or ep in ALLOW_ENDPOINTS or ep.startswith('static'):
        return
    seg = request.path.strip('/').split('/')[0] if request.path.strip('/') else ''
    aba = SEG_ABA.get(seg)
    if aba and not tem_acesso_aba(aba):
        ctx = get_ctx(); ctx['aba_negada'] = ABAS_DICT.get(aba, aba)
        return render_template('acesso_negado.html', **ctx), 403

@app.route('/setup')
def setup():
    try:
        init_db()
        return "<h2 style='font-family:sans-serif;padding:40px'>SETUP OK! <a href='/'>Login</a></h2>"
    except Exception as e:
        return "<pre style='padding:20px'>ERRO: " + str(e) + "</pre>", 500

@app.route('/reset-usuarios')
def reset_usuarios():
    conn = get_db(); cur = conn.cursor()
    try:
        for cod, nome, senha in [('F1','Renan Barcellos','renan123'),('F2','Carol Duarte','carol123')]:
            h = generate_password_hash(senha)
            perms = 'visao_geral,clientes,vendas,estoque,caixa,crediarios,despesas,usuarios,dashboards'
            cur.execute("SELECT id FROM usuarios WHERE nome=%s OR codigo=%s",(nome,cod))
            u = cur.fetchone()
            if u: cur.execute("UPDATE usuarios SET codigo=%s,senha_hash=%s,perfil='admin_n1',permissoes=%s,ativo=TRUE WHERE id=%s",(cod,h,perms,u['id']))
            else: cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes) VALUES (%s,%s,%s,'admin_n1',%s)",(cod,nome,h,perms))
        conn.commit()
        return "<h2 style='font-family:sans-serif;padding:40px'>Usuarios resetados! Renan Barcellos/renan123 Carol Duarte/carol123 <a href='/'>Login</a></h2>"
    except Exception as e:
        conn.rollback(); return "<pre>ERRO: " + str(e) + "</pre>"
    finally: cur.close(); conn.close()

@app.route('/')
def index():
    if 'uid' in session: return redirect(home_url())
    return render_template('login.html', cliente=CLIENTE, erro=None)

@app.route('/login', methods=['POST'])
def login():
    nome = request.form.get('usuario','').strip()
    senha = request.form.get('senha','').strip()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE nome=%s AND ativo=TRUE",(nome,))
    u = cur.fetchone(); cur.close(); conn.close()
    if u and check_password_hash(u['senha_hash'], senha):
        session.update(uid=u['id'], nome=u['nome'], perfil=norm_perfil(u['perfil']),
                       codigo=u.get('codigo',''),
                       permissoes=u.get('permissoes','visao_geral,clientes,vendas,estoque'),
                       usuario_foto=bool(u.get('foto')), foto_v=1)
        return redirect(home_url())
    return render_template('login.html', cliente=CLIENTE, erro='Usuario ou senha incorretos.')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'))

@app.route('/visao-geral')
@login_required
def visao_geral():
    conn = get_db(); cur = conn.cursor()
    hoje = datetime.now()
    # Período (mesmo padrão da aba Caixa)
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim    = request.args.get('data_fim',    hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = hoje.strftime('%Y-%m-%d')
    # Faturamento por forma = dinheiro REAL recebido (caixa entradas).
    # Crediário não aparece como forma própria: a entrada e as parcelas já
    # entram no caixa com a forma real (pix/dinheiro/cartão), então são contabilizadas aqui.
    formas = ['dinheiro','pix','debito','credito_vista','credito_parcelado','link']
    formas_com_taxa = ['credito_vista','credito_parcelado','debito','link']
    fat     = {f:0.0 for f in formas}   # bruto por forma
    fat_liq = {f:0.0 for f in formas}   # líquido por forma (após taxas de cartão)
    try:
        cur.execute("""SELECT forma_pagamento, valor, criado_em FROM caixa
                       WHERE tipo='entrada' AND DATE(criado_em) BETWEEN %s AND %s""", (data_inicio, data_fim))
        for r in cur.fetchall():
            f = r['forma_pagamento'] or ''
            if f not in fat: continue   # ignora 'crediario' legado / nulos
            bruto = float(r['valor'] or 0)
            fat[f] += bruto
            if f in formas_com_taxa:
                taxa_data = get_taxa_vigente(r['criado_em'].date() if hasattr(r['criado_em'],'date') else date.today())
                liq, _d, _p = calcular_liquido(bruto, f, taxa_data)
                fat_liq[f] += liq
            else:
                fat_liq[f] += bruto
    except Exception:
        pass
    fat     = {k: round(v,2) for k,v in fat.items()}
    fat_liq = {k: round(v,2) for k,v in fat_liq.items()}
    fat_total     = round(sum(fat.values()), 2)
    fat_total_liq = round(sum(fat_liq.values()), 2)
    # Estoque — custo, valor de venda, lucro potencial (sempre global, não filtra por período)
    try:
        cur.execute("""SELECT COALESCE(SUM(custo_unitario*quantidade),0) as ct,
                              COALESCE(SUM(valor_venda*quantidade),0)   as vt
                       FROM estoque WHERE ativo=TRUE""")
        r = cur.fetchone()
        custo_estoque   = round(float(r['ct']), 2)
        val_estoque     = round(float(r['vt']), 2)
        lucro_potencial = round(val_estoque - custo_estoque, 2)
    except: custo_estoque = val_estoque = lucro_potencial = 0.0
    # Crediários em aberto (global)
    try:
        cur.execute("SELECT COALESCE(SUM(saldo_devedor),0) as v FROM crediarios WHERE status='aberto'")
        val_crediarios = round(float(cur.fetchone()['v']), 2)
    except: val_crediarios = 0.0
    # Condicional / transferência em aberto (global)
    try:
        cur.execute("SELECT COALESCE(SUM(valor_total),0) as v, COUNT(*) as n FROM condicionais WHERE status='aberta'")
        rc = cur.fetchone()
        val_condicional = round(float(rc['v']), 2); n_condicional = int(rc['n'])
    except: val_condicional = 0.0; n_condicional = 0
    # Despesas do período = saída REAL de caixa:
    #   • despesas à vista antigas (sem nenhuma parcela) pela data de lançamento
    #   • qualquer parcela (1x ou Nx) somente quando paga (pela data de pagamento)
    try:
        cur.execute("""SELECT
            COALESCE((SELECT SUM(valor) FROM despesas d
                      WHERE COALESCE(d.parcelado,FALSE)=FALSE
                        AND NOT EXISTS (SELECT 1 FROM despesa_parcelas p WHERE p.despesa_id=d.id)
                        AND DATE(d.criado_em) BETWEEN %s AND %s),0)
          + COALESCE((SELECT SUM(valor) FROM despesa_parcelas
                      WHERE pago=TRUE AND data_pagamento BETWEEN %s AND %s),0) as v""",
            (data_inicio, data_fim, data_inicio, data_fim))
        val_despesas = round(float(cur.fetchone()['v']), 2)
    except: val_despesas = 0.0
    # Lucro líquido do período = entradas líquidas − despesas do período
    lucro_liquido = round(fat_total_liq - val_despesas, 2)
    # Movimentações recentes (filtradas pelo período)
    try:
        cur.execute("""SELECT id,criado_em,vendedora_nome,cliente_nome,valor_total,forma_pagamento
                       FROM vendas WHERE DATE(criado_em) BETWEEN %s AND %s
                       ORDER BY criado_em DESC LIMIT 8""", (data_inicio, data_fim))
        movs = [dict(r) for r in cur.fetchall()]
    except: movs = []
    try:
        cur.execute("SELECT codigo,modelo,tamanho,quantidade FROM estoque WHERE ativo=TRUE AND quantidade<=2 ORDER BY quantidade")
        estoque_baixo = [dict(r) for r in cur.fetchall()]
    except: estoque_baixo = []
    cur.close(); conn.close()
    ctx = get_ctx()
    ctx.update(fat=fat, fat_liq=fat_liq, fat_total=fat_total, fat_total_liq=fat_total_liq,
               custo_estoque=custo_estoque, val_estoque=val_estoque,
               lucro_potencial=lucro_potencial, val_crediarios=val_crediarios,
               val_condicional=val_condicional, n_condicional=n_condicional,
               val_despesas=val_despesas, lucro_liquido=lucro_liquido,
               movs=movs, estoque_baixo=estoque_baixo,
               data_inicio=data_inicio, data_fim=data_fim,
               mes_atual=hoje.strftime('%B / %Y').capitalize(),
               hoje=hoje.strftime('%A, %d de %B de %Y').capitalize())
    return render_template('visao_geral.html', **ctx)

def _perms_do_form(perfil):
    """Vendedor: usa as abas marcadas. Admins: acesso total (todas as abas)."""
    if perfil == 'vendedor':
        sel = [a for a in request.form.getlist('permissoes') if a in ABAS_DICT]
        return ','.join(sel)
    return ','.join([a for a,_ in ABAS])

@app.route('/usuarios')
@login_required
def usuarios():
    ctx = get_ctx()
    if pode_gerenciar_usuarios():
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios ORDER BY id")
        lista = [dict(u) for u in cur.fetchall()]
        cur.close(); conn.close()
        for u in lista:
            u['perfil_nome'] = perfil_label(u.get('perfil'))
        ctx['usuarios'] = lista
    # não-N1 caem no modo "somente minha senha" (tratado no template)
    return render_template('usuarios.html', **ctx)

@app.route('/usuarios/senha', methods=['POST'])
@login_required
def usuarios_trocar_senha():
    atual = request.form.get('senha_atual','')
    nova = request.form.get('nova_senha','')
    conf = request.form.get('confirma_senha','')
    if not nova or len(nova) < 4:
        flash('A nova senha deve ter ao menos 4 caracteres.','erro'); return redirect(url_for('usuarios'))
    if nova != conf:
        flash('A confirmação não confere com a nova senha.','erro'); return redirect(url_for('usuarios'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT senha_hash FROM usuarios WHERE id=%s",(session['uid'],))
    u = cur.fetchone()
    if u and check_password_hash(u['senha_hash'], atual):
        cur.execute("UPDATE usuarios SET senha_hash=%s WHERE id=%s",(generate_password_hash(nova),session['uid']))
        conn.commit(); flash('Senha alterada com sucesso!','ok')
    else:
        flash('Senha atual incorreta.','erro')
    cur.close(); conn.close()
    return redirect(url_for('usuarios'))

def _foto_valida(foto):
    """Valida data URI de imagem e limita o tamanho (~1.5MB de base64)."""
    if foto and foto.startswith('data:image/') and len(foto) <= 1_500_000:
        return foto
    return None

@app.route('/usuarios/avatar')
@login_required
def usuario_avatar():
    uid = request.args.get('uid') or session.get('uid')
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT foto FROM usuarios WHERE id=%s", (uid,))
    row = cur.fetchone(); cur.close(); conn.close()
    foto = row['foto'] if row else None
    if foto and foto.startswith('data:'):
        try:
            header, b64 = foto.split(',', 1)
            mime = header.split(';')[0].replace('data:', '') or 'image/jpeg'
            resp = Response(base64.b64decode(b64), mimetype=mime)
            resp.headers['Cache-Control'] = 'no-cache'
            return resp
        except Exception:
            pass
    return ('', 404)

@app.route('/usuarios/foto', methods=['POST'])
@login_required
def usuario_foto():
    foto = _foto_valida(request.form.get('foto','').strip())
    if not foto:
        flash('Imagem inválida ou muito grande.','erro'); return redirect(request.referrer or url_for('usuarios'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("UPDATE usuarios SET foto=%s WHERE id=%s", (foto, session['uid']))
        conn.commit()
        session['usuario_foto'] = True
        session['foto_v'] = session.get('foto_v', 0) + 1
        flash('Foto de perfil atualizada!','ok')
    except Exception as e:
        conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(request.referrer or url_for('usuarios'))

@app.route('/usuarios/foto/remover', methods=['POST'])
@login_required
def usuario_foto_remover():
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("UPDATE usuarios SET foto=NULL WHERE id=%s", (session['uid'],))
        conn.commit()
        session['usuario_foto'] = False
        session['foto_v'] = session.get('foto_v', 0) + 1
        flash('Foto de perfil removida.','ok')
    except Exception as e:
        conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(request.referrer or url_for('usuarios'))

@app.route('/usuarios/novo', methods=['GET','POST'])
@login_required
def usuario_novo():
    if not pode_gerenciar_usuarios():
        flash('Apenas o Administrador N1 pode cadastrar usuários.','erro')
        return redirect(url_for('usuarios'))
    ctx = get_ctx(); ctx['abas'] = ABAS
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        senha = request.form.get('senha','').strip()
        perfil = request.form.get('perfil','vendedor')
        if perfil not in ('admin_n1','admin_n2','vendedor'): perfil = 'vendedor'
        if not nome or len(senha) < 4:
            flash('Informe o nome e uma senha de ao menos 4 caracteres.','erro')
            return render_template('usuario_form.html', **ctx)
        perms = _perms_do_form(perfil)
        foto = _foto_valida(request.form.get('foto','').strip())
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as t FROM usuarios"); n = cur.fetchone()['t']
        try:
            cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes,foto) VALUES (%s,%s,%s,%s,%s,%s)",
                        (f"F{n+1}",nome,generate_password_hash(senha),perfil,perms,foto))
            conn.commit(); flash('Usuário cadastrado!','ok')
        except Exception as e: conn.rollback(); flash(str(e),'erro')
        finally: cur.close(); conn.close()
        return redirect(url_for('usuarios'))
    return render_template('usuario_form.html', **ctx)

@app.route('/usuarios/<int:uid>/editar', methods=['GET','POST'])
@login_required
def usuario_editar(uid):
    if not pode_gerenciar_usuarios():
        flash('Apenas o Administrador N1 pode editar usuários.','erro')
        return redirect(url_for('usuarios'))
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        perfil = request.form.get('perfil','vendedor')
        if perfil not in ('admin_n1','admin_n2','vendedor'): perfil = 'vendedor'
        # Trava anti-bloqueio: N1 não pode rebaixar o próprio perfil
        if uid == session.get('uid') and perfil != 'admin_n1':
            flash('Você não pode alterar o seu próprio perfil de Administrador N1.','erro')
            cur.close(); conn.close(); return redirect(url_for('usuarios'))
        perms = _perms_do_form(perfil)
        nova_senha = request.form.get('nova_senha','').strip()
        if nova_senha:
            cur.execute("UPDATE usuarios SET nome=%s,perfil=%s,permissoes=%s,senha_hash=%s WHERE id=%s",
                        (nome,perfil,perms,generate_password_hash(nova_senha),uid))
        else:
            cur.execute("UPDATE usuarios SET nome=%s,perfil=%s,permissoes=%s WHERE id=%s",(nome,perfil,perms,uid))
        conn.commit(); cur.close(); conn.close()
        flash('Usuario atualizado!','ok')
        return redirect(url_for('usuarios'))
    cur.execute("SELECT * FROM usuarios WHERE id=%s",(uid,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        flash('Usuario nao encontrado.','erro'); return redirect(url_for('usuarios'))
    user = dict(row)
    user['perms_lista'] = [x.strip() for x in (user.get('permissoes') or '').split(',') if x.strip()]
    cur.close(); conn.close()
    ctx = get_ctx(); ctx['user'] = user; ctx['abas'] = ABAS
    return render_template('usuario_editar.html', **ctx)

@app.route('/usuarios/<int:uid>/toggle', methods=['POST'])
@login_required
def usuario_toggle(uid):
    if not pode_gerenciar_usuarios():
        flash('Apenas o Administrador N1 pode ativar/desativar usuários.','erro')
        return redirect(url_for('usuarios'))
    if uid == session.get('uid'):
        flash('Você não pode desativar a si mesmo.','erro')
        return redirect(url_for('usuarios'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE usuarios SET ativo=NOT ativo WHERE id=%s",(uid,))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for('usuarios'))

@app.route('/usuarios/<int:uid>/excluir', methods=['POST'])
@login_required
def usuario_excluir(uid):
    if not pode_gerenciar_usuarios():
        flash('Apenas o Administrador N1 pode excluir usuários.','erro')
        return redirect(url_for('usuarios'))
    if uid == session.get('uid'):
        flash('Você não pode excluir a si mesmo.','erro')
        return redirect(url_for('usuarios'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM usuarios WHERE id=%s",(uid,))
        conn.commit(); flash('Usuário excluído.','ok')
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('usuarios'))

@app.route('/minha-senha', methods=['GET','POST'])
@login_required
def minha_senha():
    ctx = get_ctx()
    if request.method == 'POST':
        atual = request.form.get('senha_atual','')
        nova = request.form.get('nova_senha','')
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT senha_hash FROM usuarios WHERE id=%s",(session['uid'],))
        u = cur.fetchone()
        if u and check_password_hash(u['senha_hash'],atual):
            cur.execute("UPDATE usuarios SET senha_hash=%s WHERE id=%s",(generate_password_hash(nova),session['uid']))
            conn.commit(); flash('Senha alterada!','ok')
        else: flash('Senha atual incorreta.','erro')
        cur.close(); conn.close()
    return render_template('minha_senha.html', **ctx)

@app.route('/clientes')
@login_required
def clientes():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE ativo=TRUE ORDER BY nome")
    lista = [dict(c) for c in cur.fetchall()]
    cur.execute("SELECT COUNT(*) as t FROM clientes"); n = cur.fetchone()['t']
    cur.close(); conn.close()
    for c in lista:
        p = c['nome'].split()
        c['iniciais'] = (p[0][0]+(p[1][0] if len(p)>1 else p[0][-1])).upper()
    ctx = get_ctx(); ctx.update(clientes=lista, next_id=f"C{n+1}")
    return render_template('clientes.html', **ctx)

@app.route('/clientes/novo', methods=['POST'])
@login_required
def novo_cliente():
    nome = request.form.get('nome','').strip()
    if not nome: flash('Nome obrigatorio.','erro'); return redirect(url_for('clientes'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM clientes WHERE LOWER(TRIM(nome))=LOWER(TRIM(%s))",(nome,))
    if cur.fetchone():
        cur.close(); conn.close()
        flash('DUPLICADO_NOME||'+nome,'erro'); return redirect(url_for('clientes'))
    cur.execute("SELECT COUNT(*) as t FROM clientes"); n = cur.fetchone()['t']
    try:
        cur.execute("""INSERT INTO clientes (codigo,nome,cpf,data_nascimento,telefone,telefone2,
            cep,logradouro,numero,complemento,bairro,cidade,uf,promocoes,crediario,cor_avatar)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (f"C{n+1}",nome,
             request.form.get('cpf','').strip() or None,
             request.form.get('data_nascimento') or None,
             request.form.get('telefone','').strip() or None,
             request.form.get('telefone2','').strip() or None,
             request.form.get('cep','').strip() or None,
             request.form.get('logradouro','').strip() or None,
             request.form.get('numero','').strip() or None,
             request.form.get('complemento','').strip() or None,
             request.form.get('bairro','').strip() or None,
             request.form.get('cidade','').strip() or None,
             request.form.get('uf','').strip() or None,
             request.form.get('promocoes','0')=='1',
             request.form.get('crediario','0')=='1',
             random.choice(CORES)))
        conn.commit(); flash('SUCESSO||Cliente cadastrado!','ok')
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('clientes'))

@app.route('/clientes/verificar')
@login_required
def verificar_cliente():
    campo = request.args.get('campo'); valor = request.args.get('valor','').strip()
    if not campo or not valor: return jsonify({'ok':True})
    conn = get_db(); cur = conn.cursor()
    if campo=='nome': cur.execute("SELECT id FROM clientes WHERE LOWER(nome)=LOWER(%s)",(valor,))
    elif campo=='cpf': cur.execute("SELECT id FROM clientes WHERE cpf=%s",(valor,))
    elif campo=='telefone': cur.execute("SELECT id FROM clientes WHERE telefone=%s OR telefone2=%s",(valor,valor))
    row = cur.fetchone(); cur.close(); conn.close()
    return jsonify({'ok': not bool(row)})

@app.route('/clientes/<int:cid>')
@login_required
def ficha_cliente(cid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE id=%s",(cid,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        flash('Cliente nao encontrado.','erro'); return redirect(url_for('clientes'))
    c = dict(row)
    p = c['nome'].split()
    c['iniciais'] = (p[0][0]+(p[1][0] if len(p)>1 else p[0][-1])).upper()
    ctx = get_ctx(); ctx['c'] = c
    return render_template('ficha_cliente.html', **ctx)

@app.route('/clientes/<int:cid>/editar', methods=['GET','POST'])
@login_required
def editar_cliente(cid):
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        cur.execute("""UPDATE clientes SET nome=%s,cpf=%s,data_nascimento=%s,telefone=%s,
            telefone2=%s,cep=%s,logradouro=%s,numero=%s,complemento=%s,bairro=%s,
            cidade=%s,uf=%s,promocoes=%s,crediario=%s WHERE id=%s""",
            (request.form.get('nome','').strip(),
             request.form.get('cpf','').strip() or None,
             request.form.get('data_nascimento') or None,
             request.form.get('telefone','').strip() or None,
             request.form.get('telefone2','').strip() or None,
             request.form.get('cep','').strip() or None,
             request.form.get('logradouro','').strip() or None,
             request.form.get('numero','').strip() or None,
             request.form.get('complemento','').strip() or None,
             request.form.get('bairro','').strip() or None,
             request.form.get('cidade','').strip() or None,
             request.form.get('uf','').strip() or None,
             request.form.get('promocoes','0')=='1',
             request.form.get('crediario','0')=='1', cid))
        conn.commit(); cur.close(); conn.close()
        flash('Cliente atualizado!','ok')
        return redirect(url_for('ficha_cliente',cid=cid))
    cur.execute("SELECT * FROM clientes WHERE id=%s",(cid,))
    c = cur.fetchone(); cur.close(); conn.close()
    if not c:
        flash('Cliente nao encontrado.','erro'); return redirect(url_for('clientes'))
    ctx = get_ctx(); ctx['c'] = c
    return render_template('editar_cliente.html', **ctx)

@app.route('/clientes/<int:cid>/excluir', methods=['POST'])
@login_required
def excluir_cliente(cid):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.','erro'); return redirect(url_for('clientes'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM clientes WHERE id=%s",(cid,))
    conn.commit(); cur.close(); conn.close()
    flash('Cliente excluido.','ok')
    return redirect(url_for('clientes'))

@app.route('/estoque')
@login_required
def estoque():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM estoque WHERE ativo=TRUE ORDER BY criado_em")
    itens = [dict(i) for i in cur.fetchall()]
    cur.execute("SELECT COALESCE(SUM(custo_unitario*quantidade),0) as ct, COALESCE(SUM(valor_venda*quantidade),0) as vt FROM estoque WHERE ativo=TRUE")
    tots = cur.fetchone()
    cur.execute("SELECT nome FROM modelos_estoque ORDER BY nome")
    modelos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT nome FROM tamanhos_estoque ORDER BY id")
    tamanhos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) as t FROM estoque"); n = cur.fetchone()['t']
    # Buscar total de entradas adicionais por item (mesma conexão, antes de fechar)
    cur.execute("SELECT estoque_id, COALESCE(SUM(quantidade),0) as total FROM estoque_entradas GROUP BY estoque_id")
    entradas_map = {r['estoque_id']: int(r['total']) for r in cur.fetchall()}
    cur.close(); conn.close()
    hoje = date.today()
    for i in itens:
        i['dias_estoque'] = (hoje - i['criado_em'].date()).days
        i['entradas_adicionais'] = entradas_map.get(i['id'], 0)
        i['saidas'] = max(0, (i['estoque_inicial'] or 0) + i['entradas_adicionais'] - i['quantidade'])
    ctx = get_ctx()
    ctx.update(itens=itens, modelos=modelos, tamanhos=tamanhos,
               custo_total=float(tots['ct']), valor_total=float(tots['vt']),
               lucro_potencial=float(tots['vt'])-float(tots['ct']),
               next_ref=f"P{n+1}")
    return render_template('estoque.html', **ctx)

@app.route('/estoque/novo', methods=['POST'])
@login_required
def novo_estoque():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as t FROM estoque"); n = cur.fetchone()['t']
    qtd = int(request.form.get('quantidade',1) or 1)
    custo_raw = request.form.get('custo_unitario','').strip()
    venda_raw = request.form.get('valor_venda','').strip()
    if not custo_raw or parse_brl(custo_raw) <= 0:
        flash('O custo unitário é obrigatório e deve ser maior que zero.','erro')
        cur.close(); conn.close()
        return redirect(url_for('estoque'))
    if not venda_raw or parse_brl(venda_raw) <= 0:
        flash('O valor de venda é obrigatório e deve ser maior que zero.','erro')
        cur.close(); conn.close()
        return redirect(url_for('estoque'))
    foto = request.form.get('foto','').strip() or None
    # Segurança: só aceita data URI de imagem e limita o tamanho (~1.5MB de base64)
    if foto and (not foto.startswith('data:image/') or len(foto) > 1_500_000):
        foto = None
    try:
        cur.execute("""INSERT INTO estoque (codigo,modelo,descricao,tamanho,quantidade,estoque_inicial,
            custo_unitario,markup,valor_venda,margem_lucro,foto) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (f"P{n+1}", request.form.get('modelo','').strip(),
             request.form.get('descricao','').strip() or None,
             request.form.get('tamanho','').strip(), qtd, qtd,
             parse_brl(request.form.get('custo_unitario','0')),
             parse_brl(request.form.get('markup','0')),
             parse_brl(request.form.get('valor_venda','0')),
             parse_brl(request.form.get('margem_lucro','0')), foto))
        conn.commit(); flash('Produto cadastrado!','ok')
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('estoque'))

@app.route('/estoque/<int:eid>/nova-entrada', methods=['POST'])
@login_required
def nova_entrada_estoque(eid):
    conn = get_db(); cur = conn.cursor()
    try:
        qtd = int(request.form.get('quantidade', 0) or 0)
        custo = parse_brl(request.form.get('custo_unitario', '0'))
        markup = parse_brl(request.form.get('markup', '0'))
        venda = parse_brl(request.form.get('valor_venda', '0'))
        margem = parse_brl(request.form.get('margem_lucro', '0'))
        if qtd <= 0:
            flash('Informe uma quantidade válida.', 'erro')
            return redirect(url_for('ficha_estoque', eid=eid))
        if custo <= 0:
            flash('O custo unitário é obrigatório para nova entrada.', 'erro')
            return redirect(url_for('ficha_estoque', eid=eid))
        if venda <= 0:
            flash('O valor de venda é obrigatório para nova entrada.', 'erro')
            return redirect(url_for('ficha_estoque', eid=eid))
        # Registrar entrada
        cur.execute("""INSERT INTO estoque_entradas (estoque_id, quantidade, custo_unitario, valor_venda, markup, margem_lucro)
                       VALUES (%s,%s,%s,%s,%s,%s)""", (eid, qtd, custo, venda, markup, margem))
        # Atualizar saldo e último custo/venda do produto
        cur.execute("""UPDATE estoque SET
                       quantidade = quantidade + %s,
                       custo_unitario = %s,
                       valor_venda = %s,
                       markup = %s,
                       margem_lucro = %s
                       WHERE id = %s""", (qtd, custo, venda, markup, margem, eid))
        conn.commit()
        flash(f'Nova entrada de {qtd} unidade(s) registrada com sucesso!', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('ficha_estoque', eid=eid))

@app.route('/estoque/modelo/novo', methods=['POST'])
@login_required
def novo_modelo():
    nome = request.form.get('nome','').strip()
    if nome:
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO modelos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING",(nome,))
        conn.commit(); cur.close(); conn.close()
    return redirect(url_for('estoque'))

@app.route('/estoque/tamanho/novo', methods=['POST'])
@login_required
def novo_tamanho():
    nome = request.form.get('nome','').strip()
    if nome:
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO tamanhos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING",(nome,))
        conn.commit(); cur.close(); conn.close()
    return redirect(url_for('estoque'))

@app.route('/estoque/etiquetas')
@login_required
def etiquetas():
    data = request.args.get('data', date.today().isoformat())
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT codigo,modelo,descricao,tamanho,valor_venda,quantidade FROM estoque WHERE DATE(criado_em)=%s AND ativo=TRUE ORDER BY id",(data,))
    itens = [dict(i) for i in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'itens':itens,'data':data})

@app.route('/estoque/etiqueta-busca')
@login_required
def etiqueta_busca():
    cod = request.args.get('codigo','').strip().upper()
    if cod and not cod.startswith('P'): cod = 'P' + cod
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id,codigo,modelo,descricao,tamanho,valor_venda,quantidade FROM estoque WHERE codigo=%s AND ativo=TRUE",(cod,))
    item = cur.fetchone(); cur.close(); conn.close()
    if item: return jsonify({'ok':True,'item':dict(item)})
    return jsonify({'ok':False})

@app.route('/estoque/<int:eid>')
@login_required
def ficha_estoque(eid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM estoque WHERE id=%s",(eid,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        flash('Produto nao encontrado.','erro'); return redirect(url_for('estoque'))
    item = dict(row)
    item['dias_estoque'] = (date.today() - item['criado_em'].date()).days
    item['saidas'] = (item['estoque_inicial'] or 0) - item['quantidade']
    ctx = get_ctx(); ctx['item'] = item
    return render_template('ficha_estoque.html', **ctx)

@app.route('/estoque/<int:eid>/editar', methods=['GET','POST'])
@login_required
def editar_estoque(eid):
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        qtd = int(request.form.get('quantidade',1) or 1)
        cur.execute("""UPDATE estoque SET modelo=%s,descricao=%s,tamanho=%s,quantidade=%s,
            custo_unitario=%s,markup=%s,valor_venda=%s,margem_lucro=%s WHERE id=%s""",
            (request.form.get('modelo','').strip(),
             request.form.get('descricao','').strip() or None,
             request.form.get('tamanho','').strip(), qtd,
             parse_brl(request.form.get('custo_unitario','0')),
             parse_brl(request.form.get('markup','0')),
             parse_brl(request.form.get('valor_venda','0')),
             parse_brl(request.form.get('margem_lucro','0')), eid))
        conn.commit(); cur.close(); conn.close()
        flash('Produto atualizado!','ok')
        return redirect(url_for('ficha_estoque',eid=eid))
    cur.execute("SELECT * FROM estoque WHERE id=%s",(eid,))
    item = cur.fetchone()
    if not item:
        cur.close(); conn.close()
        flash('Produto nao encontrado.','erro'); return redirect(url_for('estoque'))
    cur.execute("SELECT nome FROM modelos_estoque ORDER BY nome")
    modelos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT nome FROM tamanhos_estoque ORDER BY id")
    tamanhos = [r['nome'] for r in cur.fetchall()]
    cur.close(); conn.close()
    ctx = get_ctx(); ctx.update(item=item, modelos=modelos, tamanhos=tamanhos)
    return render_template('editar_estoque.html', **ctx)

@app.route('/estoque/<int:eid>/excluir', methods=['POST'])
@login_required
def excluir_estoque(eid):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.','erro'); return redirect(url_for('estoque'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM estoque WHERE id=%s",(eid,))
    conn.commit(); cur.close(); conn.close()
    flash('Produto excluido.','ok')
    return redirect(url_for('estoque'))

@app.route('/vendas')
@login_required
def vendas():
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE ativo=TRUE ORDER BY nome")
        vendedoras = [dict(u) for u in cur.fetchall()]
        cur.execute("SELECT id,codigo,nome,crediario FROM clientes WHERE ativo=TRUE ORDER BY nome")
        clientes_lista = [dict(c) for c in cur.fetchall()]
        hoje = date.today()
        data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
        data_fim    = request.args.get('data_fim',    hoje.strftime('%Y-%m-%d'))
        try: date.fromisoformat(data_inicio)
        except: data_inicio = hoje.strftime('%Y-%m-01')
        try: date.fromisoformat(data_fim)
        except: data_fim = hoje.strftime('%Y-%m-%d')
        cur.execute("""SELECT v.*, COUNT(vi.id) as qtd_itens FROM vendas v
            LEFT JOIN venda_itens vi ON vi.venda_id=v.id
            WHERE DATE(v.criado_em) BETWEEN %s AND %s
            GROUP BY v.id ORDER BY v.criado_em DESC""", (data_inicio, data_fim))
        lista_vendas = [dict(v) for v in cur.fetchall()]
        cur.execute("""SELECT c.*,v.criado_em as data_venda FROM crediarios c
            JOIN vendas v ON v.id=c.venda_id ORDER BY c.criado_em DESC""")
        lista_crediarios = [dict(c) for c in cur.fetchall()]
        mes_ini = datetime.now().replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        cur.execute("""SELECT vendedora_nome,COALESCE(SUM(valor_total),0) as total,
            COUNT(id) as num_vendas,COUNT(DISTINCT cliente_id) as clientes
            FROM vendas WHERE criado_em>=%s GROUP BY vendedora_nome ORDER BY total DESC""",(mes_ini,))
        ranking = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT DATE_TRUNC('month',criado_em) as mes FROM vendas ORDER BY mes DESC")
        meses = [{'mes_val':m['mes'].strftime('%Y-%m'),'mes_label':m['mes'].strftime('%B / %Y').capitalize()} for m in cur.fetchall()]
        cur.close(); conn.close()
        now_mes = datetime.now().strftime('%Y-%m')
        now_mes_label = datetime.now().strftime('%B / %Y').capitalize()
        ctx = get_ctx()
        ctx.update(vendedoras=vendedoras, clientes=clientes_lista,
                   lista_vendas=lista_vendas, lista_crediarios=lista_crediarios,
                   ranking=ranking, meses=meses, now_mes=now_mes, now_mes_label=now_mes_label,
                   data_inicio=data_inicio, data_fim=data_fim)
        return render_template('vendas.html', **ctx)
    except Exception as e:
        return "<pre style='padding:20px'>ERRO VENDAS: " + str(e) + "</pre>", 500

@app.route('/vendas/nova', methods=['POST'])
@login_required
def nova_venda():
    conn = get_db(); cur = conn.cursor()
    try:
        usuario_id = request.form.get('usuario_id')
        vendedora_nome = request.form.get('vendedora_nome','').strip()
        cliente_id = request.form.get('cliente_id')
        cliente_nome = request.form.get('cliente_nome','').strip()
        forma = request.form.get('forma_pagamento','').strip()
        parcelas = int(request.form.get('parcelas',1) or 1)
        valor_total  = parse_brl(request.form.get('valor_total','0'))
        desconto     = parse_brl(request.form.get('desconto_valor','0'))
        pct_desconto = min(100.0, max(0.0, parse_brl(request.form.get('pct_desconto','0'))))
        desconto     = min(desconto, valor_total)  # desconto nunca maior que o total
        itens = json.loads(request.form.get('itens','[]'))
        cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)),0) as n FROM vendas WHERE codigo ~ '^V[0-9]+$'")
        n = cur.fetchone()['n']
        cod = f"V{n+1}"
        cur.execute("""INSERT INTO vendas (codigo,usuario_id,vendedora_nome,cliente_id,cliente_nome,
            valor_total,desconto,pct_desconto,forma_pagamento,parcelas) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (cod,usuario_id or None,vendedora_nome,cliente_id or None,cliente_nome,valor_total,desconto,pct_desconto,forma,parcelas))
        venda_id = cur.fetchone()['id']
        for item in itens:
            pid = item.get('produto_id')
            qtd = int(item.get('quantidade',1))
            vunit = float(item.get('valor_unitario',0))
            cur.execute("""INSERT INTO venda_itens (venda_id,produto_id,codigo_produto,modelo,
                descricao,tamanho,valor_unitario,quantidade,valor_total)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (venda_id,pid or None,item.get('codigo'),item.get('modelo'),
                 item.get('descricao'),item.get('tamanho'),vunit,qtd,vunit*qtd))
            if pid:
                cur.execute("UPDATE estoque SET quantidade=quantidade-%s,ultima_venda=CURRENT_DATE WHERE id=%s",(qtd,pid))
        if forma == 'crediario':
            entrada = parse_brl(request.form.get('entrada','0'))
            saldo = valor_total - entrada
            cur.execute("""INSERT INTO crediarios (venda_id,cliente_id,cliente_nome,valor_total,entrada,saldo_devedor)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (venda_id,cliente_id or None,cliente_nome,valor_total,entrada,saldo))
            cred_id = cur.fetchone()['id']
            for i,p in enumerate(json.loads(request.form.get('parcelas_datas','[]'))):
                cur.execute("INSERT INTO crediario_parcelas (crediario_id,numero_parcela,data_vencimento,valor) VALUES (%s,%s,%s,%s)",
                    (cred_id,i+1,p.get('data'),float(p.get('valor',0))))
        # Valor final = total - desconto (enviado já calculado pelo JS)
        valor_final_form = parse_brl(request.form.get('valor_final', '0'))
        valor_final = valor_final_form if valor_final_form > 0 else round(valor_total - desconto, 2)

        # Registrar no caixa conforme forma de pagamento
        formas_a_vista = ['pix','dinheiro','debito','credito_vista','credito_parcelado','link']
        if forma in formas_a_vista:
            # Entra tudo no caixa no dia
            cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,usuario_id,vendedora_nome)
                VALUES (%s,%s,'entrada',%s,%s,%s,%s)""",
                (f"Venda {cod} - {cliente_nome}", valor_final, forma, venda_id, usuario_id or None, vendedora_nome))
        elif forma == 'crediario':
            # Só registra a entrada paga (se houver) — com a forma de pagamento REAL da entrada
            if entrada > 0:
                entrada_forma = request.form.get('entrada_forma','dinheiro').strip() or 'dinheiro'
                if entrada_forma not in formas_a_vista: entrada_forma = 'dinheiro'
                cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,crediario_id,usuario_id,vendedora_nome)
                    VALUES (%s,%s,'entrada',%s,%s,%s,%s,%s)""",
                    (f"Entrada crediário - {cliente_nome} ({entrada_forma.replace('_',' ')})", entrada, entrada_forma, venda_id, cred_id, usuario_id or None, vendedora_nome))

        conn.commit(); flash('Venda registrada!','ok')
    except Exception as e:
        conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('vendas'))

@app.route('/vendas/<int:vid>')
@login_required
def ficha_venda(vid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM vendas WHERE id=%s",(vid,))
    row = cur.fetchone()
    if not row: flash('Venda nao encontrada.','erro'); return redirect(url_for('vendas'))
    venda = dict(row)
    cur.execute("SELECT * FROM venda_itens WHERE venda_id=%s",(vid,))
    itens = [dict(i) for i in cur.fetchall()]
    crediario = None
    if venda.get('forma_pagamento') == 'crediario':
        cur.execute("SELECT * FROM crediarios WHERE venda_id=%s",(vid,))
        c = cur.fetchone()
        if c:
            crediario = dict(c)
            cur.execute("SELECT * FROM crediario_parcelas WHERE crediario_id=%s ORDER BY numero_parcela",(crediario['id'],))
            crediario['parcelas'] = [dict(p) for p in cur.fetchall()]
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u) for u in cur.fetchall()]
    cur.close(); conn.close()
    ctx = get_ctx(); ctx.update(venda=venda, itens=itens, crediario=crediario, vendedoras=vendedoras)
    return render_template('ficha_venda.html', **ctx)

@app.route('/vendas/<int:vid>/excluir', methods=['POST'])
@login_required
def excluir_venda(vid):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.','erro')
        return redirect(url_for('ficha_venda', vid=vid))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM venda_itens WHERE venda_id=%s",(vid,))
        for item in cur.fetchall():
            if item['produto_id']:
                cur.execute("UPDATE estoque SET quantidade=quantidade+%s WHERE id=%s",(item['quantidade'],item['produto_id']))
        # Remover registros do caixa vinculados a esta venda
        cur.execute("DELETE FROM caixa WHERE venda_id=%s",(vid,))
        # Remover crediário vinculado (e suas parcelas)
        cur.execute("DELETE FROM crediarios WHERE venda_id=%s",(vid,))
        cur.execute("DELETE FROM vendas WHERE id=%s",(vid,))
        conn.commit(); flash('Venda excluída. Estoque e caixa restaurados.','ok')
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('vendas'))


@app.route('/vendas/<int:vid>/editar', methods=['GET','POST'])
@login_required
def editar_venda(vid):
    # Edição liberada para quem tem acesso à aba Vendas (vendedor só não pode excluir).
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        try:
            cliente_nome = request.form.get('cliente_nome','').strip()
            vendedora_nome = request.form.get('vendedora_nome','').strip()
            forma_pagamento = request.form.get('forma_pagamento','')
            parcelas = int(request.form.get('parcelas', 1) or 1)
            cur.execute("""UPDATE vendas SET cliente_nome=%s, vendedora_nome=%s,
                          forma_pagamento=%s, parcelas=%s WHERE id=%s""",
                       (cliente_nome, vendedora_nome, forma_pagamento, parcelas, vid))
            conn.commit()
            flash('Venda atualizada com sucesso!','ok')
            return redirect(url_for('ficha_venda', vid=vid))
        except Exception as e:
            conn.rollback(); flash(str(e),'erro')
        finally: cur.close(); conn.close()
        return redirect(url_for('ficha_venda', vid=vid))
    cur.execute("SELECT * FROM vendas WHERE id=%s",(vid,))
    row = cur.fetchone()
    if not row:
        flash('Venda não encontrada.','erro')
        return redirect(url_for('vendas'))
    venda = dict(row)
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u)['nome'] for u in cur.fetchall()]
    cur.close(); conn.close()
    ctx = get_ctx(); ctx.update(venda=venda, vendedoras=vendedoras)
    return render_template('editar_venda.html', **ctx)

@app.route('/vendas/ranking')
@login_required
def ranking_vendedoras():
    hoje = date.today()
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim = request.args.get('data_fim', hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = hoje.strftime('%Y-%m-%d')
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT vendedora_nome,COALESCE(SUM(valor_total),0) as total,
        COUNT(id) as num_vendas,COUNT(DISTINCT cliente_id) as clientes
        FROM vendas WHERE DATE(criado_em) BETWEEN %s AND %s
        GROUP BY vendedora_nome ORDER BY total DESC""",(data_inicio, data_fim))
    ranking = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'ranking':ranking})

@app.route('/vendas/buscar-ref')
@login_required
def buscar_ref():
    ref = request.args.get('ref','').strip().upper()
    busca = ref if ref.startswith('P') else f"P{ref}"
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id as produto_id,codigo,modelo,descricao,tamanho,valor_venda,quantidade FROM estoque WHERE codigo=%s AND ativo=TRUE AND quantidade>0",(busca,))
    item = cur.fetchone(); cur.close(); conn.close()
    if item: return jsonify({'ok':True,'item':dict(item)})
    return jsonify({'ok':False})

@app.route('/vendas/buscar-cliente')
@login_required
def buscar_cliente():
    q = request.args.get('q','').strip()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id,codigo,nome,crediario FROM clientes WHERE ativo=TRUE AND (LOWER(nome) LIKE %s OR codigo ILIKE %s) ORDER BY nome LIMIT 8",
        (f'%{q.lower()}%',f'%{q}%'))
    lista = [dict(c) for c in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'clientes':lista})

# ══════════════ CONDICIONAL / TRANSFERÊNCIA ══════════════
LOJA_TRANSFERENCIA = 'CD By Carol Duarte'

@app.route('/condicionais')
@login_required
def condicionais():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u) for u in cur.fetchall()]
    cur.execute("SELECT id,codigo,nome,crediario FROM clientes WHERE ativo=TRUE ORDER BY nome")
    clientes_lista = [dict(c) for c in cur.fetchall()]
    hoje = date.today()
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim    = request.args.get('data_fim',    hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = hoje.strftime('%Y-%m-%d')
    # Abertas no período (o filtro do topo conecta a tela toda)
    cur.execute("""SELECT c.*,
        COALESCE((SELECT SUM(quantidade) FROM condicional_itens WHERE condicional_id=c.id AND status='pendente'),0) as qtd_pecas
        FROM condicionais c WHERE c.status='aberta' AND DATE(c.criado_em) BETWEEN %s AND %s
        ORDER BY c.criado_em""", (data_inicio, data_fim))
    abertas = [dict(r) for r in cur.fetchall()]
    for c in abertas:
        c['dias'] = (hoje - c['criado_em'].date()).days
    # Histórico (filtrado pelo período)
    cur.execute("""SELECT c.*,
        COALESCE((SELECT SUM(quantidade) FROM condicional_itens WHERE condicional_id=c.id),0) as qtd_pecas
        FROM condicionais c WHERE c.status<>'aberta' AND DATE(c.criado_em) BETWEEN %s AND %s
        ORDER BY c.criado_em DESC""", (data_inicio, data_fim))
    historico = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)),0) as n FROM condicionais WHERE codigo ~ '^C[0-9]+$'")
    next_n = cur.fetchone()['n'] + 1
    cur.close(); conn.close()
    # ── KPIs / agregações ──
    total_aberto = round(sum(float(c['valor_total'] or 0) for c in abertas), 2)
    n_abertas = len(abertas)
    n_pecas = sum(int(c['qtd_pecas'] or 0) for c in abertas)
    cond_aberto  = round(sum(float(c['valor_total'] or 0) for c in abertas if c['tipo'] == 'condicional'), 2)
    transf_aberto = round(sum(float(c['valor_total'] or 0) for c in abertas if c['tipo'] == 'transferencia'), 2)
    n_cond  = sum(1 for c in abertas if c['tipo'] == 'condicional')
    n_transf = sum(1 for c in abertas if c['tipo'] == 'transferencia')
    # Aging — mais tempo em aberto
    aging = sorted(abertas, key=lambda c: c['dias'], reverse=True)[:8]
    # Maiores valores por cliente/destino
    por_cliente = {}
    for c in abertas:
        k = c['cliente_nome'] or '—'
        por_cliente[k] = por_cliente.get(k, 0.0) + float(c['valor_total'] or 0)
    maiores = sorted([{'nome': k, 'valor': round(v, 2)} for k, v in por_cliente.items()],
                     key=lambda x: x['valor'], reverse=True)[:8]
    ctx = get_ctx()
    ctx.update(vendedoras=vendedoras, clientes=clientes_lista, abertas=abertas, historico=historico,
               data_inicio=data_inicio, data_fim=data_fim, next_cod=f"C{next_n}",
               total_aberto=total_aberto, n_abertas=n_abertas, n_pecas=n_pecas,
               cond_aberto=cond_aberto, transf_aberto=transf_aberto, n_cond=n_cond, n_transf=n_transf,
               aging=aging, maiores=maiores, loja_transf=LOJA_TRANSFERENCIA)
    return render_template('condicionais.html', **ctx)

@app.route('/condicionais/nova', methods=['POST'])
@login_required
def nova_condicional():
    conn = get_db(); cur = conn.cursor()
    try:
        tipo = request.form.get('tipo', 'condicional').strip().lower()
        if tipo not in ('condicional', 'transferencia'): tipo = 'condicional'
        usuario_id = request.form.get('usuario_id')
        vendedora_nome = request.form.get('vendedora_nome', '').strip()
        if tipo == 'transferencia':
            cliente_id = None; cliente_nome = LOJA_TRANSFERENCIA
        else:
            cliente_id = request.form.get('cliente_id') or None
            cliente_nome = request.form.get('cliente_nome', '').strip()
        obs = request.form.get('observacao', '').strip() or None
        itens = json.loads(request.form.get('itens', '[]'))
        if not itens:
            raise Exception('Adicione pelo menos um item.')
        if tipo == 'condicional' and not cliente_nome:
            raise Exception('Informe o cliente da condicional.')
        cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)),0) as n FROM condicionais WHERE codigo ~ '^C[0-9]+$'")
        n = cur.fetchone()['n']; cod = f"C{n+1}"
        total = sum(float(i.get('valor_unitario', 0)) * int(i.get('quantidade', 1)) for i in itens)
        cur.execute("""INSERT INTO condicionais (codigo,tipo,cliente_id,cliente_nome,usuario_id,vendedora_nome,valor_total,observacao)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (cod, tipo, cliente_id, cliente_nome, usuario_id or None, vendedora_nome, total, obs))
        cid = cur.fetchone()['id']
        for it in itens:
            pid = it.get('produto_id'); qtd = int(it.get('quantidade', 1)); vu = float(it.get('valor_unitario', 0))
            if pid:
                cur.execute("SELECT quantidade FROM estoque WHERE id=%s", (pid,))
                row = cur.fetchone(); disp = int(row['quantidade']) if row else 0
                if qtd > disp:
                    raise Exception(f"Saldo insuficiente para {it.get('codigo')} (disponível: {disp}).")
                cur.execute("UPDATE estoque SET quantidade=quantidade-%s, reservado=COALESCE(reservado,0)+%s WHERE id=%s", (qtd, qtd, pid))
            cur.execute("""INSERT INTO condicional_itens (condicional_id,produto_id,codigo_produto,modelo,descricao,tamanho,valor_unitario,quantidade)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (cid, pid or None, it.get('codigo'), it.get('modelo'), it.get('descricao'), it.get('tamanho'), vu, qtd))
        rotulo = 'Transferência' if tipo == 'transferencia' else 'Condicional'
        conn.commit(); flash(f'{rotulo} {cod} registrada! Itens reservados no estoque.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('condicionais'))

@app.route('/condicionais/<int:cid>')
@login_required
def ficha_condicional(cid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM condicionais WHERE id=%s", (cid,))
    row = cur.fetchone()
    if not row:
        flash('Condicional não encontrada.', 'erro'); cur.close(); conn.close()
        return redirect(url_for('condicionais'))
    cond = dict(row)
    cur.execute("SELECT * FROM condicional_itens WHERE condicional_id=%s ORDER BY id", (cid,))
    itens = [dict(i) for i in cur.fetchall()]
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u) for u in cur.fetchall()]
    cliente_cred = False
    if cond.get('cliente_id'):
        cur.execute("SELECT crediario FROM clientes WHERE id=%s", (cond['cliente_id'],))
        cc = cur.fetchone(); cliente_cred = bool(cc and cc['crediario'])
    venda = None
    if cond.get('venda_id'):
        cur.execute("SELECT codigo FROM vendas WHERE id=%s", (cond['venda_id'],))
        vv = cur.fetchone(); venda = dict(vv) if vv else None
    cur.close(); conn.close()
    cond['dias'] = (date.today() - cond['criado_em'].date()).days
    ctx = get_ctx(); ctx.update(cond=cond, itens=itens, vendedoras=vendedoras,
                                cliente_cred=cliente_cred, venda=venda)
    return render_template('ficha_condicional.html', **ctx)

@app.route('/condicionais/<int:cid>/gerar-venda', methods=['POST'])
@login_required
def gerar_venda_condicional(cid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM condicionais WHERE id=%s", (cid,))
        cond = cur.fetchone()
        if not cond: raise Exception('Condicional não encontrada.')
        cond = dict(cond)
        if cond['status'] != 'aberta': raise Exception('Esta condicional já foi finalizada.')
        cur.execute("SELECT * FROM condicional_itens WHERE condicional_id=%s", (cid,))
        citens = [dict(i) for i in cur.fetchall()]
        usuario_id = request.form.get('usuario_id') or cond.get('usuario_id')
        vendedora_nome = request.form.get('vendedora_nome', '').strip() or cond.get('vendedora_nome')
        forma = request.form.get('forma_pagamento', '').strip()
        cliente_id = cond.get('cliente_id'); cliente_nome = cond.get('cliente_nome')
        # Quantas peças o cliente ficou (por item)
        kept_total = 0
        for it in citens:
            k = int(request.form.get(f'fica_{it["id"]}', 0) or 0)
            it['_kept'] = max(0, min(k, int(it['quantidade'])))
            kept_total += it['_kept']
        if kept_total == 0:
            raise Exception('Selecione ao menos uma peça que ficou com o cliente. Para devolver tudo, use "Devolver tudo".')
        if not forma:
            raise Exception('Selecione a forma de pagamento.')
        valor_total = round(sum(float(it['valor_unitario']) * it['_kept'] for it in citens if it['_kept'] > 0), 2)
        desconto = min(parse_brl(request.form.get('desconto_valor', '0')), valor_total)
        pct_desconto = min(100.0, max(0.0, parse_brl(request.form.get('pct_desconto', '0'))))
        valor_final = round(valor_total - desconto, 2)
        parcelas = int(request.form.get('parcelas', 1) or 1)
        cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)),0) as n FROM vendas WHERE codigo ~ '^V[0-9]+$'")
        vn = cur.fetchone()['n']; vcod = f"V{vn+1}"
        cur.execute("""INSERT INTO vendas (codigo,usuario_id,vendedora_nome,cliente_id,cliente_nome,valor_total,desconto,pct_desconto,forma_pagamento,parcelas)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (vcod, usuario_id or None, vendedora_nome, cliente_id or None, cliente_nome,
             valor_total, desconto, pct_desconto, forma, parcelas))
        venda_id = cur.fetchone()['id']
        for it in citens:
            k = it['_kept']; q = int(it['quantidade']); devolver = q - k; pid = it['produto_id']
            if k > 0:
                vu = float(it['valor_unitario'])
                cur.execute("""INSERT INTO venda_itens (venda_id,produto_id,codigo_produto,modelo,descricao,tamanho,valor_unitario,quantidade,valor_total)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (venda_id, pid or None, it['codigo_produto'], it['modelo'], it['descricao'], it['tamanho'], vu, k, vu * k))
                if pid:
                    cur.execute("UPDATE estoque SET reservado=GREATEST(0,COALESCE(reservado,0)-%s), ultima_venda=CURRENT_DATE WHERE id=%s", (k, pid))
            if devolver > 0 and pid:
                cur.execute("UPDATE estoque SET quantidade=quantidade+%s, reservado=GREATEST(0,COALESCE(reservado,0)-%s) WHERE id=%s", (devolver, devolver, pid))
            novo = 'vendido' if (k > 0 and devolver == 0) else ('parcial' if k > 0 else 'devolvido')
            cur.execute("UPDATE condicional_itens SET status=%s WHERE id=%s", (novo, it['id']))
        # Caixa / crediário
        formas_a_vista = ['pix', 'dinheiro', 'debito', 'credito_vista', 'credito_parcelado', 'link']
        if forma in formas_a_vista:
            cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,usuario_id,vendedora_nome)
                VALUES (%s,%s,'entrada',%s,%s,%s,%s)""",
                (f"Venda {vcod} - {cliente_nome} (condicional {cond['codigo']})", valor_final, forma, venda_id, usuario_id or None, vendedora_nome))
        elif forma == 'crediario':
            entrada = parse_brl(request.form.get('entrada', '0'))
            saldo = round(valor_final - entrada, 2)
            cur.execute("""INSERT INTO crediarios (venda_id,cliente_id,cliente_nome,valor_total,entrada,saldo_devedor)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (venda_id, cliente_id or None, cliente_nome, valor_final, entrada, saldo))
            cred_id = cur.fetchone()['id']
            for i, p in enumerate(json.loads(request.form.get('parcelas_datas', '[]'))):
                cur.execute("INSERT INTO crediario_parcelas (crediario_id,numero_parcela,data_vencimento,valor) VALUES (%s,%s,%s,%s)",
                    (cred_id, i + 1, p.get('data'), float(p.get('valor', 0))))
            if entrada > 0:
                entrada_forma = request.form.get('entrada_forma','dinheiro').strip() or 'dinheiro'
                if entrada_forma not in formas_a_vista: entrada_forma = 'dinheiro'
                cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,crediario_id,usuario_id,vendedora_nome)
                    VALUES (%s,%s,'entrada',%s,%s,%s,%s,%s)""",
                    (f"Entrada crediário - {cliente_nome} (condicional {cond['codigo']}, {entrada_forma.replace('_',' ')})", entrada, entrada_forma, venda_id, cred_id, usuario_id or None, vendedora_nome))
        cur.execute("UPDATE condicionais SET status='finalizada', venda_id=%s, finalizado_em=CURRENT_TIMESTAMP WHERE id=%s", (venda_id, cid))
        conn.commit(); flash(f'Venda {vcod} gerada da condicional {cond["codigo"]}! Peças não retiradas voltaram ao estoque.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
        cur.close(); conn.close()
        return redirect(url_for('ficha_condicional', cid=cid))
    cur.close(); conn.close()
    return redirect(url_for('ficha_venda', vid=venda_id))

@app.route('/condicionais/<int:cid>/devolver', methods=['POST'])
@login_required
def devolver_condicional(cid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM condicionais WHERE id=%s", (cid,))
        cond = cur.fetchone()
        if not cond: raise Exception('Condicional não encontrada.')
        cond = dict(cond)
        if cond['status'] != 'aberta': raise Exception('Esta condicional já foi finalizada.')
        cur.execute("SELECT * FROM condicional_itens WHERE condicional_id=%s AND status='pendente'", (cid,))
        for it in cur.fetchall():
            if it['produto_id']:
                cur.execute("UPDATE estoque SET quantidade=quantidade+%s, reservado=GREATEST(0,COALESCE(reservado,0)-%s) WHERE id=%s",
                    (it['quantidade'], it['quantidade'], it['produto_id']))
        cur.execute("UPDATE condicional_itens SET status='devolvido' WHERE condicional_id=%s", (cid,))
        cur.execute("UPDATE condicionais SET status='devolvida', finalizado_em=CURRENT_TIMESTAMP WHERE id=%s", (cid,))
        conn.commit(); flash(f'Condicional {cond["codigo"]} devolvida. Peças retornaram ao estoque.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('condicionais'))

@app.route('/condicionais/<int:cid>/confirmar-transferencia', methods=['POST'])
@login_required
def confirmar_transferencia(cid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM condicionais WHERE id=%s", (cid,))
        cond = cur.fetchone()
        if not cond: raise Exception('Registro não encontrado.')
        cond = dict(cond)
        if cond['status'] != 'aberta': raise Exception('Já finalizada.')
        cur.execute("SELECT * FROM condicional_itens WHERE condicional_id=%s AND status='pendente'", (cid,))
        for it in cur.fetchall():
            if it['produto_id']:
                cur.execute("UPDATE estoque SET reservado=GREATEST(0,COALESCE(reservado,0)-%s) WHERE id=%s", (it['quantidade'], it['produto_id']))
        cur.execute("UPDATE condicional_itens SET status='transferido' WHERE condicional_id=%s", (cid,))
        cur.execute("UPDATE condicionais SET status='finalizada', finalizado_em=CURRENT_TIMESTAMP WHERE id=%s", (cid,))
        conn.commit(); flash(f'Transferência {cond["codigo"]} confirmada. Peças baixadas (enviadas à {LOJA_TRANSFERENCIA}).', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('condicionais'))

@app.route('/condicionais/<int:cid>/excluir', methods=['POST'])
@login_required
def excluir_condicional(cid):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.','erro'); return redirect(url_for('condicionais'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT status FROM condicionais WHERE id=%s", (cid,))
        r = cur.fetchone()
        if r and r['status'] == 'aberta':
            cur.execute("SELECT * FROM condicional_itens WHERE condicional_id=%s AND status='pendente'", (cid,))
            for it in cur.fetchall():
                if it['produto_id']:
                    cur.execute("UPDATE estoque SET quantidade=quantidade+%s, reservado=GREATEST(0,COALESCE(reservado,0)-%s) WHERE id=%s",
                        (it['quantidade'], it['quantidade'], it['produto_id']))
        cur.execute("DELETE FROM condicionais WHERE id=%s", (cid,))
        conn.commit(); flash('Condicional excluída.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('condicionais'))

@app.route('/crediarios')
@login_required
def crediarios():
    data_inicio = request.args.get('data_inicio','')
    data_fim = request.args.get('data_fim','')
    conn = get_db(); cur = conn.cursor()
    if data_inicio and data_fim:
        cur.execute("""SELECT c.*,v.codigo as codigo_venda,v.criado_em as data_venda
            FROM crediarios c JOIN vendas v ON v.id=c.venda_id
            WHERE DATE(v.criado_em) BETWEEN %s AND %s
            ORDER BY c.status,c.criado_em DESC""",(data_inicio,data_fim))
    else:
        cur.execute("""SELECT c.*,v.codigo as codigo_venda,v.criado_em as data_venda
            FROM crediarios c JOIN vendas v ON v.id=c.venda_id ORDER BY c.status,c.criado_em DESC""")
    raw = [dict(c) for c in cur.fetchall()]
    for c in raw:
        cur.execute("SELECT * FROM crediario_parcelas WHERE crediario_id=%s ORDER BY numero_parcela",(c['id'],))
        c['parcelas'] = [dict(p) for p in cur.fetchall()]
    # Agrupar por cliente
    from collections import OrderedDict
    agrupado = OrderedDict()
    for c in raw:
        nome = c['cliente_nome']
        if nome not in agrupado:
            agrupado[nome] = {'cliente_nome':nome,'vendas':[],'total':0,'pago':0,'saldo':0}
        agrupado[nome]['vendas'].append(c)
        agrupado[nome]['total'] += float(c['valor_total'])
        agrupado[nome]['pago']  += float(c['valor_total']) - float(c['saldo_devedor'])
        agrupado[nome]['saldo'] += float(c['saldo_devedor'])
    clientes = list(agrupado.values())
    # ── Análise de atraso e distribuição por cliente (para os gráficos) ──
    hoje = date.today()
    for cli in clientes:
        atraso_val = 0.0; atraso_qtd = 0; dias_max = 0; prox_venc = None
        for c in cli['vendas']:
            for p in c['parcelas']:
                if not p.get('pago'):
                    venc = p.get('data_vencimento')
                    if venc and venc < hoje:
                        atraso_val += float(p['valor'] or 0); atraso_qtd += 1
                        dias_max = max(dias_max, (hoje - venc).days)
                    elif venc and (prox_venc is None or venc < prox_venc):
                        prox_venc = venc
        cli['atraso_valor'] = round(atraso_val, 2)
        cli['atraso_qtd'] = atraso_qtd
        cli['dias_atraso'] = dias_max
        cli['em_atraso'] = atraso_val > 0
        cli['prox_venc'] = prox_venc
    clientes_abertos = [c for c in clientes if c['saldo'] > 0.01]
    clientes_atraso = sorted([c for c in clientes_abertos if c['em_atraso']],
                             key=lambda c: c['atraso_valor'], reverse=True)
    top_devedores = sorted(clientes_abertos, key=lambda c: c['saldo'], reverse=True)[:8]
    valor_atraso = round(sum(c['atraso_valor'] for c in clientes_atraso), 2)
    valor_em_dia = round(sum(c['saldo'] for c in clientes_abertos) - valor_atraso, 2)
    # Faixas de valor em aberto (distribuição de clientes)
    faixas = [('Até R$ 200', 0, 200), ('R$ 200–500', 200, 500),
              ('R$ 500–1.000', 500, 1000), ('Acima de R$ 1.000', 1000, float('inf'))]
    faixas_dist = []
    for lbl, lo, hi in faixas:
        grp = [c for c in clientes_abertos if lo < c['saldo'] <= hi]
        faixas_dist.append({'label': lbl, 'qtd': len(grp),
                            'valor': round(sum(c['saldo'] for c in grp), 2)})
    cur.execute("SELECT COALESCE(SUM(saldo_devedor),0) as t FROM crediarios WHERE status='aberto'")
    total_aberto = float(cur.fetchone()['t'])
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u) for u in cur.fetchall()]
    cur.close(); conn.close()
    taxa_vigente = get_taxa_vigente()
    ctx = get_ctx(); ctx.update(clientes=clientes, total_aberto=total_aberto, vendedoras=vendedoras,
        taxa_vigente=taxa_vigente, data_inicio=data_inicio, data_fim=data_fim,
        n_abertos=len(clientes_abertos), n_atraso=len(clientes_atraso),
        valor_atraso=valor_atraso, valor_em_dia=valor_em_dia,
        clientes_atraso=clientes_atraso, top_devedores=top_devedores, faixas_dist=faixas_dist)
    return render_template('crediarios.html', **ctx)

@app.route('/crediarios/<int:cid>/parcela/<int:pid>/pagar', methods=['POST'])
@login_required
def pagar_parcela(cid, pid):
    vendedora_nome = request.form.get('vendedora_nome','').strip()
    valor_pago = float(request.form.get('valor_pago',0) or 0)
    forma_pg = request.form.get('forma_pagamento','dinheiro').strip()
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM crediarios WHERE id=%s",(cid,))
        cred = dict(cur.fetchone())
        cur.execute("UPDATE crediario_parcelas SET pago=TRUE,valor=%s,data_pagamento=CURRENT_DATE WHERE id=%s",(valor_pago,pid))
        novo_saldo = round(float(cred['saldo_devedor']) - valor_pago, 2)
        if novo_saldo <= 0.01:
            cur.execute("DELETE FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE",(cid,))
            cur.execute("UPDATE crediarios SET saldo_devedor=0,status='quitado' WHERE id=%s",(cid,))
        else:
            cur.execute("SELECT id FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE ORDER BY numero_parcela",(cid,))
            rest = cur.fetchall()
            if rest:
                vp = math.ceil((novo_saldo/len(rest))*100)/100
                for i,p in enumerate(rest):
                    v = round(novo_saldo-vp*(len(rest)-1),2) if i==len(rest)-1 else vp
                    cur.execute("UPDATE crediario_parcelas SET valor=%s WHERE id=%s",(v,p['id']))
            cur.execute("UPDATE crediarios SET saldo_devedor=%s WHERE id=%s",(novo_saldo,cid))
        # Gravar no caixa com a forma de pagamento real (para taxas serem aplicadas corretamente)
        descr = f"Crediário - {cred['cliente_nome']} ({forma_pg.replace('_',' ')})"
        cur.execute("INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,crediario_id,vendedora_nome) VALUES (%s,%s,'entrada',%s,%s,%s)",
            (descr,valor_pago,forma_pg,cid,vendedora_nome))
        conn.commit(); flash('Pagamento registrado!','ok')
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('crediarios'))

@app.route('/taxas', methods=['GET','POST'])
@login_required
def taxas():
    if not is_admin():
        flash('Apenas administradores podem gerenciar taxas.','erro')
        return redirect(url_for('caixa'))
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        try:
            cv  = parse_brl(request.form.get('credito_vista','0'))
            cp  = parse_brl(request.form.get('credito_parcelado','0'))
            deb = parse_brl(request.form.get('debito','0'))
            lnk = parse_brl(request.form.get('link','0'))
            ant = parse_brl(request.form.get('antecipacao','0'))
            vig = request.form.get('vigencia_em', str(date.today()))
            cur.execute("""INSERT INTO taxas_pagamento
                (vigencia_em,credito_vista,credito_parcelado,debito,link,antecipacao,usuario_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (vig, cv, cp, deb, lnk, ant, session.get('uid')))
            conn.commit()
            flash('Taxas atualizadas com sucesso!','ok')
        except Exception as e:
            conn.rollback(); flash(str(e),'erro')
        finally: cur.close(); conn.close()
        return redirect(url_for('taxas'))
    # GET
    taxa_atual = get_taxa_vigente()
    cur.execute("""SELECT t.*,u.nome as usuario_nome FROM taxas_pagamento t
                   LEFT JOIN usuarios u ON t.usuario_id=u.id
                   ORDER BY t.vigencia_em DESC LIMIT 20""")
    historico = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    ctx = get_ctx()
    ctx.update(taxa_atual=taxa_atual, historico=historico, today=str(date.today()))
    return render_template('taxas.html', **ctx)

@app.route('/caixa')
@login_required
def caixa():
    conn = get_db(); cur = conn.cursor()
    hoje = date.today()
    # Suporte a filtro por data_inicio e data_fim
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim    = request.args.get('data_fim',    hoje.strftime('%Y-%m-%d'))
    # Garantir formato correto
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = hoje.strftime('%Y-%m-%d')
    cur.execute("SELECT * FROM caixa WHERE DATE(criado_em) BETWEEN %s AND %s ORDER BY criado_em DESC",(data_inicio, data_fim))
    movs = [dict(m) for m in cur.fetchall()]
    # Categorias de entrada:
    #   • Venda à vista:  venda_id NÃO nulo, crediario_id nulo, forma <> 'crediario'
    #   • Crediário entrada: venda_id NÃO nulo E (crediario_id NÃO nulo OU forma='crediario' [legado])
    #   • Crediário parcela: crediario_id NÃO nulo E venda_id nulo
    cur.execute("""SELECT
        COALESCE(SUM(CASE WHEN tipo='entrada' THEN valor ELSE 0 END),0) as entradas,
        COALESCE(SUM(CASE WHEN tipo='saida' THEN valor ELSE 0 END),0) as saidas,
        COALESCE(SUM(CASE WHEN tipo='entrada' AND venda_id IS NOT NULL AND crediario_id IS NULL AND COALESCE(forma_pagamento,'')<>'crediario' THEN valor ELSE 0 END),0) as entradas_vendas,
        COALESCE(SUM(CASE WHEN tipo='entrada' AND venda_id IS NOT NULL AND (crediario_id IS NOT NULL OR forma_pagamento='crediario') THEN valor ELSE 0 END),0) as entradas_cred_entrada,
        COALESCE(SUM(CASE WHEN tipo='entrada' AND crediario_id IS NOT NULL AND venda_id IS NULL THEN valor ELSE 0 END),0) as entradas_cred_parcelas
        FROM caixa WHERE DATE(criado_em) BETWEEN %s AND %s""",(data_inicio, data_fim))
    tots = cur.fetchone()
    entradas = float(tots['entradas']); saidas = float(tots['saidas'])
    entradas_vendas        = float(tots['entradas_vendas'])
    entradas_cred_entrada  = float(tots['entradas_cred_entrada'])
    entradas_cred_parcelas = float(tots['entradas_cred_parcelas'])
    entradas_crediarios    = round(entradas_cred_entrada + entradas_cred_parcelas, 2)
    cur.close(); conn.close()
    taxa_vigente_hoje = get_taxa_vigente()
    ctx = get_ctx()
    # Calcular líquido por movimento + desconto por forma E por categoria de crediário
    total_desconto = 0
    desconto_formas = {'credito_vista':0.0,'credito_parcelado':0.0,'debito':0.0,'link':0.0}
    desconto_vendas = 0.0; desconto_cred_entrada = 0.0; desconto_cred_parcela = 0.0
    for m in movs:
        if m['tipo'] == 'entrada' and m.get('forma_pagamento') in ['credito_vista','credito_parcelado','debito','link']:
            taxa_data = get_taxa_vigente(m['criado_em'].date() if hasattr(m.get('criado_em',''), 'date') else date.today())
            liq, desc, ptc = calcular_liquido(float(m['valor']), m['forma_pagamento'], taxa_data)
            m['valor_liquido'] = liq
            m['desconto_taxa'] = desc
            m['taxa_total_pct'] = ptc
            total_desconto += desc
            desconto_formas[m['forma_pagamento']] += desc
            vid = m.get('venda_id'); crid = m.get('crediario_id')
            if crid and not vid:
                desconto_cred_parcela += desc
            elif crid and vid:
                desconto_cred_entrada += desc
            else:
                desconto_vendas += desc
        else:
            m['valor_liquido'] = float(m['valor'])
            m['desconto_taxa'] = 0
            m['taxa_total_pct'] = 0
    saldo_bruto   = round(entradas - total_desconto, 2)
    saldo_liquido = round(saldo_bruto - saidas, 2)
    ctx.update(movs=movs, entradas=entradas, saidas=saidas,
               entradas_vendas=entradas_vendas, entradas_crediarios=entradas_crediarios,
               entradas_cred_entrada=entradas_cred_entrada,
               entradas_cred_parcelas=entradas_cred_parcelas,
               saldo=round(entradas-saidas,2),
               saldo_bruto=saldo_bruto,
               total_desconto=round(total_desconto,2), saldo_liquido=saldo_liquido,
               desconto_formas={k: round(v,2) for k,v in desconto_formas.items()},
               desconto_vendas=round(desconto_vendas,2),
               desconto_cred_entrada=round(desconto_cred_entrada,2),
               desconto_cred_parcela=round(desconto_cred_parcela,2),
               taxa_vigente=taxa_vigente_hoje,
               data_inicio=data_inicio, data_fim=data_fim)
    return render_template('caixa.html', **ctx)

@app.route('/despesas')
@login_required
def despesas():
    conn = get_db(); cur = conn.cursor()
    hoje = date.today()
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim    = request.args.get('data_fim',    hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = hoje.strftime('%Y-%m-%d')
    cur.execute("SELECT * FROM despesas WHERE DATE(COALESCE(data_despesa,criado_em)) BETWEEN %s AND %s ORDER BY criado_em DESC",(data_inicio,data_fim))
    lista = [dict(d) for d in cur.fetchall()]
    # Carregar parcelas de cada despesa parcelada
    for d in lista:
        if d.get('parcelado'):
            cur.execute("SELECT * FROM despesa_parcelas WHERE despesa_id=%s ORDER BY numero",(d['id'],))
            d['parcelas'] = [dict(p) for p in cur.fetchall()]
            d['parc_pagas'] = sum(1 for p in d['parcelas'] if p['pago'])
        else:
            d['parcelas'] = []
            d['parc_pagas'] = 0
    cur.execute("SELECT COALESCE(SUM(valor),0) as t FROM despesas WHERE DATE(COALESCE(data_despesa,criado_em)) BETWEEN %s AND %s",(data_inicio,data_fim))
    total = float(cur.fetchone()['t'])
    cur.execute("SELECT COUNT(*) as t FROM despesas"); n = cur.fetchone()['t']
    # Categorias para o cadastro (ordenadas)
    cur.execute("SELECT nome FROM despesa_categorias WHERE ativo=TRUE ORDER BY nome")
    categorias = [r['nome'] for r in cur.fetchall()]
    # Contas a pagar (parcelas pendentes — independe do filtro de data)
    cur.execute("""SELECT p.id as parcela_id, p.numero, p.valor, p.data_vencimento,
                          d.id as despesa_id, d.codigo, d.descricao, d.categoria,
                          d.forma_pagamento, d.local_retirada, d.num_parcelas
                   FROM despesa_parcelas p JOIN despesas d ON d.id=p.despesa_id
                   WHERE p.pago=FALSE ORDER BY p.data_vencimento""")
    a_pagar = [dict(r) for r in cur.fetchall()]
    for p in a_pagar:
        p['atrasada'] = bool(p['data_vencimento'] and p['data_vencimento'] < hoje)
    total_a_pagar = round(sum(float(p['valor'] or 0) for p in a_pagar), 2)
    n_atrasadas = sum(1 for p in a_pagar if p['atrasada'])
    cur.close(); conn.close()
    # ── Agregações para gráficos (fixa vs avulsa + descrições + categorias) ──
    def _norm_tipo(t):
        return 'fixa' if (t or '').strip().lower() in ('fixa', 'fixo') else 'avulsa'
    total_fixa = total_avulsa = 0.0
    qtd_fixa = qtd_avulsa = 0
    cat_fixa, cat_avulsa = {}, {}
    forma_dist = {}
    for d in lista:
        v = float(d['valor'] or 0)
        tp = _norm_tipo(d.get('tipo'))
        d['tipo'] = tp  # normaliza para o template
        chave = (d.get('categoria') or d.get('descricao') or '—').strip() or '—'
        fp = (d.get('forma_pagamento') or 'Não informado').strip() or 'Não informado'
        forma_dist[fp] = forma_dist.get(fp, 0.0) + v
        if tp == 'fixa':
            total_fixa += v; qtd_fixa += 1
            cat_fixa[chave] = cat_fixa.get(chave, 0.0) + v
        else:
            total_avulsa += v; qtd_avulsa += 1
            cat_avulsa[chave] = cat_avulsa.get(chave, 0.0) + v
    def _ranked(dic):
        itens = sorted(dic.items(), key=lambda kv: kv[1], reverse=True)
        return [{'descricao': k, 'valor': round(v, 2)} for k, v in itens]
    desc_fixa_list = _ranked(cat_fixa)
    desc_avulsa_list = _ranked(cat_avulsa)
    forma_list = sorted(
        [{'forma': k, 'valor': round(v, 2)} for k, v in forma_dist.items()],
        key=lambda x: x['valor'], reverse=True)
    ctx = get_ctx()
    ctx.update(lista=lista, total=total, data_inicio=data_inicio, data_fim=data_fim, next_cod=f"D{n+1}",
               total_fixa=round(total_fixa, 2), total_avulsa=round(total_avulsa, 2),
               qtd_fixa=qtd_fixa, qtd_avulsa=qtd_avulsa,
               desc_fixa=desc_fixa_list, desc_avulsa=desc_avulsa_list, forma_list=forma_list,
               categorias=categorias, a_pagar=a_pagar, total_a_pagar=total_a_pagar,
               n_a_pagar=len(a_pagar), n_atrasadas=n_atrasadas)
    return render_template('despesas.html', **ctx)

@app.route('/despesas/nova', methods=['POST'])
@login_required
def nova_despesa():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as t FROM despesas"); n = cur.fetchone()['t']
    valor = parse_brl(request.form.get('valor','0'))
    descricao = request.form.get('descricao','').strip()
    categoria = request.form.get('categoria','').strip()
    forma = request.form.get('forma_pagamento','').strip()
    tipo = request.form.get('tipo','avulsa').strip().lower()
    if tipo not in ('fixa','avulsa'): tipo = 'avulsa'
    local_ret = request.form.get('local_retirada','').strip().lower()
    if local_ret not in ('caixa','pix'): local_ret = None
    obs_ret = request.form.get('obs_retirada','').strip() or None
    parcelado = request.form.get('parcelado','nao').strip().lower() == 'sim'
    try:
        num_parc = int(request.form.get('num_parcelas','1') or 1)
    except ValueError:
        num_parc = 1
    if not parcelado or num_parc < 2:
        parcelado = False; num_parc = 1
    num_parc = min(max(num_parc, 1), 24)
    # Vencimento (despesa sem parcelamento = 1 conta a pagar)
    venc_unico = request.form.get('data_vencimento_unica') or date.today().isoformat()
    # Rótulo da despesa para histórico (categoria + descrição livre)
    rotulo = categoria or descricao or 'Despesa'
    if categoria and descricao:
        rotulo = f"{categoria} — {descricao}"
    try:
        # Persistir categoria nova, se digitada
        if categoria:
            cur.execute("INSERT INTO despesa_categorias (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING",(categoria,))
        # Tanto parcelada quanto não-parcelada entram como conta(s) a pagar (pendente)
        status = 'pendente'
        data_venc_desp = None if parcelado else venc_unico
        cur.execute("""INSERT INTO despesas
            (codigo,descricao,categoria,valor,data_despesa,forma_pagamento,tipo,
             parcelado,num_parcelas,local_retirada,obs_retirada,status,data_vencimento,usuario_id,usuario_nome)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (f"D{n+1}",descricao or None,categoria or None,valor,
             request.form.get('data_despesa') or date.today().isoformat(),
             forma or None,tipo,parcelado,num_parc,local_ret,obs_ret,status,data_venc_desp,
             session['uid'],session['nome']))
        desp_id = cur.fetchone()['id']
        if parcelado:
            # Gera as parcelas; só viram saída no Caixa quando pagas
            soma = 0.0
            for i in range(1, num_parc+1):
                pv = request.form.get(f'parcela_valor_{i}')
                pd = request.form.get(f'parcela_data_{i}')
                pvf = parse_brl(pv) if pv else round(valor/num_parc, 2)
                if not pd:
                    pd = (date.today() + timedelta(days=30*i)).isoformat()
                soma += pvf
                cur.execute("""INSERT INTO despesa_parcelas (despesa_id,numero,valor,data_vencimento)
                    VALUES (%s,%s,%s,%s)""",(desp_id,i,pvf,pd))
            flash(f'Despesa parcelada em {num_parc}x registrada! As parcelas entram no caixa conforme você as paga.','ok')
        else:
            # Sem parcelamento = 1 conta a pagar com vencimento (só entra no caixa quando paga)
            cur.execute("""INSERT INTO despesa_parcelas (despesa_id,numero,valor,data_vencimento)
                VALUES (%s,1,%s,%s)""",(desp_id,valor,venc_unico))
            try: venc_fmt = datetime.fromisoformat(venc_unico).strftime('%d/%m/%Y')
            except Exception: venc_fmt = venc_unico
            flash(f'Despesa registrada como conta a pagar (vence em {venc_fmt}). Marque como paga quando quitar.','ok')
        conn.commit()
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('despesas'))

@app.route('/despesas/<int:did>/parcela/<int:pid>/pagar', methods=['POST'])
@login_required
def pagar_parcela_despesa(did, pid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM despesas WHERE id=%s",(did,))
        d = cur.fetchone()
        if not d:
            flash('Despesa não encontrada.','erro'); return redirect(url_for('despesas'))
        d = dict(d)
        cur.execute("SELECT * FROM despesa_parcelas WHERE id=%s",(pid,))
        p = cur.fetchone()
        if not p:
            flash('Parcela não encontrada.','erro'); return redirect(url_for('despesas'))
        p = dict(p)
        if p['pago']:
            flash('Esta parcela já está paga.','erro'); return redirect(url_for('despesas'))
        cur.execute("UPDATE despesa_parcelas SET pago=TRUE,data_pagamento=CURRENT_DATE WHERE id=%s",(pid,))
        rotulo = d.get('categoria') or d.get('descricao') or 'Despesa'
        loc = d.get('local_retirada')
        descr_caixa = f"Despesa: {rotulo} (parc. {p['numero']}/{d.get('num_parcelas')})" + (f" [{loc}]" if loc else "")
        cur.execute("INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,despesa_id,usuario_id,vendedora_nome) VALUES (%s,%s,'saida',%s,%s,%s,%s)",
            (descr_caixa,float(p['valor']),d.get('forma_pagamento'),did,session['uid'],session['nome']))
        # Se todas pagas, fecha a despesa
        cur.execute("SELECT COUNT(*) as t FROM despesa_parcelas WHERE despesa_id=%s AND pago=FALSE",(did,))
        if cur.fetchone()['t'] == 0:
            cur.execute("UPDATE despesas SET status='pago' WHERE id=%s",(did,))
        conn.commit(); flash(f"Parcela {p['numero']} paga e lançada no caixa!",'ok')
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('despesas'))

@app.route('/despesas/<int:did>/excluir', methods=['POST'])
@login_required
def excluir_despesa(did):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.','erro'); return redirect(url_for('despesas'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM caixa WHERE despesa_id=%s",(did,))
        cur.execute("DELETE FROM despesa_parcelas WHERE despesa_id=%s",(did,))
        cur.execute("DELETE FROM despesas WHERE id=%s",(did,))
        conn.commit(); flash('Despesa excluida.','ok')
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('despesas'))

@app.route('/dashboard')
@login_required
def dashboard_view():
    conn = get_db(); cur = conn.cursor()
    hoje = datetime.now()
    mes_ini = hoje.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    try:
        cur.execute("SELECT DATE(criado_em) as dia,COUNT(*) as qtd,COALESCE(SUM(valor_total),0) as total FROM vendas WHERE criado_em>=%s GROUP BY DATE(criado_em) ORDER BY dia",(mes_ini,))
        vendas_dia = [dict(r) for r in cur.fetchall()]
    except: vendas_dia = []
    try:
        cur.execute("""SELECT vi.codigo_produto,vi.modelo,SUM(vi.quantidade) as qtd_vendida,SUM(vi.valor_total) as receita
            FROM venda_itens vi JOIN vendas v ON v.id=vi.venda_id WHERE v.criado_em>=%s
            GROUP BY vi.codigo_produto,vi.modelo ORDER BY qtd_vendida DESC LIMIT 10""",(mes_ini,))
        top_produtos = [dict(r) for r in cur.fetchall()]
    except: top_produtos = []
    try:
        cur.execute("SELECT forma_pagamento,COUNT(*) as qtd,COALESCE(SUM(valor_total),0) as total FROM vendas WHERE criado_em>=%s GROUP BY forma_pagamento ORDER BY total DESC",(mes_ini,))
        formas_pag = [dict(r) for r in cur.fetchall()]
    except: formas_pag = []
    try:
        cur.execute("SELECT vendedora_nome,COUNT(*) as qtd_vendas,COALESCE(SUM(valor_total),0) as total,COUNT(DISTINCT cliente_id) as clientes FROM vendas WHERE criado_em>=%s GROUP BY vendedora_nome ORDER BY total DESC",(mes_ini,))
        vendedoras_rank = [dict(r) for r in cur.fetchall()]
    except: vendedoras_rank = []
    try:
        cur.execute("SELECT COALESCE(SUM(CASE WHEN tipo='entrada' THEN valor ELSE 0 END),0) as ent,COALESCE(SUM(CASE WHEN tipo='saida' THEN valor ELSE 0 END),0) as sai FROM caixa WHERE criado_em>=%s",(mes_ini,))
        fluxo = dict(cur.fetchone())
    except: fluxo = {'ent':0,'sai':0}
    try:
        cur.execute("SELECT COUNT(*) as t FROM clientes WHERE criado_em>=%s",(mes_ini,))
        clientes_novos = cur.fetchone()['t']
    except: clientes_novos = 0
    try:
        cur.execute("SELECT COALESCE(AVG(valor_total),0) as t FROM vendas WHERE criado_em>=%s",(mes_ini,))
        ticket_medio = float(cur.fetchone()['t'])
    except: ticket_medio = 0.0
    cur.close(); conn.close()
    ctx = get_ctx()
    ctx.update(vendas_dia=vendas_dia, top_produtos=top_produtos, formas_pag=formas_pag,
               vendedoras_rank=vendedoras_rank, fluxo=fluxo,
               clientes_novos=clientes_novos, ticket_medio=ticket_medio,
               mes_atual=hoje.strftime('%B / %Y').capitalize())
    return render_template('dashboard.html', **ctx)

with app.app_context():
    try: init_db()
    except Exception as e: print(f"init_db: {e}")

@app.route('/admin/limpar-caixa-orfaos')
@login_required
def limpar_caixa_orfaos():
    if not pode_excluir():
        return 'Acesso negado', 403
    conn = get_db(); cur = conn.cursor()
    try:
        # Remover registros do caixa cujas vendas não existem mais
        cur.execute("""DELETE FROM caixa
                       WHERE venda_id IS NOT NULL
                       AND venda_id NOT IN (SELECT id FROM vendas)""")
        removidos = cur.rowcount
        # Remover crediários órfãos
        cur.execute("""DELETE FROM crediarios
                       WHERE venda_id IS NOT NULL
                       AND venda_id NOT IN (SELECT id FROM vendas)""")
        cred_removidos = cur.rowcount
        conn.commit()
        return f"""<div style='font-family:monospace;padding:40px'>
        <b>✅ Limpeza concluída!</b><br><br>
        Registros de caixa removidos: <b>{removidos}</b><br>
        Crediários órfãos removidos: <b>{cred_removidos}</b><br><br>
        <a href='/caixa'>← Voltar ao Caixa</a>
        </div>"""
    except Exception as e:
        conn.rollback()
        return f'Erro: {e}', 500
    finally:
        cur.close(); conn.close()

@app.route('/versao')
def versao():
    return """<div style='font-family:monospace;padding:40px;font-size:18px'>
    <b>CD Gestão</b><br>
    Versão: <b style='color:green'>v89 — 2026-06-08</b><br>
    Despesas: corrigido erro ao salvar sem descrição (campo agora opcional) ✅<br>
    Despesas: sem parcelamento agora pede data de vencimento e vira conta a pagar ✅<br>
    Condicional: transferência também aceita crediário como forma de pagamento ✅<br>
    Responsivo: ERP adaptado para celular e tablet (menu vira barra superior rolável) ✅<br>
    Caixa: quadrantes de totais mais compactos na altura ✅<br>
    Menu: botão "Sair" movido para o final do menu lateral (abaixo de Usuários); removido "Minha senha" do topo ✅<br>
    Avatar: clique para carregar/tirar foto de perfil (ou iniciais do nome); foto também no cadastro de novo usuário ✅<br>
    Acesso negado: removida a opção de trocar senha da caixa de aviso ✅<br>
    Usuários (N1): botões de ação padronizados (tamanho uniforme) ✅<br>
    Ortografia: "vendedora" → "Vendedor (a)" em todo o ERP ✅<br>
    Condicional: ao finalizar uma transferência também há forma de pagamento (igual condicional) ✅<br>
    Despesas: máscara do valor corrigida (caixa registradora), sem erro ao digitar ✅<br>
    Correção: perfil legado "admin" agora é reconhecido como Administrador N1 (acesso total + gestão de usuários) ✅<br>
    Estoque: "Cadastrar produto" e "Imprimir etiquetas" viraram botões dentro da tela (com voltar) ✅<br>
    Etiquetas: busca por código do produto + quantidade de etiquetas, montando uma fila ✅<br>
    Etiquetas: folha A4 retrato configurada — 7 col × 18 lin = 126 (2,5 × 1,5 cm); escolha em qual posição começar para aproveitar 100% de meia folha ✅<br>
    Usuários: 3 perfis — Administrador N1 (acesso total + exclusão + gestão de usuários), N2 (tudo, edita, mas não exclui/nem gerencia usuários) e Vendedor (abas que o N1 liberar, sem exclusão) ✅<br>
    Acesso: menu sempre visível; clicar em aba sem permissão mostra aviso de acesso restrito ✅<br>
    Usuários: vendedor/N2 só trocam a própria senha na aba; só o N1 cadastra/edita perfis e libera abas ✅<br>
    Exclusão de dados (vendas, despesas, clientes, estoque, condicional...): apenas Administrador N1 ✅<br>
    Visão Geral: faturamento por forma vem do caixa (crediário já distribuído na forma real recebida) — sem linha de crediário ✅<br>
    Visão Geral: card Condicional trocou de posição com Crediários ✅<br>
    Vendas: entrada do crediário pede a forma de pagamento (aplica taxa no caixa, se cartão) ✅<br>
    Estoque: foto do produto no cadastro (câmera no celular ou arquivo) exibida na ficha ✅<br>
    Caixa: quadrante de taxas detalha desconto por Vendas / Crediário entrada / Crediário parcelas ✅<br>
    Condicional: filtro de período no topo, conectado a KPIs, gráficos, abertas e histórico ✅<br>
    Condicional: nova aba (condicional p/ cliente e transferência p/ CD By Carol Duarte) com reserva de estoque ✅<br>
    Condicional: gerar venda selecionando o que o cliente ficou (peças não retiradas voltam ao estoque); devolução total; baixa de transferência ✅<br>
    Condicional: integração total — estoque (reserva), vendas, caixa e crediário (ao gerar venda) e Visão Geral (valor em aberto) ✅<br>
    Condicional: dashboard com KPIs, donut condicional×transferência, aging (mais tempo) e maiores valores ✅<br>
    Crediários: dashboard moderno — donut em dia × atraso, distribuição por faixa, top devedores, lista de clientes em atraso ✅<br>
    Despesas: gráficos (donut fixa/avulsa, % por categoria em cada tipo, por forma de pagamento) ✅<br>
    Despesas: novo lançamento passo a passo (tipo → categoria com lista/busca/cadastro → descrição → valor → parcelamento até 24x com vencimentos 30/60/90 editáveis → meio de pagamento → origem Caixa/PIX) ✅<br>
    Despesas: parcelas viram contas a pagar e só entram no caixa quando pagas (Visão Geral conta saída real) ✅<br>
    Despesas: filtro De/Até + atalhos (Hoje/7dias/Mês) + busca rápida ✅<br>
    Crediários: busca + filtro De/Até + accordion duplo (cliente→vendas→parcelas) ✅<br>
    Scroll fixo: Crediários, Caixa, Estoque, Clientes, Despesas (tabela não cresce) ✅<br>
    Sticky headers: Caixa, Estoque, Clientes, Despesas ✅<br>
    Crediários: forma de pagamento ao receber parcela (dinheiro/pix/débito/crédito) ✅<br>
    Crediários: taxas aplicadas automaticamente no caixa (débito/crédito) ✅<br>
    Crediários: agrupado por cliente com accordion (expandir/recolher vendas) ✅<br>
    Caixa: ordenação clicável em Data, Tipo, Forma, Vendedora e Líquido ✅<br>
    Vendas: layout invertido (topo → tabela → ranking embaixo) ✅<br>
    Vendas: filtros de período integrados — tabela + ranking + resumo sincronizados ✅<br>
    Vendas: tabela com scroll interno (altura fixa, barra de rolagem) ✅<br>
    Vendas: ranking sem seletor de mês (usa filtro de período da página) ✅<br>
    Vendas: botão no topo + resumo + busca + ordenação clicável + donut ✅<br>
    Visão Geral: layout corrigido (sidebar + conteúdo lado a lado) ✅<br>
    Visão Geral: tudo em uma página sem scroll ✅<br>
    Caixa: taxas descontadas detalhadas por forma de pagamento ✅<br>
    <br><span style='color:#888;font-size:14px'>Correções da v61 (estoque, taxas, rotas, fichas) incluídas.</span><br>
    <br><a href='/'>← Voltar</a>
    </div>"""

if __name__ == '__main__':
    app.run(debug=False)
