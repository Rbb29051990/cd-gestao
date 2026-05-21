from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import json
from werkzeug.security import generate_password_hash, check_password_hash

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

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # USUÁRIOS (funcionários)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            codigo VARCHAR(10) UNIQUE,
            nome VARCHAR(200) NOT NULL,
            senha_hash VARCHAR(200),
            perfil VARCHAR(20) DEFAULT 'vendedor',
            ativo BOOLEAN DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migração: adicionar coluna codigo se não existir
    cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS codigo VARCHAR(10)")

    # CLIENTES
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            codigo VARCHAR(10) UNIQUE,
            nome VARCHAR(200) NOT NULL,
            cpf VARCHAR(20),
            data_nascimento DATE,
            telefone VARCHAR(30),
            telefone2 VARCHAR(30),
            cep VARCHAR(10),
            logradouro VARCHAR(200),
            numero VARCHAR(20),
            complemento VARCHAR(100),
            bairro VARCHAR(100),
            cidade VARCHAR(100),
            uf VARCHAR(2),
            promocoes BOOLEAN DEFAULT TRUE,
            crediario BOOLEAN DEFAULT FALSE,
            ativo BOOLEAN DEFAULT TRUE,
            cor_avatar VARCHAR(10) DEFAULT '#2e7d32',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS codigo VARCHAR(10)")
    cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS telefone2 VARCHAR(30)")

    # MODELOS E TAMANHOS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS modelos_estoque (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100) UNIQUE NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for m in ['Vestido','Calça','Blusa','Bolsa','Saia','Macacão','Conjunto']:
        cur.execute("INSERT INTO modelos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (m,))

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tamanhos_estoque (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(20) UNIQUE NOT NULL
        )
    """)
    for t in ['PP','P','M','G','GG','EG','EGG','36','38','40','42','44','46','48','50','52','54','56','58','60']:
        cur.execute("INSERT INTO tamanhos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (t,))

    # ESTOQUE (PRODUTOS)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            id SERIAL PRIMARY KEY,
            codigo VARCHAR(10) UNIQUE,
            modelo VARCHAR(100),
            descricao TEXT,
            tamanho VARCHAR(20),
            quantidade INTEGER DEFAULT 1,
            estoque_inicial INTEGER DEFAULT 1,
            custo_unitario NUMERIC(10,2),
            markup NUMERIC(10,2),
            valor_venda NUMERIC(10,2),
            margem_lucro NUMERIC(10,2),
            ativo BOOLEAN DEFAULT TRUE,
            ultima_venda DATE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("ALTER TABLE estoque ADD COLUMN IF NOT EXISTS codigo VARCHAR(10)")
    cur.execute("ALTER TABLE estoque ADD COLUMN IF NOT EXISTS estoque_inicial INTEGER DEFAULT 1")

    # VENDAS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id SERIAL PRIMARY KEY,
            codigo VARCHAR(10) UNIQUE,
            usuario_id INTEGER REFERENCES usuarios(id),
            vendedora_nome VARCHAR(200),
            cliente_id INTEGER REFERENCES clientes(id),
            cliente_nome VARCHAR(200),
            valor_total NUMERIC(10,2),
            forma_pagamento VARCHAR(50),
            parcelas INTEGER DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("ALTER TABLE vendas ADD COLUMN IF NOT EXISTS codigo VARCHAR(10)")

    # ITENS DA VENDA
    cur.execute("""
        CREATE TABLE IF NOT EXISTS venda_itens (
            id SERIAL PRIMARY KEY,
            venda_id INTEGER REFERENCES vendas(id) ON DELETE CASCADE,
            produto_id INTEGER REFERENCES estoque(id),
            codigo_produto VARCHAR(10),
            modelo VARCHAR(100),
            descricao TEXT,
            tamanho VARCHAR(20),
            valor_unitario NUMERIC(10,2),
            quantidade INTEGER DEFAULT 1,
            valor_total NUMERIC(10,2)
        )
    """)

    # CREDIÁRIOS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS crediarios (
            id SERIAL PRIMARY KEY,
            venda_id INTEGER REFERENCES vendas(id) ON DELETE CASCADE,
            cliente_id INTEGER REFERENCES clientes(id),
            cliente_nome VARCHAR(200),
            valor_total NUMERIC(10,2),
            entrada NUMERIC(10,2) DEFAULT 0,
            saldo_devedor NUMERIC(10,2),
            status VARCHAR(20) DEFAULT 'aberto',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # PARCELAS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS crediario_parcelas (
            id SERIAL PRIMARY KEY,
            crediario_id INTEGER REFERENCES crediarios(id) ON DELETE CASCADE,
            numero_parcela INTEGER,
            data_vencimento DATE,
            valor NUMERIC(10,2),
            pago BOOLEAN DEFAULT FALSE,
            data_pagamento DATE
        )
    """)

    # CAIXA
    cur.execute("""
        CREATE TABLE IF NOT EXISTS caixa (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor NUMERIC(10,2),
            tipo VARCHAR(20) DEFAULT 'entrada',
            forma_pagamento VARCHAR(50),
            venda_id INTEGER,
            crediario_id INTEGER,
            usuario_id INTEGER,
            vendedora_nome VARCHAR(200),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Criar usuários padrão se não existirem
    for codigo, nome, senha, perfil in [('F1','Renan Barcellos','renan123','admin'),('F2','Carol Duarte','carol123','admin')]:
        cur.execute("SELECT id FROM usuarios WHERE nome=%s", (nome,))
        if not cur.fetchone():
            h = generate_password_hash(senha)
            cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil) VALUES (%s,%s,%s,%s)", (codigo,nome,h,perfil))

    conn.commit()
    cur.close()
    conn.close()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def proximo_codigo(prefixo, tabela):
    """Gera próximo código: C1, C2... P1, P2... etc"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) as total FROM {tabela}")
    total = cur.fetchone()['total']
    cur.close()
    conn.close()
    return f"{prefixo}{total+1}"

