from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, date
import os, json, random, math
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cd-gestao-2026-secret')
DATABASE_URL = os.environ.get('DATABASE_URL')

CLIENTE = {
    'nome': 'CD Gestão Empresarial',
    'loja': 'By Carol Duarte',
    'sigla': 'CD · GESTÃO',
    'tagline': 'Gestão inteligente para sua loja.',
    'cor_primaria': '#1a1a2e',
    'cor_secundaria': '#f4f4f6',
    'cor_botao': '#2e7d32'
}

ABAS = [
    ('visao_geral','Visão Geral'),('clientes','Clientes'),('vendas','Vendas'),
    ('estoque','Estoque'),('caixa','Caixa'),('crediarios','Crediários'),
    ('despesas','Despesas'),('usuarios','Usuários'),('relatorios','Relatórios'),('dashboards','Dashboards'),
]

CORES = ['#2e7d32','#1565c0','#6a1b9a','#c62828','#e65100','#00695c','#283593','#4a148c']

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def db_exec(sql, params=(), fetchone=False, fetchall=False, commit=False):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    result = None
    if fetchone: result = dict(cur.fetchone()) if cur.rowcount != 0 else None
    if fetchall: result = [dict(r) for r in cur.fetchall()]
    if commit: conn.commit()
    cur.close(); conn.close()
    return result

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE,
        nome VARCHAR(200) NOT NULL UNIQUE, senha_hash VARCHAR(300),
        perfil VARCHAR(20) DEFAULT 'vendedor',
        permissoes TEXT DEFAULT 'visao_geral,clientes,vendas,estoque',
        ativo BOOLEAN DEFAULT TRUE,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS clientes (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE,
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

    for m in ['Vestido','Calça','Blusa','Bolsa','Saia','Macacão','Conjunto','Short','Blazer','Kimono']:
        cur.execute("INSERT INTO modelos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING",(m,))
    for t in ['PP','P','M','G','GG','EG','EGG','36','38','40','42','44','46','48','50','52','54','56','58','60','ÚNICO']:
        cur.execute("INSERT INTO tamanhos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING",(t,))

    cur.execute("""CREATE TABLE IF NOT EXISTS estoque (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE NOT NULL,
        modelo VARCHAR(100), descricao TEXT, tamanho VARCHAR(20),
        quantidade INTEGER DEFAULT 1, estoque_inicial INTEGER DEFAULT 1,
        custo_unitario NUMERIC(10,2) DEFAULT 0, markup NUMERIC(10,2) DEFAULT 0,
        valor_venda NUMERIC(10,2) DEFAULT 0, margem_lucro NUMERIC(10,2) DEFAULT 0,
        ativo BOOLEAN DEFAULT TRUE, ultima_venda DATE,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS vendas (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE,
        usuario_id INTEGER REFERENCES usuarios(id),
        vendedora_nome VARCHAR(200),
        cliente_id INTEGER REFERENCES clientes(id),
        cliente_nome VARCHAR(200),
        valor_total NUMERIC(10,2) DEFAULT 0,
        forma_pagamento VARCHAR(50), parcelas INTEGER DEFAULT 1,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS venda_itens (
        id SERIAL PRIMARY KEY,
        venda_id INTEGER REFERENCES vendas(id) ON DELETE CASCADE,
        produto_id INTEGER REFERENCES estoque(id),
        codigo_produto VARCHAR(10), modelo VARCHAR(100), descricao TEXT,
        tamanho VARCHAR(20), valor_unitario NUMERIC(10,2) DEFAULT 0,
        quantidade INTEGER DEFAULT 1, valor_total NUMERIC(10,2) DEFAULT 0)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS crediarios (
        id SERIAL PRIMARY KEY,
        venda_id INTEGER REFERENCES vendas(id) ON DELETE CASCADE,
        cliente_id INTEGER REFERENCES clientes(id),
        cliente_nome VARCHAR(200),
        valor_total NUMERIC(10,2) DEFAULT 0,
        entrada NUMERIC(10,2) DEFAULT 0,
        saldo_devedor NUMERIC(10,2) DEFAULT 0,
        status VARCHAR(20) DEFAULT 'aberto',
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS crediario_parcelas (
        id SERIAL PRIMARY KEY,
        crediario_id INTEGER REFERENCES crediarios(id) ON DELETE CASCADE,
        numero_parcela INTEGER, data_vencimento DATE,
        valor NUMERIC(10,2) DEFAULT 0,
        pago BOOLEAN DEFAULT FALSE, data_pagamento DATE)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS caixa (
        id SERIAL PRIMARY KEY, descricao TEXT,
        valor NUMERIC(10,2) DEFAULT 0,
        tipo VARCHAR(20) DEFAULT 'entrada',
        forma_pagamento VARCHAR(50),
        venda_id INTEGER, crediario_id INTEGER,
        despesa_id INTEGER, usuario_id INTEGER,
        vendedora_nome VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS despesas (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE,
        descricao TEXT NOT NULL, categoria VARCHAR(100),
        valor NUMERIC(10,2) DEFAULT 0,
        data_despesa DATE DEFAULT CURRENT_DATE,
        forma_pagamento VARCHAR(50),
        usuario_id INTEGER, usuario_nome VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    # Migrações seguras
    migracoes = [
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS codigo VARCHAR(10)",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS permissoes TEXT DEFAULT 'visao_geral,clientes,vendas,estoque'",
        "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS codigo VARCHAR(10)",
        "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS telefone2 VARCHAR(30)",
        "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS cor_avatar VARCHAR(10) DEFAULT '#2e7d32'",
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS codigo VARCHAR(10)",
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS estoque_inicial INTEGER DEFAULT 1",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS codigo VARCHAR(10)",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS usuario_id INTEGER",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS vendedora_nome VARCHAR(200)",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS cliente_id INTEGER",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS cliente_nome VARCHAR(200)",
        "ALTER TABLE venda_itens ADD COLUMN IF NOT EXISTS produto_id INTEGER",
        "ALTER TABLE venda_itens ADD COLUMN IF NOT EXISTS codigo_produto VARCHAR(10)",
        "ALTER TABLE caixa ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'entrada'",
        "ALTER TABLE caixa ADD COLUMN IF NOT EXISTS forma_pagamento VARCHAR(50)",
        "ALTER TABLE caixa ADD COLUMN IF NOT EXISTS venda_id INTEGER",
        "ALTER TABLE caixa ADD COLUMN IF NOT EXISTS crediario_id INTEGER",
        "ALTER TABLE caixa ADD COLUMN IF NOT EXISTS despesa_id INTEGER",
        "ALTER TABLE caixa ADD COLUMN IF NOT EXISTS usuario_id INTEGER",
        "ALTER TABLE caixa ADD COLUMN IF NOT EXISTS vendedora_nome VARCHAR(200)",
        "ALTER TABLE crediarios ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'aberto'",
    ]
    for m in migracoes:
        try: cur.execute(m)
        except: conn.rollback()

    # Remover NOT NULL de referencia (coluna legada)
    try: cur.execute("ALTER TABLE estoque ALTER COLUMN referencia DROP NOT NULL")
    except: conn.rollback()

    # Sync codigo com referencia para dados antigos
    try: cur.execute("UPDATE estoque SET codigo=referencia WHERE codigo IS NULL AND referencia IS NOT NULL")
    except: conn.rollback()

    # Usuários padrão
    for cod, nome, senha, perfil in [
        ('F1','Renan Barcellos','renan123','admin'),
        ('F2','Carol Duarte','carol123','admin')]:
        cur.execute("SELECT id FROM usuarios WHERE nome=%s",(nome,))
        if not cur.fetchone():
            cur.execute("""INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes)
                VALUES (%s,%s,%s,%s,'visao_geral,clientes,vendas,estoque,caixa,crediarios,despesas,usuarios,relatorios,dashboards')""",
                (cod,nome,generate_password_hash(senha),perfil))
        else:
            cur.execute("UPDATE usuarios SET codigo=%s WHERE nome=%s AND codigo IS NULL",(cod,nome))

    conn.commit(); cur.close(); conn.close()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'uid' not in session: return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def get_ctx():
    return dict(nome=session.get('nome'), perfil=session.get('perfil'),
                permissoes=session.get('permissoes','').split(','),
                cliente=CLIENTE, abas=ABAS)

# ══════════════════════════════════════════
# RESET E UTILITÁRIOS
# ══════════════════════════════════════════


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
        valor_total = float(request.form.get('valor_total',0) or 0)
        itens = json.loads(request.form.get('itens','[]'))

        cur.execute("SELECT COUNT(*) as t FROM vendas"); n = cur.fetchone()['t']
        cod = f"V{n+1}"
        cur.execute("""INSERT INTO vendas (codigo,usuario_id,vendedora_nome,cliente_id,cliente_nome,
            valor_total,forma_pagamento,parcelas) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (cod,usuario_id or None,vendedora_nome,cliente_id or None,cliente_nome,valor_total,forma,parcelas))
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

        # Crediário
        if forma == 'crediario':
            entrada = float(request.form.get('entrada',0) or 0)
            saldo = valor_total - entrada
            cur.execute("""INSERT INTO crediarios (venda_id,cliente_id,cliente_nome,valor_total,entrada,saldo_devedor)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (venda_id,cliente_id or None,cliente_nome,valor_total,entrada,saldo))
            cred_id = cur.fetchone()['id']
            for i,p in enumerate(json.loads(request.form.get('parcelas_datas','[]'))):
                cur.execute("INSERT INTO crediario_parcelas (crediario_id,numero_parcela,data_vencimento,valor) VALUES (%s,%s,%s,%s)",
                    (cred_id,i+1,p.get('data'),float(p.get('valor',0))))

        # Caixa
        cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,usuario_id,vendedora_nome)
            VALUES (%s,%s,'entrada',%s,%s,%s,%s)""",
            (f"Venda {cod} — {cliente_nome}",valor_total,forma,venda_id,usuario_id or None,vendedora_nome))

        conn.commit(); flash('✅ Venda registrada!','ok')
    except Exception as e:
        conn.rollback(); flash(f'Erro: {e}','erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('vendas'))

@app.route('/vendas/<int:vid>')
@login_required
def ficha_venda(vid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM vendas WHERE id=%s",(vid,))
    row = cur.fetchone()
    if not row: flash('Venda não encontrada.','erro'); return redirect(url_for('vendas'))
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
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM venda_itens WHERE venda_id=%s",(vid,))
        for item in cur.fetchall():
            if item['produto_id']:
                cur.execute("UPDATE estoque SET quantidade=quantidade+%s WHERE id=%s",(item['quantidade'],item['produto_id']))
        cur.execute("DELETE FROM vendas WHERE id=%s",(vid,))
        conn.commit(); flash('✅ Venda excluída. Estoque restaurado.','ok')
    except Exception as e: conn.rollback(); flash(f'Erro: {e}','erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('vendas'))

@app.route('/vendas/ranking')
@login_required
def ranking_vendedoras():
    mes = request.args.get('mes', datetime.now().strftime('%Y-%m'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT vendedora_nome,COALESCE(SUM(valor_total),0) as total,
        COUNT(id) as num_vendas, COUNT(DISTINCT cliente_id) as clientes
        FROM vendas WHERE TO_CHAR(criado_em,'YYYY-MM')=%s
        GROUP BY vendedora_nome ORDER BY total DESC""",(mes,))
    ranking = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'ranking':ranking})

@app.route('/vendas/buscar-ref')
@login_required
def buscar_ref():
    ref = request.args.get('ref','').strip().upper()
    busca = ref if ref.startswith('P') else f"P{ref}"
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT id as produto_id,codigo,modelo,descricao,tamanho,valor_venda,quantidade
        FROM estoque WHERE codigo=%s AND ativo=TRUE AND quantidade>0""",(busca,))
    item = cur.fetchone()
    cur.close(); conn.close()
    if item: return jsonify({'ok':True,'item':dict(item)})
    return jsonify({'ok':False})

@app.route('/vendas/buscar-cliente')
@login_required
def buscar_cliente():
    q = request.args.get('q','').strip()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT id,codigo,nome,crediario FROM clientes
        WHERE ativo=TRUE AND (LOWER(nome) LIKE %s OR codigo ILIKE %s)
        ORDER BY nome LIMIT 8""",(f'%{q.lower()}%',f'%{q}%'))
    lista = [dict(c) for c in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'clientes':lista})

# ══════════════════════════════════════════
# CREDIÁRIOS
# ══════════════════════════════════════════
@app.route('/crediarios')
@login_required
def crediarios():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT c.*,v.codigo as codigo_venda,v.criado_em as data_venda
        FROM crediarios c JOIN vendas v ON v.id=c.venda_id
        ORDER BY c.status, c.criado_em DESC""")
    lista = [dict(c) for c in cur.fetchall()]
    for c in lista:
        cur.execute("SELECT * FROM crediario_parcelas WHERE crediario_id=%s ORDER BY numero_parcela",(c['id'],))
        c['parcelas'] = [dict(p) for p in cur.fetchall()]
    cur.execute("SELECT COALESCE(SUM(saldo_devedor),0) as t FROM crediarios WHERE status='aberto'")
    total_aberto = float(cur.fetchone()['t'])
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u) for u in cur.fetchall()]
    cur.close(); conn.close()
    ctx = get_ctx(); ctx.update(lista=lista, total_aberto=total_aberto, vendedoras=vendedoras)
    return render_template('crediarios.html', **ctx)

@app.route('/crediarios/<int:cid>/parcela/<int:pid>/pagar', methods=['POST'])
@login_required
def pagar_parcela(cid, pid):
    vendedora_nome = request.form.get('vendedora_nome','').strip()
    valor_pago = float(request.form.get('valor_pago',0) or 0)
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM crediarios WHERE id=%s",(cid,))
        cred = dict(cur.fetchone())
        cur.execute("UPDATE crediario_parcelas SET pago=TRUE,valor=%s,data_pagamento=CURRENT_DATE WHERE id=%s",(valor_pago,pid))
        novo_saldo = round(float(cred['saldo_devedor']) - valor_pago, 2)
        if novo_saldo <= 0.01:
            cur.execute("DELETE FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE",(cid,))
            cur.execute("UPDATE crediarios SET saldo_devedor=0,status='quitado' WHERE id=%s",(cid,))
            msg = 'quitado'
        else:
            cur.execute("SELECT id FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE ORDER BY numero_parcela",(cid,))
            rest = cur.fetchall()
            if rest:
                vp = math.ceil((novo_saldo/len(rest))*100)/100
                for i,p in enumerate(rest):
                    v = round(novo_saldo-vp*(len(rest)-1),2) if i==len(rest)-1 else vp
                    cur.execute("UPDATE crediario_parcelas SET valor=%s WHERE id=%s",(v,p['id']))
            cur.execute("UPDATE crediarios SET saldo_devedor=%s WHERE id=%s",(novo_saldo,cid))
            msg = 'atualizado'
        # Registrar no caixa
        cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,crediario_id,vendedora_nome)
            VALUES (%s,%s,'entrada','crediario',%s,%s)""",
            (f"Crediário — {cred['cliente_nome']}",valor_pago,cid,vendedora_nome))
        conn.commit(); flash(f'✅ Pagamento registrado! Crediário {msg}.','ok')
    except Exception as e: conn.rollback(); flash(f'Erro: {e}','erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('crediarios'))

# ══════════════════════════════════════════
# CAIXA
# ══════════════════════════════════════════
@app.route('/caixa')
@login_required
def caixa():
    conn = get_db(); cur = conn.cursor()
    mes = request.args.get('mes', datetime.now().strftime('%Y-%m'))
    cur.execute("""SELECT * FROM caixa WHERE TO_CHAR(criado_em,'YYYY-MM')=%s ORDER BY criado_em DESC""",(mes,))
    movs = [dict(m) for m in cur.fetchall()]
    cur.execute("""SELECT COALESCE(SUM(CASE WHEN tipo='entrada' THEN valor ELSE 0 END),0) as entradas,
        COALESCE(SUM(CASE WHEN tipo='saida' THEN valor ELSE 0 END),0) as saidas
        FROM caixa WHERE TO_CHAR(criado_em,'YYYY-MM')=%s""",(mes,))
    tots = cur.fetchone()
    entradas = float(tots['entradas']); saidas = float(tots['saidas'])
    saldo = entradas - saidas
    cur.execute("SELECT DISTINCT TO_CHAR(criado_em,'YYYY-MM') as mes FROM caixa ORDER BY mes DESC")
    meses = [r['mes'] for r in cur.fetchall()]
    cur.close(); conn.close()
    ctx = get_ctx()
    ctx.update(movs=movs, entradas=entradas, saidas=saidas, saldo=saldo,
               mes_atual=mes, meses=meses)
    return render_template('caixa.html', **ctx)

# ══════════════════════════════════════════
# DESPESAS
# ══════════════════════════════════════════
@app.route('/despesas')
@login_required
def despesas():
    conn = get_db(); cur = conn.cursor()
    mes = request.args.get('mes', datetime.now().strftime('%Y-%m'))
    cur.execute("""SELECT * FROM despesas WHERE TO_CHAR(criado_em,'YYYY-MM')=%s ORDER BY criado_em DESC""",(mes,))
    lista = [dict(d) for d in cur.fetchall()]
    cur.execute("""SELECT COALESCE(SUM(valor),0) as t FROM despesas WHERE TO_CHAR(criado_em,'YYYY-MM')=%s""",(mes,))
    total = float(cur.fetchone()['t'])
    cur.execute("SELECT DISTINCT TO_CHAR(criado_em,'YYYY-MM') as mes FROM despesas ORDER BY mes DESC")
    meses = [r['mes'] for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) as t FROM despesas"); n = cur.fetchone()['t']
    cur.close(); conn.close()
    ctx = get_ctx()
    ctx.update(lista=lista, total=total, mes_atual=mes, meses=meses, next_cod=f"D{n+1}")
    return render_template('despesas.html', **ctx)

@app.route('/despesas/nova', methods=['POST'])
@login_required
def nova_despesa():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as t FROM despesas"); n = cur.fetchone()['t']
    cod = f"D{n+1}"
    descricao = request.form.get('descricao','').strip()
    categoria = request.form.get('categoria','').strip()
    valor = float(request.form.get('valor',0) or 0)
    forma = request.form.get('forma_pagamento','').strip()
    data_d = request.form.get('data_despesa') or date.today().isoformat()
    try:
        cur.execute("""INSERT INTO despesas (codigo,descricao,categoria,valor,data_despesa,forma_pagamento,usuario_id,usuario_nome)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (cod,descricao,categoria or None,valor,data_d,forma or None,session['uid'],session['nome']))
        desp_id = cur.fetchone()['id']
        # Lançar no caixa como saída
        cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,despesa_id,usuario_id,vendedora_nome)
            VALUES (%s,%s,'saida',%s,%s,%s,%s)""",
            (f"Despesa: {descricao}",valor,forma or None,desp_id,session['uid'],session['nome']))
        conn.commit(); flash('✅ Despesa registrada e lançada no caixa!','ok')
    except Exception as e: conn.rollback(); flash(f'Erro: {e}','erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('despesas'))

@app.route('/despesas/<int:did>/excluir', methods=['POST'])
@login_required
def excluir_despesa(did):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM caixa WHERE despesa_id=%s",(did,))
        cur.execute("DELETE FROM despesas WHERE id=%s",(did,))
        conn.commit(); flash('✅ Despesa excluída.','ok')
    except Exception as e: conn.rollback(); flash(f'Erro: {e}','erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('despesas'))

# ══════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════
@app.route('/dashboard')
@login_required
def dashboard_view():
    conn = get_db(); cur = conn.cursor()
    hoje = datetime.now()
    mes_ini = hoje.replace(day=1,hour=0,minute=0,second=0,microsecond=0)

    # Vendas por dia no mês
    cur.execute("""SELECT DATE(criado_em) as dia, COUNT(*) as qtd, COALESCE(SUM(valor_total),0) as total
        FROM vendas WHERE criado_em>=%s GROUP BY DATE(criado_em) ORDER BY dia""",(mes_ini,))
    vendas_dia = [dict(r) for r in cur.fetchall()]

    # Ranking produtos mais vendidos
    cur.execute("""SELECT vi.codigo_produto, vi.modelo, SUM(vi.quantidade) as qtd_vendida,
        SUM(vi.valor_total) as receita FROM venda_itens vi
        JOIN vendas v ON v.id=vi.venda_id WHERE v.criado_em>=%s
        GROUP BY vi.codigo_produto,vi.modelo ORDER BY qtd_vendida DESC LIMIT 10""",(mes_ini,))
    top_produtos = [dict(r) for r in cur.fetchall()]

    # Formas de pagamento
    cur.execute("""SELECT forma_pagamento, COUNT(*) as qtd, COALESCE(SUM(valor_total),0) as total
        FROM vendas WHERE criado_em>=%s GROUP BY forma_pagamento ORDER BY total DESC""",(mes_ini,))
    formas_pag = [dict(r) for r in cur.fetchall()]

    # Vendedoras
    cur.execute("""SELECT vendedora_nome, COUNT(*) as qtd_vendas,
        COALESCE(SUM(valor_total),0) as total, COUNT(DISTINCT cliente_id) as clientes
        FROM vendas WHERE criado_em>=%s GROUP BY vendedora_nome ORDER BY total DESC""",(mes_ini,))
    vendedoras_rank = [dict(r) for r in cur.fetchall()]

    # Fluxo caixa mês
    cur.execute("""SELECT COALESCE(SUM(CASE WHEN tipo='entrada' THEN valor ELSE 0 END),0) as ent,
        COALESCE(SUM(CASE WHEN tipo='saida' THEN valor ELSE 0 END),0) as sai
        FROM caixa WHERE criado_em>=%s""",(mes_ini,))
    fluxo = cur.fetchone()

    # Clientes novos no mês
    cur.execute("SELECT COUNT(*) as t FROM clientes WHERE criado_em>=%s",(mes_ini,))
    clientes_novos = cur.fetchone()['t']

    # Ticket médio
    cur.execute("SELECT COALESCE(AVG(valor_total),0) as t FROM vendas WHERE criado_em>=%s",(mes_ini,))
    ticket_medio = float(cur.fetchone()['t'])

    cur.close(); conn.close()
    ctx = get_ctx()
    ctx.update(vendas_dia=vendas_dia, top_produtos=top_produtos, formas_pag=formas_pag,
               vendedoras_rank=vendedoras_rank, fluxo=dict(fluxo),
               clientes_novos=clientes_novos, ticket_medio=ticket_medio,
               mes_atual=hoje.strftime('%B / %Y').capitalize())
    return render_template('dashboard.html', **ctx)

# ══════════════════════════════════════════
# COMPATIBILIDADE
# ══════════════════════════════════════════


with app.app_context():
    try: init_db()
    except Exception as e: print(f"init_db erro: {e}")

if __name__ == '__main__':
    app.run(debug=False)
