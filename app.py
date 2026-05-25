from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, date
import os, json, random, math
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
    """Converte valor em formato BRL (1.000,00) para float."""
    try:
        if not val: return default
        return float(str(val).replace('.','').replace(',','.'))
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
    conn.commit()
    # ── MIGRAÇÕES — adiciona colunas novas em tabelas existentes ──
    migracoes = [
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS desconto NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS pct_desconto NUMERIC(6,2) DEFAULT 0",
        "ALTER TABLE vendas ALTER COLUMN pct_desconto TYPE NUMERIC(6,2)",
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS dias_estoque INTEGER DEFAULT 0",
        "ALTER TABLE estoque_entradas ADD COLUMN IF NOT EXISTS markup NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE estoque_entradas ADD COLUMN IF NOT EXISTS margem_lucro NUMERIC(10,2) DEFAULT 0",
    ]
    for sql in migracoes:
        try:
            cur.execute(sql)
        except Exception:
            conn.rollback()
    conn.commit()
    try:
        for cod, nome, senha in [('F1','Renan Barcellos','renan123'),('F2','Carol Duarte','carol123')]:
            cur.execute("SELECT id FROM usuarios WHERE nome=%s",(nome,))
            if not cur.fetchone():
                perms = 'visao_geral,clientes,vendas,estoque,caixa,crediarios,despesas,usuarios,dashboards'
                cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes) VALUES (%s,%s,%s,'admin',%s)",
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

def get_ctx():
    return dict(nome=session.get('nome'), perfil=session.get('perfil'), cliente=CLIENTE)

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
            if u: cur.execute("UPDATE usuarios SET codigo=%s,senha_hash=%s,perfil='admin',permissoes=%s,ativo=TRUE WHERE id=%s",(cod,h,perms,u['id']))
            else: cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes) VALUES (%s,%s,%s,'admin',%s)",(cod,nome,h,perms))
        conn.commit()
        return "<h2 style='font-family:sans-serif;padding:40px'>Usuarios resetados! Renan Barcellos/renan123 Carol Duarte/carol123 <a href='/'>Login</a></h2>"
    except Exception as e:
        conn.rollback(); return "<pre>ERRO: " + str(e) + "</pre>"
    finally: cur.close(); conn.close()

@app.route('/')
def index():
    if 'uid' in session: return redirect(url_for('visao_geral'))
    return render_template('login.html', cliente=CLIENTE, erro=None)

@app.route('/login', methods=['POST'])
def login():
    nome = request.form.get('usuario','').strip()
    senha = request.form.get('senha','').strip()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE nome=%s AND ativo=TRUE",(nome,))
    u = cur.fetchone(); cur.close(); conn.close()
    if u and check_password_hash(u['senha_hash'], senha):
        session.update(uid=u['id'], nome=u['nome'], perfil=u['perfil'],
                       codigo=u.get('codigo',''),
                       permissoes=u.get('permissoes','visao_geral,clientes,vendas,estoque'))
        return redirect(url_for('visao_geral'))
    return render_template('login.html', cliente=CLIENTE, erro='Usuario ou senha incorretos.')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'))