# ─── LOGIN ───
@app.route('/')
def index():
    if 'usuario_id' in session:
        return redirect(url_for('visao_geral'))
    return render_template('login.html', cliente=CLIENTE)

@app.route('/login', methods=['POST'])
def login():
    nome = request.form.get('usuario','').strip()
    senha = request.form.get('senha','').strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE nome=%s AND ativo=TRUE", (nome,))
    u = cur.fetchone()
    cur.close()
    conn.close()
    if u and check_password_hash(u['senha_hash'], senha):
        session['usuario_id'] = u['id']
        session['nome'] = u['nome']
        session['perfil'] = u['perfil']
        session['codigo'] = u['codigo']
        return redirect(url_for('visao_geral'))
    flash('Usuário ou senha incorretos.', 'erro')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ─── VISÃO GERAL ───
@app.route('/visao-geral')
@login_required
def visao_geral():
    conn = get_db()
    cur = conn.cursor()
    hoje = datetime.now()
    mes_ini = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    formas = ['dinheiro','pix','debito','credito_vista','credito_parcelado','link','crediario']
    fat = {}
    for f in formas:
        cur.execute("SELECT COALESCE(SUM(valor_total),0) as total FROM vendas WHERE forma_pagamento=%s AND criado_em>=%s", (f, mes_ini))
        fat[f] = float(cur.fetchone()['total'])
    fat_total = sum(fat.values())
    cur.execute("SELECT COALESCE(SUM(valor_venda*quantidade),0) as vt FROM estoque WHERE ativo=TRUE")
    valor_estoque = float(cur.fetchone()['vt'])
    cur.execute("SELECT COALESCE(SUM(saldo_devedor),0) as total FROM crediarios WHERE status='aberto'")
    crediarios_total = float(cur.fetchone()['total'])
    cur.execute("SELECT v.id, v.criado_em, v.vendedora_nome, v.cliente_nome, v.valor_total, v.forma_pagamento FROM vendas v ORDER BY v.criado_em DESC LIMIT 10")
    movimentacoes = [dict(m) for m in cur.fetchall()]
    cur.close()
    conn.close()
    mes_atual = hoje.strftime('%B / %Y').capitalize()
    hoje_fmt = hoje.strftime('%A, %d de %B de %Y').capitalize()
    return render_template('visao_geral.html', cliente=CLIENTE,
                           fat=fat, fat_total=fat_total,
                           valor_estoque=valor_estoque,
                           crediarios_total=crediarios_total,
                           saidas_total=0,
                           movimentacoes=movimentacoes,
                           mes_atual=mes_atual, hoje=hoje_fmt,
                           nome=session.get('nome'), perfil=session.get('perfil'))