@app.route('/visao-geral')
@login_required
def visao_geral():
    conn = get_db(); cur = conn.cursor()
    hoje = datetime.now()
    mes_ini = hoje.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    formas = ['dinheiro','pix','debito','credito_vista','credito_parcelado','link','crediario']
    fat = {}
    for f in formas:
        try:
            cur.execute("SELECT COALESCE(SUM(valor_total),0) as v FROM vendas WHERE forma_pagamento=%s AND criado_em>=%s",(f,mes_ini))
            fat[f] = float(cur.fetchone()['v'])
        except: fat[f] = 0.0
    fat_total = sum(fat.values())
    try:
        cur.execute("SELECT COALESCE(SUM(valor_venda*quantidade),0) as v FROM estoque WHERE ativo=TRUE")
        val_estoque = float(cur.fetchone()['v'])
    except: val_estoque = 0.0
    try:
        cur.execute("SELECT COALESCE(SUM(saldo_devedor),0) as v FROM crediarios WHERE status='aberto'")
        val_crediarios = float(cur.fetchone()['v'])
    except: val_crediarios = 0.0
    try:
        cur.execute("SELECT COALESCE(SUM(valor),0) as v FROM despesas WHERE DATE_TRUNC('month',criado_em)=DATE_TRUNC('month',NOW())")
        val_despesas = float(cur.fetchone()['v'])
    except: val_despesas = 0.0
    try:
        cur.execute("SELECT id,criado_em,vendedora_nome,cliente_nome,valor_total,forma_pagamento FROM vendas ORDER BY criado_em DESC LIMIT 8")
        movs = [dict(r) for r in cur.fetchall()]
    except: movs = []
    try:
        cur.execute("SELECT codigo,modelo,tamanho,quantidade FROM estoque WHERE ativo=TRUE AND quantidade<=2 ORDER BY quantidade")
        estoque_baixo = [dict(r) for r in cur.fetchall()]
    except: estoque_baixo = []
    cur.close(); conn.close()
    ctx = get_ctx()
    ctx.update(fat=fat, fat_total=fat_total, val_estoque=val_estoque,
               val_crediarios=val_crediarios, val_despesas=val_despesas,
               movs=movs, estoque_baixo=estoque_baixo,
               mes_atual=hoje.strftime('%B / %Y').capitalize(),
               hoje=hoje.strftime('%A, %d de %B de %Y').capitalize())
    return render_template('visao_geral.html', **ctx)

@app.route('/usuarios')
@login_required
def usuarios():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios ORDER BY id")
    lista = [dict(u) for u in cur.fetchall()]
    cur.close(); conn.close()
    ctx = get_ctx(); ctx['usuarios'] = lista
    return render_template('usuarios.html', **ctx)

@app.route('/usuarios/novo', methods=['GET','POST'])
@login_required
def usuario_novo():
    ctx = get_ctx()
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        senha = request.form.get('senha','').strip()
        perfil = request.form.get('perfil','vendedor')
        perms = ','.join(request.form.getlist('permissoes') or ['visao_geral','clientes','vendas','estoque'])
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as t FROM usuarios"); n = cur.fetchone()['t']
        try:
            cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes) VALUES (%s,%s,%s,%s,%s)",
                        (f"F{n+1}",nome,generate_password_hash(senha),perfil,perms))
            conn.commit(); flash('Usuario cadastrado!','ok')
        except Exception as e: conn.rollback(); flash(str(e),'erro')
        finally: cur.close(); conn.close()
        return redirect(url_for('usuarios'))
    return render_template('usuario_form.html', **ctx)

@app.route('/usuarios/<int:uid>/editar', methods=['GET','POST'])
@login_required
def usuario_editar(uid):
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        perfil = request.form.get('perfil','vendedor')
        perms = ','.join(request.form.getlist('permissoes') or ['visao_geral','clientes','vendas','estoque'])
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
    user = dict(cur.fetchone())
    user['perms_lista'] = user.get('permissoes','').split(',')
    cur.close(); conn.close()
    ctx = get_ctx(); ctx['user'] = user
    return render_template('usuario_editar.html', **ctx)