# ─── USUÁRIOS ───
@app.route('/usuarios')
@login_required
def usuarios():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios ORDER BY id")
    lista = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('usuarios.html', cliente=CLIENTE, usuarios=lista,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/usuarios/novo', methods=['GET','POST'])
@login_required
def usuario_novo():
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        senha = request.form.get('senha','').strip()
        perfil = request.form.get('perfil','vendedor')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as total FROM usuarios")
        total = cur.fetchone()['total']
        codigo = f"F{total+1}"
        cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil) VALUES (%s,%s,%s,%s)",
                    (codigo, nome, generate_password_hash(senha), perfil))
        conn.commit()
        cur.close()
        conn.close()
        flash('✅ Usuário cadastrado!', 'ok')
        return redirect(url_for('usuarios'))
    return render_template('usuario_form.html', cliente=CLIENTE,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/usuarios/<int:uid>/editar', methods=['GET','POST'])
@login_required
def usuario_editar(uid):
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        perfil = request.form.get('perfil','vendedor')
        cur.execute("UPDATE usuarios SET nome=%s, perfil=%s WHERE id=%s", (nome, perfil, uid))
        conn.commit()
        cur.close()
        conn.close()
        flash('✅ Usuário atualizado!', 'ok')
        return redirect(url_for('usuarios'))
    cur.execute("SELECT * FROM usuarios WHERE id=%s", (uid,))
    u = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('usuario_editar.html', cliente=CLIENTE, u=u,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/usuarios/<int:uid>/senha', methods=['POST'])
@login_required
def usuario_senha(uid):
    nova = request.form.get('nova_senha','').strip()
    if nova:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE usuarios SET senha_hash=%s WHERE id=%s", (generate_password_hash(nova), uid))
        conn.commit()
        cur.close()
        conn.close()
        flash('✅ Senha atualizada!', 'ok')
    return redirect(url_for('usuarios'))

@app.route('/usuarios/<int:uid>/toggle', methods=['POST'])
@login_required
def usuario_toggle(uid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE usuarios SET ativo = NOT ativo WHERE id=%s", (uid,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('usuarios'))

@app.route('/minha-senha', methods=['GET','POST'])
@login_required
def minha_senha():
    if request.method == 'POST':
        atual = request.form.get('senha_atual','')
        nova = request.form.get('nova_senha','')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT senha_hash FROM usuarios WHERE id=%s", (session['usuario_id'],))
        u = cur.fetchone()
        if u and check_password_hash(u['senha_hash'], atual):
            cur.execute("UPDATE usuarios SET senha_hash=%s WHERE id=%s",
                        (generate_password_hash(nova), session['usuario_id']))
            conn.commit()
            flash('✅ Senha alterada!', 'ok')
        else:
            flash('Senha atual incorreta.', 'erro')
        cur.close()
        conn.close()
        return redirect(url_for('minha_senha'))
    return render_template('minha_senha.html', cliente=CLIENTE,
                           nome=session.get('nome'), perfil=session.get('perfil'))

# ─── CLIENTES ───
@app.route('/clientes')
@login_required
def clientes():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE ativo=TRUE ORDER BY nome")
    lista = cur.fetchall()
    cur.execute("SELECT COUNT(*) as total FROM clientes WHERE ativo=TRUE")
    total = cur.fetchone()['total']
    cur.close()
    conn.close()
    next_codigo = f"C{total+1}"
    for c in lista:
        partes = c['nome'].split()
        c['iniciais'] = (partes[0][0] + (partes[1][0] if len(partes)>1 else partes[0][1])).upper()
    return render_template('clientes.html', cliente=CLIENTE, clientes=lista,
                           next_id=next_codigo,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/clientes/novo', methods=['POST'])
@login_required
def novo_cliente():
    cores = ['#2e7d32','#1565c0','#6a1b9a','#c62828','#e65100','#00695c','#283593','#4a148c']
    nome = request.form.get('nome','').strip()
    cpf = request.form.get('cpf','').strip()
    data_nascimento = request.form.get('data_nascimento') or None
    telefone = request.form.get('telefone','').strip()
    telefone2 = request.form.get('telefone2','').strip()
    cep = request.form.get('cep','').strip()
    logradouro = request.form.get('logradouro','').strip()
    numero = request.form.get('numero','').strip()
    complemento = request.form.get('complemento','').strip()
    bairro = request.form.get('bairro','').strip()
    cidade = request.form.get('cidade','').strip()
    uf = request.form.get('uf','').strip()
    promocoes = request.form.get('promocoes','0') == '1'
    crediario = request.form.get('crediario','0') == '1'
    if not nome:
        flash('Nome é obrigatório.', 'erro')
        return redirect(url_for('clientes'))
    conn = get_db()
    cur = conn.cursor()
    # Bloqueios de duplicidade
    cur.execute("SELECT id FROM clientes WHERE LOWER(TRIM(nome))=LOWER(TRIM(%s))", (nome,))
    if cur.fetchone():
        cur.close(); conn.close()
        flash(f'DUPLICADO_NOME||{nome}', 'erro')
        return redirect(url_for('clientes'))
    if cpf:
        cur.execute("SELECT id FROM clientes WHERE cpf=%s", (cpf,))
        if cur.fetchone():
            cur.close(); conn.close()
            flash(f'DUPLICADO_CPF||{cpf}', 'erro')
            return redirect(url_for('clientes'))
    if telefone:
        cur.execute("SELECT id FROM clientes WHERE telefone=%s OR telefone2=%s", (telefone,telefone))
        if cur.fetchone():
            cur.close(); conn.close()
            flash(f'DUPLICADO_TEL||{telefone}', 'erro')
            return redirect(url_for('clientes'))
    cur.execute("SELECT COUNT(*) as total FROM clientes")
    total = cur.fetchone()['total']
    codigo = f"C{total+1}"
    cor = random.choice(cores)
    try:
        cur.execute("""INSERT INTO clientes (codigo,nome,cpf,data_nascimento,telefone,telefone2,
                       cep,logradouro,numero,complemento,bairro,cidade,uf,promocoes,crediario,cor_avatar)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (codigo,nome,cpf or None,data_nascimento,telefone or None,telefone2 or None,
                     cep or None,logradouro or None,numero or None,complemento or None,
                     bairro or None,cidade or None,uf or None,promocoes,crediario,cor))
        conn.commit()
        flash('SUCESSO||Cliente cadastrado com sucesso!', 'ok')
    except Exception as e:
        flash(f'Erro: {e}', 'erro')
    finally:
        cur.close(); conn.close()
    return redirect(url_for('clientes'))

@app.route('/clientes/verificar')
@login_required
def verificar_cliente():
    campo = request.args.get('campo')
    valor = request.args.get('valor','').strip()
    cid = request.args.get('id', None)
    if not campo or not valor:
        return jsonify({'ok': True})
    conn = get_db()
    cur = conn.cursor()
    if campo == 'nome':
        cur.execute("SELECT id FROM clientes WHERE LOWER(nome)=LOWER(%s)", (valor,))
    elif campo == 'cpf':
        cur.execute("SELECT id FROM clientes WHERE cpf=%s", (valor,))
    elif campo == 'telefone':
        cur.execute("SELECT id FROM clientes WHERE telefone=%s OR telefone2=%s", (valor,valor))
    row = cur.fetchone()
    cur.close(); conn.close()
    if row and (not cid or str(row['id']) != str(cid)):
        return jsonify({'ok': False})
    return jsonify({'ok': True})

@app.route('/clientes/<int:cid>')
@login_required
def ficha_cliente(cid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE id=%s", (cid,))
    c = cur.fetchone()
    cur.close(); conn.close()
    if not c:
        flash('Cliente não encontrado.', 'erro')
        return redirect(url_for('clientes'))
    partes = c['nome'].split()
    c['iniciais'] = (partes[0][0]+(partes[1][0] if len(partes)>1 else partes[0][1])).upper()
    return render_template('ficha_cliente.html', cliente=CLIENTE, c=c,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/clientes/<int:cid>/editar', methods=['GET','POST'])
@login_required
def editar_cliente(cid):
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        cpf = request.form.get('cpf','').strip()
        data_nascimento = request.form.get('data_nascimento') or None
        telefone = request.form.get('telefone','').strip()
        telefone2 = request.form.get('telefone2','').strip()
        cep = request.form.get('cep','').strip()
        logradouro = request.form.get('logradouro','').strip()
        numero = request.form.get('numero','').strip()
        complemento = request.form.get('complemento','').strip()
        bairro = request.form.get('bairro','').strip()
        cidade = request.form.get('cidade','').strip()
        uf = request.form.get('uf','').strip()
        promocoes = request.form.get('promocoes','0') == '1'
        crediario_hab = request.form.get('crediario','0') == '1'
        cur.execute("""UPDATE clientes SET nome=%s,cpf=%s,data_nascimento=%s,telefone=%s,telefone2=%s,
                       cep=%s,logradouro=%s,numero=%s,complemento=%s,bairro=%s,cidade=%s,uf=%s,
                       promocoes=%s,crediario=%s WHERE id=%s""",
                    (nome,cpf or None,data_nascimento,telefone or None,telefone2 or None,
                     cep or None,logradouro or None,numero or None,complemento or None,
                     bairro or None,cidade or None,uf or None,promocoes,crediario_hab,cid))
        conn.commit()
        cur.close(); conn.close()
        flash('✅ Cliente atualizado!', 'ok')
        return redirect(url_for('ficha_cliente', cid=cid))
    cur.execute("SELECT * FROM clientes WHERE id=%s", (cid,))
    c = cur.fetchone()
    cur.close(); conn.close()
    return render_template('editar_cliente.html', cliente=CLIENTE, c=c,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/clientes/<int:cid>/excluir', methods=['POST'])
@login_required
def excluir_cliente(cid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
    conn.commit()
    cur.close(); conn.close()
    flash('✅ Cliente excluído.', 'ok')
    return redirect(url_for('clientes'))

# ─── ESTOQUE ───
@app.route('/estoque')
@login_required
def estoque():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM estoque WHERE ativo=TRUE ORDER BY criado_em ASC")
    itens = [dict(i) for i in cur.fetchall()]
    cur.execute("SELECT COALESCE(SUM(custo_unitario*quantidade),0) as ct, COALESCE(SUM(valor_venda*quantidade),0) as vt FROM estoque WHERE ativo=TRUE")
    totais = cur.fetchone()
    cur.execute("SELECT nome FROM modelos_estoque ORDER BY nome")
    modelos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT nome FROM tamanhos_estoque ORDER BY id")
    tamanhos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) as total FROM estoque")
    total = cur.fetchone()['total']
    cur.close(); conn.close()
    hoje = datetime.now().date()
    for item in itens:
        item['dias_estoque'] = (hoje - item['criado_em'].date()).days
        item['saidas'] = (item['estoque_inicial'] or item['quantidade']) - item['quantidade']
    lucro_potencial = float(totais['vt']) - float(totais['ct'])
    next_codigo = f"P{total+1}"
    return render_template('estoque.html', cliente=CLIENTE, itens=itens,
                           custo_total=totais['ct'], valor_total=totais['vt'],
                           lucro_potencial=lucro_potencial, modelos=modelos,
                           tamanhos=tamanhos, next_ref=next_codigo,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/estoque/novo', methods=['POST'])
@login_required
def novo_estoque():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total FROM estoque")
    total = cur.fetchone()['total']
    codigo = f"P{total+1}"
    modelo = request.form.get('modelo','').strip()
    descricao = request.form.get('descricao','').strip()
    tamanho = request.form.get('tamanho','').strip()
    quantidade = int(request.form.get('quantidade',1) or 1)
    custo = float(request.form.get('custo_unitario',0) or 0)
    markup = float(request.form.get('markup',0) or 0)
    venda = float(request.form.get('valor_venda',0) or 0)
    margem = float(request.form.get('margem_lucro',0) or 0)
    try:
        cur.execute("""INSERT INTO estoque (codigo,modelo,descricao,tamanho,quantidade,estoque_inicial,
                       custo_unitario,markup,valor_venda,margem_lucro)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (codigo,modelo,descricao or None,tamanho,quantidade,quantidade,
                     custo,markup,venda,margem))
        conn.commit()
        flash('✅ Produto cadastrado!', 'ok')
    except Exception as e:
        flash(f'Erro: {e}', 'erro')
    finally:
        cur.close(); conn.close()
    return redirect(url_for('estoque'))

@app.route('/estoque/modelo/novo', methods=['POST'])
@login_required
def novo_modelo():
    nome = request.form.get('nome','').strip()
    if nome:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO modelos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (nome,))
        conn.commit()
        cur.close(); conn.close()
    return redirect(url_for('estoque'))

@app.route('/estoque/tamanho/novo', methods=['POST'])
@login_required
def novo_tamanho():
    nome = request.form.get('nome','').strip()
    if nome:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO tamanhos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (nome,))
        conn.commit()
        cur.close(); conn.close()
    return redirect(url_for('estoque'))

@app.route('/estoque/etiquetas')
@login_required
def etiquetas():
    data = request.args.get('data', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT codigo,modelo,tamanho,valor_venda,quantidade FROM estoque WHERE DATE(criado_em)=%s AND ativo=TRUE ORDER BY id", (data,))
    itens = [dict(i) for i in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'itens': itens, 'data': data})

@app.route('/estoque/<int:eid>')
@login_required
def ficha_estoque(eid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM estoque WHERE id=%s", (eid,))
    item = dict(cur.fetchone())
    cur.close(); conn.close()
    hoje = datetime.now().date()
    item['dias_estoque'] = (hoje - item['criado_em'].date()).days
    item['saidas'] = (item['estoque_inicial'] or item['quantidade']) - item['quantidade']
    return render_template('ficha_estoque.html', cliente=CLIENTE, item=item,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/estoque/<int:eid>/editar', methods=['GET','POST'])
@login_required
def editar_estoque(eid):
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'POST':
        modelo = request.form.get('modelo','').strip()
        descricao = request.form.get('descricao','').strip()
        tamanho = request.form.get('tamanho','').strip()
        quantidade = int(request.form.get('quantidade',1) or 1)
        custo = float(request.form.get('custo_unitario',0) or 0)
        markup = float(request.form.get('markup',0) or 0)
        venda = float(request.form.get('valor_venda',0) or 0)
        margem = float(request.form.get('margem_lucro',0) or 0)
        cur.execute("""UPDATE estoque SET modelo=%s,descricao=%s,tamanho=%s,quantidade=%s,
                       custo_unitario=%s,markup=%s,valor_venda=%s,margem_lucro=%s WHERE id=%s""",
                    (modelo,descricao or None,tamanho,quantidade,custo,markup,venda,margem,eid))
        conn.commit()
        cur.close(); conn.close()
        flash('✅ Produto atualizado!', 'ok')
        return redirect(url_for('ficha_estoque', eid=eid))
    cur.execute("SELECT * FROM estoque WHERE id=%s", (eid,))
    item = cur.fetchone()
    cur.execute("SELECT nome FROM modelos_estoque ORDER BY nome")
    modelos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT nome FROM tamanhos_estoque ORDER BY id")
    tamanhos = [r['nome'] for r in cur.fetchall()]
    cur.close(); conn.close()
    return render_template('editar_estoque.html', cliente=CLIENTE, item=item,
                           modelos=modelos, tamanhos=tamanhos,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/estoque/<int:eid>/excluir', methods=['POST'])
@login_required
def excluir_estoque(eid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM estoque WHERE id=%s", (eid,))
    conn.commit()
    cur.close(); conn.close()
    flash('✅ Produto excluído.', 'ok')
    return redirect(url_for('estoque'))

# ─── VENDAS ───
@app.route('/vendas')
@login_required
def vendas():
    import traceback
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE ativo=TRUE ORDER BY nome")
        vendedoras = cur.fetchall()
        cur.execute("SELECT id,codigo,nome,crediario FROM clientes WHERE ativo=TRUE ORDER BY nome")
        clientes_lista = cur.fetchall()
        cur.execute("""SELECT v.*, COUNT(vi.id) as qtd_itens FROM vendas v
                       LEFT JOIN venda_itens vi ON vi.venda_id=v.id
                       GROUP BY v.id ORDER BY v.criado_em DESC""")
        lista_vendas = [dict(v) for v in cur.fetchall()]
        cur.execute("""SELECT c.*, v.criado_em as data_venda FROM crediarios c
                       JOIN vendas v ON v.id=c.venda_id ORDER BY c.criado_em DESC""")
        lista_crediarios = [dict(c) for c in cur.fetchall()]
        mes_ini = datetime.now().replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        cur.execute("""SELECT vendedora_nome, COALESCE(SUM(valor_total),0) as total,
                       COUNT(id) as num_vendas, COUNT(DISTINCT cliente_id) as clientes
                       FROM vendas WHERE criado_em>=%s GROUP BY vendedora_nome ORDER BY total DESC""", (mes_ini,))
        ranking = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT DATE_TRUNC('month',criado_em) as mes FROM vendas ORDER BY mes DESC")
        meses_raw = cur.fetchall()
        cur.close(); conn.close()
        now_mes = datetime.now().strftime('%Y-%m')
        now_mes_label = datetime.now().strftime('%B / %Y').capitalize()
        meses = [{'mes_val': m['mes'].strftime('%Y-%m'), 'mes_label': m['mes'].strftime('%B / %Y').capitalize()} for m in meses_raw]
        return render_template('vendas.html', cliente=CLIENTE,
                               vendedoras=vendedoras, clientes=clientes_lista,
                               lista_vendas=lista_vendas, lista_crediarios=lista_crediarios,
                               ranking=ranking, meses=meses,
                               now_mes=now_mes, now_mes_label=now_mes_label,
                               nome=session.get('nome'), perfil=session.get('perfil'))
    except Exception as e:
        print(f"ERRO VENDAS: {e}")
        print(traceback.format_exc())
        return f"<pre style='padding:20px'>ERRO: {e}\n\n{traceback.format_exc()}</pre>", 500

@app.route('/vendas/nova', methods=['POST'])
@login_required
def nova_venda():
    conn = get_db()
    cur = conn.cursor()
    try:
        vendedora_id = request.form.get('usuario_id') or request.form.get('vendedora_id')
        vendedora_nome = request.form.get('vendedora_nome','').strip()
        cliente_id = request.form.get('cliente_id')
        cliente_nome = request.form.get('cliente_nome','').strip()
        forma_pagamento = request.form.get('forma_pagamento','').strip()
        parcelas = int(request.form.get('parcelas',1) or 1)
        valor_total = float(request.form.get('valor_total',0) or 0)
        itens = json.loads(request.form.get('itens','[]'))
        # Gerar código V1, V2...
        cur.execute("SELECT COUNT(*) as total FROM vendas")
        total = cur.fetchone()['total']
        codigo_venda = f"V{total+1}"
        cur.execute("""INSERT INTO vendas (codigo,usuario_id,vendedora_nome,cliente_id,cliente_nome,
                       valor_total,forma_pagamento,parcelas)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (codigo_venda, vendedora_id or None, vendedora_nome,
                     cliente_id or None, cliente_nome, valor_total, forma_pagamento, parcelas))
        venda_id = cur.fetchone()['id']
        # Inserir itens e dar baixa no estoque
        for item in itens:
            produto_id = item.get('produto_id') or item.get('estoque_id')
            qtd = int(item.get('quantidade',1))
            val_unit = float(item.get('valor_unitario',0))
            cur.execute("""INSERT INTO venda_itens (venda_id,produto_id,codigo_produto,modelo,descricao,
                           tamanho,valor_unitario,quantidade,valor_total)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (venda_id, produto_id or None, item.get('codigo'),
                         item.get('modelo'), item.get('descricao'), item.get('tamanho'),
                         val_unit, qtd, val_unit*qtd))
            if produto_id:
                cur.execute("UPDATE estoque SET quantidade=quantidade-%s, ultima_venda=CURRENT_DATE WHERE id=%s",
                            (qtd, produto_id))
        # Crediário
        if forma_pagamento == 'crediario':
            entrada = float(request.form.get('entrada',0) or 0)
            saldo = valor_total - entrada
            cur.execute("""INSERT INTO crediarios (venda_id,cliente_id,cliente_nome,valor_total,entrada,saldo_devedor)
                           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (venda_id, cliente_id or None, cliente_nome, valor_total, entrada, saldo))
            crediario_id = cur.fetchone()['id']
            parcelas_list = json.loads(request.form.get('parcelas_datas','[]'))
            for i, p in enumerate(parcelas_list):
                cur.execute("""INSERT INTO crediario_parcelas (crediario_id,numero_parcela,data_vencimento,valor)
                               VALUES (%s,%s,%s,%s)""",
                            (crediario_id, i+1, p.get('data'), float(p.get('valor',0))))
        # Registrar no caixa
        cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,vendedora_nome)
                       VALUES (%s,%s,'entrada',%s,%s,%s)""",
                    (f"Venda {codigo_venda} - {cliente_nome}", valor_total, forma_pagamento, venda_id, vendedora_nome))
        conn.commit()
        flash('✅ Venda registrada com sucesso!', 'ok')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao registrar venda: {e}', 'erro')
    finally:
        cur.close(); conn.close()
    return redirect(url_for('vendas'))

@app.route('/vendas/<int:vid>')
@login_required
def ficha_venda(vid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM vendas WHERE id=%s", (vid,))
    venda = dict(cur.fetchone())
    cur.execute("SELECT * FROM venda_itens WHERE venda_id=%s", (vid,))
    itens = cur.fetchall()
    crediario = None
    if venda.get('forma_pagamento') == 'crediario':
        cur.execute("SELECT * FROM crediarios WHERE venda_id=%s", (vid,))
        c = cur.fetchone()
        if c:
            crediario = dict(c)
            cur.execute("SELECT * FROM crediario_parcelas WHERE crediario_id=%s ORDER BY numero_parcela", (crediario['id'],))
            crediario['parcelas'] = cur.fetchall()
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = cur.fetchall()
    cur.close(); conn.close()
    return render_template('ficha_venda.html', cliente=CLIENTE, venda=venda,
                           itens=itens, crediario=crediario, vendedoras=vendedoras,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/vendas/<int:vid>/excluir', methods=['POST'])
@login_required
def excluir_venda(vid):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM venda_itens WHERE venda_id=%s", (vid,))
        itens = cur.fetchall()
        for item in itens:
            if item['produto_id']:
                cur.execute("UPDATE estoque SET quantidade=quantidade+%s WHERE id=%s",
                            (item['quantidade'], item['produto_id']))
        cur.execute("DELETE FROM vendas WHERE id=%s", (vid,))
        conn.commit()
        flash('✅ Venda excluída e estoque restaurado.', 'ok')
    except Exception as e:
        conn.rollback()
        flash(f'Erro: {e}', 'erro')
    finally:
        cur.close(); conn.close()
    return redirect(url_for('vendas'))

@app.route('/vendas/ranking')
@login_required
def ranking_vendedoras():
    mes = request.args.get('mes', datetime.now().strftime('%Y-%m'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""SELECT vendedora_nome, COALESCE(SUM(valor_total),0) as total,
                   COUNT(id) as num_vendas, COUNT(DISTINCT cliente_id) as clientes
                   FROM vendas WHERE TO_CHAR(criado_em,'YYYY-MM')=%s
                   GROUP BY vendedora_nome ORDER BY total DESC""", (mes,))
    ranking = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'ranking': ranking})

@app.route('/vendas/buscar-ref')
@login_required
def buscar_ref_venda():
    ref = request.args.get('ref','').strip().upper()
    conn = get_db()
    cur = conn.cursor()
    # Buscar por código exato (P1, P2...) ou por número
    cur.execute("""SELECT id as produto_id, codigo, modelo, descricao, tamanho, valor_venda, quantidade
                   FROM estoque WHERE (codigo=%s OR codigo=%s) AND ativo=TRUE AND quantidade>0""",
                (ref, f"P{ref}" if ref.isdigit() else ref))
    item = cur.fetchone()
    cur.close(); conn.close()
    if item:
        return jsonify({'ok': True, 'item': dict(item)})
    return jsonify({'ok': False})

@app.route('/vendas/buscar-cliente')
@login_required
def buscar_cliente_venda():
    q = request.args.get('q','').strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""SELECT id, codigo, nome, crediario FROM clientes
                   WHERE ativo=TRUE AND (LOWER(nome) LIKE %s OR codigo ILIKE %s)
                   ORDER BY nome LIMIT 8""", (f'%{q.lower()}%', f'%{q}%'))
    clientes = [dict(c) for c in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'clientes': clientes})

@app.route('/crediarios/<int:cid>/parcela/<int:pid>/pagar', methods=['POST'])
@login_required
def pagar_parcela(cid, pid):
    import math
    vendedora_nome = request.form.get('vendedora_nome','').strip()
    valor_pago = float(request.form.get('valor_pago',0) or 0)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM crediarios WHERE id=%s", (cid,))
        crediario = dict(cur.fetchone())
        cur.execute("UPDATE crediario_parcelas SET pago=TRUE, valor=%s, data_pagamento=CURRENT_DATE WHERE id=%s", (valor_pago, pid))
        novo_saldo = round(float(crediario['saldo_devedor']) - valor_pago, 2)
        if novo_saldo <= 0.01:
            cur.execute("DELETE FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE", (cid,))
            cur.execute("UPDATE crediarios SET saldo_devedor=0, status='quitado' WHERE id=%s", (cid,))
            status_msg = 'quitado'
        else:
            cur.execute("SELECT id FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE ORDER BY numero_parcela", (cid,))
            restantes = cur.fetchall()
            if restantes:
                val_por = math.ceil((novo_saldo/len(restantes))*100)/100
                for i, p in enumerate(restantes):
                    val = round(novo_saldo - val_por*(len(restantes)-1), 2) if i==len(restantes)-1 else val_por
                    cur.execute("UPDATE crediario_parcelas SET valor=%s WHERE id=%s", (val, p['id']))
            cur.execute("UPDATE crediarios SET saldo_devedor=%s WHERE id=%s", (novo_saldo, cid))
            status_msg = 'atualizado'
        cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,crediario_id,vendedora_nome)
                       VALUES (%s,%s,'entrada','crediario',%s,%s)""",
                    (f"Crediário - {crediario['cliente_nome']}", valor_pago, cid, vendedora_nome))
        conn.commit()
        flash(f'✅ Parcela registrada! Crediário {status_msg}.', 'ok')
    except Exception as e:
        conn.rollback()
        flash(f'Erro: {e}', 'erro')
    finally:
        cur.close(); conn.close()
    return redirect(url_for('ficha_venda', vid=crediario['venda_id']))

# ─── DASHBOARD (compatibilidade) ───
@app.route('/dashboard')
@login_required
def dashboard():
    return redirect(url_for('visao_geral'))

with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"Erro init_db: {e}")

if __name__ == '__main__':
    app.run(debug=False)