@app.route('/usuarios/<int:uid>/toggle', methods=['POST'])
@login_required
def usuario_toggle(uid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE usuarios SET ativo=NOT ativo WHERE id=%s",(uid,))
    conn.commit(); cur.close(); conn.close()
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
    c = dict(cur.fetchone()); cur.close(); conn.close()
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
    ctx = get_ctx(); ctx['c'] = c
    return render_template('editar_cliente.html', **ctx)

@app.route('/clientes/<int:cid>/excluir', methods=['POST'])
@login_required
def excluir_cliente(cid):
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
    cur.close(); conn.close()
    hoje = date.today()
    # Buscar total de entradas adicionais por item
    cur2 = conn.cursor() if False else get_db().cursor()
    cur2.execute("SELECT estoque_id, COALESCE(SUM(quantidade),0) as total FROM estoque_entradas GROUP BY estoque_id")
    entradas_map = {r['estoque_id']: int(r['total']) for r in cur2.fetchall()}
    cur2.close()
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
    try:
        cur.execute("""INSERT INTO estoque (codigo,modelo,descricao,tamanho,quantidade,estoque_inicial,
            custo_unitario,markup,valor_venda,margem_lucro) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (f"P{n+1}", request.form.get('modelo','').strip(),
             request.form.get('descricao','').strip() or None,
             request.form.get('tamanho','').strip(), qtd, qtd,
             parse_brl(request.form.get('custo_unitario','0')),
             parse_brl(request.form.get('markup','0')),
             parse_brl(request.form.get('valor_venda','0')),
             parse_brl(request.form.get('margem_lucro','0'))))
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
    cur.execute("SELECT codigo,modelo,tamanho,valor_venda,quantidade FROM estoque WHERE DATE(criado_em)=%s AND ativo=TRUE ORDER BY id",(data,))
    itens = [dict(i) for i in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'itens':itens,'data':data})

@app.route('/estoque/<int:eid>')
@login_required
def ficha_estoque(eid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM estoque WHERE id=%s",(eid,))
    item = dict(cur.fetchone()); cur.close(); conn.close()
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
        cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,usuario_id,vendedora_nome)
            VALUES (%s,%s,'entrada',%s,%s,%s,%s)""",
            (f"Venda {cod} - {cliente_nome}",valor_total,forma,venda_id,usuario_id or None,vendedora_nome))
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
    if session.get('perfil') != 'admin':
        flash('Apenas administradores podem excluir vendas.','erro')
        return redirect(url_for('ficha_venda', vid=vid))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM venda_itens WHERE venda_id=%s",(vid,))
        for item in cur.fetchall():
            if item['produto_id']:
                cur.execute("UPDATE estoque SET quantidade=quantidade+%s WHERE id=%s",(item['quantidade'],item['produto_id']))
        cur.execute("DELETE FROM vendas WHERE id=%s",(vid,))
        conn.commit(); flash('Venda excluida. Estoque restaurado.','ok')
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('vendas'))


@app.route('/vendas/<int:vid>/editar', methods=['GET','POST'])
@login_required
def editar_venda(vid):
    if session.get('perfil') != 'admin':
        flash('Apenas administradores podem editar vendas.','erro')
        return redirect(url_for('ficha_venda', vid=vid))
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
    mes = request.args.get('mes', datetime.now().strftime('%Y-%m'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT vendedora_nome,COALESCE(SUM(valor_total),0) as total,
        COUNT(id) as num_vendas,COUNT(DISTINCT cliente_id) as clientes
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

@app.route('/crediarios')
@login_required
def crediarios():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT c.*,v.codigo as codigo_venda,v.criado_em as data_venda
        FROM crediarios c JOIN vendas v ON v.id=c.venda_id ORDER BY c.status,c.criado_em DESC""")
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
        else:
            cur.execute("SELECT id FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE ORDER BY numero_parcela",(cid,))
            rest = cur.fetchall()
            if rest:
                vp = math.ceil((novo_saldo/len(rest))*100)/100
                for i,p in enumerate(rest):
                    v = round(novo_saldo-vp*(len(rest)-1),2) if i==len(rest)-1 else vp
                    cur.execute("UPDATE crediario_parcelas SET valor=%s WHERE id=%s",(v,p['id']))
            cur.execute("UPDATE crediarios SET saldo_devedor=%s WHERE id=%s",(novo_saldo,cid))
        cur.execute("INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,crediario_id,vendedora_nome) VALUES (%s,%s,'entrada','crediario',%s,%s)",
            (f"Crediario - {cred['cliente_nome']}",valor_pago,cid,vendedora_nome))
        conn.commit(); flash('Pagamento registrado!','ok')
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('crediarios'))

@app.route('/taxas', methods=['GET','POST'])
@login_required
def taxas():
    if session.get('perfil') != 'admin':
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
                (vig, cv, cp, deb, lnk, ant, session.get('usuario_id')))
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
    cur.execute("""SELECT COALESCE(SUM(CASE WHEN tipo='entrada' THEN valor ELSE 0 END),0) as entradas,
        COALESCE(SUM(CASE WHEN tipo='saida' THEN valor ELSE 0 END),0) as saidas
        FROM caixa WHERE DATE(criado_em) BETWEEN %s AND %s""",(data_inicio, data_fim))
    tots = cur.fetchone()
    entradas = float(tots['entradas']); saidas = float(tots['saidas'])
    cur.close(); conn.close()
    taxa_vigente_hoje = get_taxa_vigente()
    ctx = get_ctx()
    # Calcular líquido por movimento
    total_desconto = 0
    for m in movs:
        if m['tipo'] == 'entrada' and m.get('forma_pagamento') in ['credito_vista','credito_parcelado','debito','link']:
            taxa_data = get_taxa_vigente(m['criado_em'].date() if hasattr(m.get('criado_em',''), 'date') else date.today())
            liq, desc, ptc = calcular_liquido(float(m['valor']), m['forma_pagamento'], taxa_data)
            m['valor_liquido'] = liq
            m['desconto_taxa'] = desc
            m['taxa_total_pct'] = ptc
            total_desconto += desc
        else:
            m['valor_liquido'] = float(m['valor'])
            m['desconto_taxa'] = 0
            m['taxa_total_pct'] = 0
    saldo_bruto   = round(entradas - total_desconto, 2)
    saldo_liquido = round(saldo_bruto - saidas, 2)
    ctx.update(movs=movs, entradas=entradas, saidas=saidas,
               saldo=round(entradas-saidas,2),
               saldo_bruto=saldo_bruto,
               total_desconto=round(total_desconto,2), saldo_liquido=saldo_liquido,
               taxa_vigente=taxa_vigente_hoje,
               data_inicio=data_inicio, data_fim=data_fim)
    return render_template('caixa.html', **ctx)

@app.route('/despesas')
@login_required
def despesas():
    conn = get_db(); cur = conn.cursor()
    mes = request.args.get('mes', datetime.now().strftime('%Y-%m'))
    cur.execute("SELECT * FROM despesas WHERE TO_CHAR(criado_em,'YYYY-MM')=%s ORDER BY criado_em DESC",(mes,))
    lista = [dict(d) for d in cur.fetchall()]
    cur.execute("SELECT COALESCE(SUM(valor),0) as t FROM despesas WHERE TO_CHAR(criado_em,'YYYY-MM')=%s",(mes,))
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
    valor = float(request.form.get('valor',0) or 0)
    descricao = request.form.get('descricao','').strip()
    forma = request.form.get('forma_pagamento','').strip()
    try:
        cur.execute("""INSERT INTO despesas (codigo,descricao,categoria,valor,data_despesa,forma_pagamento,usuario_id,usuario_nome)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (f"D{n+1}",descricao,request.form.get('categoria','').strip() or None,
             valor,request.form.get('data_despesa') or date.today().isoformat(),
             forma or None,session['uid'],session['nome']))
        desp_id = cur.fetchone()['id']
        cur.execute("INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,despesa_id,usuario_id,vendedora_nome) VALUES (%s,%s,'saida',%s,%s,%s,%s)",
            (f"Despesa: {descricao}",valor,forma or None,desp_id,session['uid'],session['nome']))
        conn.commit(); flash('Despesa registrada!','ok')
    except Exception as e: conn.rollback(); flash(str(e),'erro')
    finally: cur.close(); conn.close()
    return redirect(url_for('despesas'))

@app.route('/despesas/<int:did>/excluir', methods=['POST'])
@login_required
def excluir_despesa(did):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM caixa WHERE despesa_id=%s",(did,))
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

if __name__ == '__main__':
    app.run(debug=False)

@app.route('/versao')
def versao():
    return """<div style='font-family:monospace;padding:40px;font-size:18px'>
    <b>CD Gestão</b><br>
    Versão: <b style='color:green'>v24 — 2026-05-22</b><br>
    Clientes: máscaras telefone/CEP, WhatsApp, GPS, aniversários ✅<br>
    Estoque: design corrigido ✅<br>
    <br><a href='/'>← Voltar</a>
    </div>"""
