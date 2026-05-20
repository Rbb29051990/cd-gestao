from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import random
from werkzeug.security import generate_password_hash, check_password_hash
import json

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cd-gestao-2026-secret')

DATABASE_URL = os.environ.get('DATABASE_URL')

CLIENTE = {
    'nome': 'CD Gestão Empresarial',
    'sigla': 'CD',
    'tagline': 'Elegância na gestão, precisão nos resultados.',
    'cor_primaria': '#0a0a0a',
    'cor_secundaria': '#f5f5f0',
    'cor_botao': '#0a0a0a',
}

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100) NOT NULL,
            usuario VARCHAR(50) UNIQUE NOT NULL,
            senha_hash VARCHAR(255) NOT NULL,
            perfil VARCHAR(20) DEFAULT 'vendedor',
            ativo BOOLEAN DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute("SELECT COUNT(*) as total FROM usuarios")
    result = cur.fetchone()
    if result['total'] == 0:
        cur.execute('''
            INSERT INTO usuarios (nome, usuario, senha_hash, perfil)
            VALUES (%s, %s, %s, %s)
        ''', ('Renan', 'renan', generate_password_hash('renan123'), 'admin'))
        cur.execute('''
            INSERT INTO usuarios (nome, usuario, senha_hash, perfil)
            VALUES (%s, %s, %s, %s)
        ''', ('Carol Duarte', 'carol', generate_password_hash('carol123'), 'admin'))
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(200) NOT NULL,
            cpf VARCHAR(20),
            data_nascimento DATE,
            telefone VARCHAR(30),
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
    ''')
    for col_def in ['cep VARCHAR(10)', 'logradouro VARCHAR(200)', 'numero VARCHAR(20)',
                    'complemento VARCHAR(100)', 'bairro VARCHAR(100)', 'cidade VARCHAR(100)', 'uf VARCHAR(2)', 'telefone2 VARCHAR(30)']:
        try:
            cur.execute(f'ALTER TABLE clientes ADD COLUMN IF NOT EXISTS {col_def}')
        except Exception:
            pass

    # Tabela modelos de estoque
    cur.execute('''
        CREATE TABLE IF NOT EXISTS modelos_estoque (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100) UNIQUE NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    for m in ['Vestido','Calça','Blusa','Bolsa','Saia','Macacão','Conjunto']:
        try:
            cur.execute("INSERT INTO modelos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (m,))
        except:
            pass

    # Tabela tamanhos de estoque
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tamanhos_estoque (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(20) UNIQUE NOT NULL
        )
    ''')
    for t in ['PP','P','M','G','GG','EG','EGG','36','38','40','42','44','46','48','50','52','54','56','58','60']:
        try:
            cur.execute("INSERT INTO tamanhos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (t,))
        except:
            pass

    # Tabela vendas
    cur.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id SERIAL PRIMARY KEY,
            vendedora_id INTEGER,
            vendedora_nome VARCHAR(200),
            cliente_id INTEGER,
            cliente_nome VARCHAR(200),
            valor_total NUMERIC(10,2),
            forma_pagamento VARCHAR(50),
            parcelas INTEGER,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS venda_itens (
            id SERIAL PRIMARY KEY,
            venda_id INTEGER REFERENCES vendas(id) ON DELETE CASCADE,
            estoque_id INTEGER,
            referencia VARCHAR(20),
            modelo VARCHAR(100),
            descricao TEXT,
            tamanho VARCHAR(20),
            valor_unitario NUMERIC(10,2),
            quantidade INTEGER DEFAULT 1,
            valor_total NUMERIC(10,2)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS crediarios (
            id SERIAL PRIMARY KEY,
            venda_id INTEGER REFERENCES vendas(id) ON DELETE CASCADE,
            cliente_id INTEGER,
            cliente_nome VARCHAR(200),
            valor_total NUMERIC(10,2),
            entrada NUMERIC(10,2) DEFAULT 0,
            saldo_devedor NUMERIC(10,2),
            status VARCHAR(20) DEFAULT 'aberto',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS crediario_parcelas (
            id SERIAL PRIMARY KEY,
            crediario_id INTEGER REFERENCES crediarios(id) ON DELETE CASCADE,
            numero_parcela INTEGER,
            data_vencimento DATE,
            valor NUMERIC(10,2),
            pago BOOLEAN DEFAULT FALSE,
            data_pagamento DATE
        )
    ''')

    # Tabela estoque
    cur.execute('''
        CREATE TABLE IF NOT EXISTS estoque (
            id SERIAL PRIMARY KEY,
            referencia VARCHAR(20) UNIQUE NOT NULL,
            modelo VARCHAR(100),
            descricao TEXT,
            tamanho VARCHAR(20),
            quantidade INTEGER DEFAULT 1,
            estoque_inicial INTEGER DEFAULT 1,
            custo_unitario NUMERIC(10,2),
            markup NUMERIC(10,2),
            valor_venda NUMERIC(10,2),
            margem_lucro NUMERIC(10,2),
            custo_total NUMERIC(10,2),
            valor_total NUMERIC(10,2),
            ativo BOOLEAN DEFAULT TRUE,
            ultima_venda DATE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cur.execute('ALTER TABLE estoque ADD COLUMN IF NOT EXISTS estoque_inicial INTEGER DEFAULT 1')
        cur.execute('UPDATE estoque SET estoque_inicial=quantidade WHERE estoque_inicial IS NULL OR estoque_inicial=1')
    except:
        pass
    cur.execute('''
        CREATE TABLE IF NOT EXISTS caixa (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor NUMERIC(10,2),
            tipo VARCHAR(20) DEFAULT 'entrada',
            forma_pagamento VARCHAR(50),
            crediario_id INTEGER,
            vendedora_nome VARCHAR(200),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
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

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('perfil') != 'admin':
            flash('Acesso restrito a administradores.', 'erro')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', cliente=CLIENTE)

@app.route('/login', methods=['POST'])
def login():
    usuario = request.form.get('usuario', '').strip().lower()
    senha = request.form.get('senha', '')
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE usuario = %s AND ativo = TRUE", (usuario,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and check_password_hash(user['senha_hash'], senha):
            session['usuario_id'] = user['id']
            session['nome'] = user['nome']
            session['usuario'] = user['usuario']
            session['perfil'] = user['perfil']
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Erro login: {e}")
    return render_template('login.html', cliente=CLIENTE, erro='Usuário ou senha incorretos.')

@app.route('/dashboard')
@login_required
def dashboard():
    return redirect(url_for('visao_geral'))

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
        cur.execute("SELECT COALESCE(SUM(valor_total),0) as total FROM vendas WHERE forma_pagamento=%s AND criado_em >= %s", (f, mes_ini))
        fat[f] = float(cur.fetchone()['total'])
    fat_total = sum(fat.values())

    cur.execute("SELECT COALESCE(SUM(valor_total),0) as vt FROM estoque WHERE ativo=TRUE")
    valor_estoque = float(cur.fetchone()['vt'])

    cur.execute("SELECT COALESCE(SUM(saldo_devedor),0) as total FROM crediarios WHERE status='aberto'")
    crediarios_total = float(cur.fetchone()['total'])

    cur.execute(
        "SELECT v.id, v.criado_em, v.vendedora_nome, v.cliente_nome, v.valor_total, v.forma_pagamento "
        "FROM vendas v ORDER BY v.criado_em DESC LIMIT 10"
    )
    movimentacoes = cur.fetchall()
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
    hoje = datetime.now().strftime('%d de %B de %Y')
    meses = {'January':'Janeiro','February':'Fevereiro','March':'Março','April':'Abril',
             'May':'Maio','June':'Junho','July':'Julho','August':'Agosto',
             'September':'Setembro','October':'Outubro','November':'Novembro','December':'Dezembro'}
    for en, pt in meses.items():
        hoje = hoje.replace(en, pt)
    dias = {'Monday':'Segunda-feira','Tuesday':'Terça-feira','Wednesday':'Quarta-feira',
            'Thursday':'Quinta-feira','Friday':'Sexta-feira','Saturday':'Sábado','Sunday':'Domingo'}
    dia_semana = datetime.now().strftime('%A')
    hoje = dias.get(dia_semana, '') + ', ' + hoje
    meses = {'January':'Janeiro','February':'Fevereiro','March':'Março','April':'Abril',
             'May':'Maio','June':'Junho','July':'Julho','August':'Agosto',
             'September':'Setembro','October':'Outubro','November':'Novembro','December':'Dezembro'}
    mes_atual = datetime.now().strftime('%B / %Y')
    for en, pt in meses.items():
        mes_atual = mes_atual.replace(en, pt)
    return render_template('visao_geral.html', cliente=CLIENTE, hoje=hoje, mes_atual=mes_atual,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/usuarios')
@login_required
@admin_required
def usuarios():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, nome, usuario, perfil, ativo, criado_em FROM usuarios ORDER BY nome")
    lista = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('usuarios.html', cliente=CLIENTE, usuarios=lista,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def novo_usuario():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        usuario = request.form.get('usuario', '').strip().lower()
        senha = request.form.get('senha', '')
        perfil = request.form.get('perfil', 'vendedor')
        if not nome or not usuario or not senha:
            return render_template('usuario_form.html', cliente=CLIENTE, erro='Preencha todos os campos.',
                                   nome=session.get('nome'), perfil=session.get('perfil'))
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO usuarios (nome, usuario, senha_hash, perfil)
                VALUES (%s, %s, %s, %s)
            ''', (nome, usuario, generate_password_hash(senha), perfil))
            conn.commit()
            cur.close()
            conn.close()
            flash('Usuário criado com sucesso!', 'ok')
            return redirect(url_for('usuarios'))
        except Exception as e:
            flash(f'Esse nome de usuário já existe.', 'erro')
    return render_template('usuario_form.html', cliente=CLIENTE,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/usuarios/<int:uid>/senha', methods=['GET', 'POST'])
@login_required
@admin_required
def redefinir_senha(uid):
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha', '')
        confirmar = request.form.get('confirmar_senha', '')
        if not nova_senha or len(nova_senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'erro')
        elif nova_senha != confirmar:
            flash('As senhas não coincidem.', 'erro')
        else:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE usuarios SET senha_hash = %s WHERE id = %s",
                        (generate_password_hash(nova_senha), uid))
            conn.commit()
            cur.close()
            conn.close()
            flash('Senha redefinida com sucesso!', 'ok')
            return redirect(url_for('usuarios'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT nome, usuario FROM usuarios WHERE id = %s", (uid,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('redefinir_senha.html', cliente=CLIENTE, user=user, uid=uid,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/usuarios/<int:uid>/toggle')
@login_required
@admin_required
def toggle_usuario(uid):
    if uid == session.get('usuario_id'):
        flash('Você não pode desativar sua própria conta.', 'erro')
        return redirect(url_for('usuarios'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE usuarios SET ativo = NOT ativo WHERE id = %s", (uid,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Status do usuário atualizado.', 'ok')
    return redirect(url_for('usuarios'))

@app.route('/minha-senha', methods=['GET', 'POST'])
@login_required
def minha_senha():
    if request.method == 'POST':
        senha_atual = request.form.get('senha_atual', '')
        nova_senha = request.form.get('nova_senha', '')
        confirmar = request.form.get('confirmar_senha', '')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT senha_hash FROM usuarios WHERE id = %s", (session['usuario_id'],))
        user = cur.fetchone()
        if not check_password_hash(user['senha_hash'], senha_atual):
            flash('Senha atual incorreta.', 'erro')
        elif len(nova_senha) < 6:
            flash('A nova senha deve ter pelo menos 6 caracteres.', 'erro')
        elif nova_senha != confirmar:
            flash('As senhas não coincidem.', 'erro')
        else:
            cur.execute("UPDATE usuarios SET senha_hash = %s WHERE id = %s",
                        (generate_password_hash(nova_senha), session['usuario_id']))
            conn.commit()
            flash('Senha alterada com sucesso!', 'ok')
        cur.close()
        conn.close()
    return render_template('minha_senha.html', cliente=CLIENTE,
                           nome=session.get('nome'), perfil=session.get('perfil'))


@app.route('/usuarios/<int:uid>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_usuario(uid):
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        usuario = request.form.get('usuario', '').strip().lower()
        perfil = request.form.get('perfil', 'vendedor')
        nova_senha = request.form.get('nova_senha', '')
        confirmar = request.form.get('confirmar_senha', '')
        if not nome or not usuario:
            flash('Nome e usuário são obrigatórios.', 'erro')
        elif nova_senha and len(nova_senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'erro')
        elif nova_senha and nova_senha != confirmar:
            flash('As senhas não coincidem.', 'erro')
        else:
            try:
                if nova_senha:
                    cur.execute("""UPDATE usuarios SET nome=%s, usuario=%s, perfil=%s, senha_hash=%s WHERE id=%s""",
                                (nome, usuario, perfil, generate_password_hash(nova_senha), uid))
                else:
                    cur.execute("UPDATE usuarios SET nome=%s, usuario=%s, perfil=%s WHERE id=%s",
                                (nome, usuario, perfil, uid))
                conn.commit()
                flash('Usuário atualizado com sucesso!', 'ok')
                cur.close()
                conn.close()
                return redirect(url_for('usuarios'))
            except Exception as e:
                flash('Esse nome de usuário já existe.', 'erro')
    cur.execute("SELECT id, nome, usuario, perfil FROM usuarios WHERE id=%s", (uid,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('usuario_editar.html', cliente=CLIENTE, user=user, uid=uid,
                           nome=session.get('nome'), perfil=session.get('perfil'))


@app.route('/clientes')
@login_required
def clientes():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE ativo = TRUE ORDER BY nome")
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) as total FROM clientes WHERE ativo = TRUE")
    total = cur.fetchone()['total']
    cur.close()
    conn.close()
    next_id = total + 1
    for r in rows:
        partes = r['nome'].split()
        r['iniciais'] = (partes[0][0] + (partes[1][0] if len(partes) > 1 else partes[0][1])).upper()
    return render_template('clientes.html', cliente=CLIENTE, clientes=rows, next_id=next_id,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/clientes/novo', methods=['POST'])
@login_required
def novo_cliente():
    import random
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

    # 1º BLOQUEIO — Nome duplicado
    cur.execute("SELECT id FROM clientes WHERE LOWER(TRIM(nome)) = LOWER(TRIM(%s))", (nome,))
    if cur.fetchone():
        cur.close(); conn.close()
        flash(f'DUPLICADO_NOME||{nome}', 'erro')
        return redirect(url_for('clientes'))

    # 2º BLOQUEIO — CPF duplicado
    if cpf:
        cur.execute("SELECT id FROM clientes WHERE cpf = %s", (cpf,))
        if cur.fetchone():
            cur.close(); conn.close()
            flash(f'DUPLICADO_CPF||{cpf}', 'erro')
            return redirect(url_for('clientes'))

    # 3º BLOQUEIO — Telefone duplicado
    if telefone:
        cur.execute("SELECT id FROM clientes WHERE telefone = %s OR telefone2 = %s", (telefone, telefone))
        if cur.fetchone():
            cur.close(); conn.close()
            flash(f'DUPLICADO_TEL||{telefone}', 'erro')
            return redirect(url_for('clientes'))
    if telefone2:
        cur.execute("SELECT id FROM clientes WHERE telefone = %s OR telefone2 = %s", (telefone2, telefone2))
        if cur.fetchone():
            cur.close(); conn.close()
            flash(f'DUPLICADO_TEL||{telefone2}', 'erro')
            return redirect(url_for('clientes'))

    try:
        cor = random.choice(cores)
        cur.execute("""INSERT INTO clientes (nome,cpf,data_nascimento,telefone,telefone2,cep,logradouro,numero,complemento,bairro,cidade,uf,promocoes,crediario,cor_avatar)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (nome, cpf or None, data_nascimento, telefone or None, telefone2 or None,
                     cep or None, logradouro or None, numero or None, complemento or None,
                     bairro or None, cidade or None, uf or None, promocoes, crediario, cor))
        conn.commit()
        flash('SUCESSO||Cliente cadastrado com sucesso!', 'ok')
    except Exception as e:
        flash(f'Erro ao cadastrar: {e}', 'erro')
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('clientes'))
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""INSERT INTO clientes (nome,cpf,data_nascimento,telefone,cep,logradouro,numero,complemento,bairro,cidade,uf,promocoes,crediario,cor_avatar)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (nome,cpf or None,data_nascimento,telefone or None,cep or None,logradouro or None,numero or None,complemento or None,bairro or None,cidade or None,uf or None,promocoes,crediario,cor))
        # salvar telefone2 se houver
        telefone2 = request.form.get('telefone2','').strip()
        if telefone2:
            cur.execute('UPDATE clientes SET telefone2=%s WHERE id=(SELECT MAX(id) FROM clientes)', (telefone2,))
        conn.commit()
        cur.close()
        conn.close()
        flash('Cliente cadastrado com sucesso!', 'ok')
    except Exception as e:
        flash(f'Erro ao cadastrar cliente: {e}', 'erro')
    return redirect(url_for('clientes'))

@app.route('/clientes/<int:cid>')
@login_required
def ficha_cliente(cid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE id = %s", (cid,))
    c = cur.fetchone()
    cur.close()
    conn.close()
    if not c:
        flash('Cliente não encontrado.', 'erro')
        return redirect(url_for('clientes'))
    partes = c['nome'].split()
    c['iniciais'] = (partes[0][0] + (partes[1][0] if len(partes) > 1 else partes[0][1])).upper()
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
        cep = request.form.get('cep','').strip()
        logradouro = request.form.get('logradouro','').strip()
        numero = request.form.get('numero','').strip()
        complemento = request.form.get('complemento','').strip()
        bairro = request.form.get('bairro','').strip()
        cidade = request.form.get('cidade','').strip()
        uf = request.form.get('uf','').strip()
        promocoes = request.form.get('promocoes','0') == '1'
        crediario = request.form.get('crediario','0') == '1'
        cur.execute("""UPDATE clientes SET nome=%s,cpf=%s,data_nascimento=%s,telefone=%s,
                       cep=%s,logradouro=%s,numero=%s,complemento=%s,bairro=%s,cidade=%s,uf=%s,
                       promocoes=%s,crediario=%s WHERE id=%s""",
                    (nome,cpf or None,data_nascimento,telefone or None,cep or None,logradouro or None,
                     numero or None,complemento or None,bairro or None,cidade or None,uf or None,
                     promocoes,crediario,cid))
        conn.commit()
        cur.close()
        conn.close()
        flash('Cliente atualizado com sucesso!', 'ok')
        return redirect(url_for('ficha_cliente', cid=cid))
    cur.execute("SELECT * FROM clientes WHERE id = %s", (cid,))
    c = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('editar_cliente.html', cliente=CLIENTE, c=c,
                           nome=session.get('nome'), perfil=session.get('perfil'))


@app.route('/clientes/<int:cid>/excluir', methods=['POST'])
@login_required
def excluir_cliente(cid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM clientes WHERE id = %s", (cid,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Cliente excluído com sucesso.', 'ok')
    return redirect(url_for('clientes'))

@app.route('/clientes/verificar')
@login_required
def verificar_cliente():
    campo = request.args.get('campo')
    valor = request.args.get('valor','').strip()
    cid = request.args.get('id', None)
    if not campo or not valor:
        return {'ok': True}
    conn = get_db()
    cur = conn.cursor()
    if campo == 'nome':
        cur.execute("SELECT id FROM clientes WHERE LOWER(nome) = LOWER(%s)", (valor,))
    elif campo == 'cpf':
        cur.execute("SELECT id FROM clientes WHERE cpf = %s", (valor,))
    elif campo == 'telefone':
        cur.execute("SELECT id FROM clientes WHERE telefone = %s OR telefone2 = %s", (valor, valor))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        if cid and str(row['id']) == str(cid):
            return {'ok': True}
        return {'ok': False}
    return {'ok': True}


@app.route('/estoque')
@login_required
def estoque():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM estoque WHERE ativo = TRUE ORDER BY criado_em ASC")
    itens = cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(custo_total),0) as ct, COALESCE(SUM(valor_total),0) as vt FROM estoque WHERE ativo=TRUE")
    totais = cur.fetchone()
    cur.execute("SELECT nome FROM modelos_estoque ORDER BY nome")
    modelos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT nome FROM tamanhos_estoque ORDER BY id")
    tamanhos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) as total FROM estoque WHERE ativo=TRUE")
    total = cur.fetchone()['total']
    cur.close()
    conn.close()
    hoje = datetime.now().date()
    for item in itens:
        delta = (hoje - item['criado_em'].date()).days
        item['dias_estoque'] = delta
        item['saidas'] = (item['estoque_inicial'] or item['quantidade']) - item['quantidade']
    lucro_potencial = float(totais['vt']) - float(totais['ct'])
    next_ref = f"REF.{total+1:04d}"
    return render_template('estoque.html', cliente=CLIENTE, itens=itens,
                           custo_total=totais['ct'], valor_total=totais['vt'],
                           lucro_potencial=lucro_potencial, modelos=modelos,
                           tamanhos=tamanhos, next_ref=next_ref,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/estoque/novo', methods=['POST'])
@login_required
def novo_estoque():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total FROM estoque")
    total = cur.fetchone()['total']
    referencia = f"REF.{total+1:04d}"
    modelo = request.form.get('modelo','').strip()
    descricao = request.form.get('descricao','').strip()
    tamanho = request.form.get('tamanho','').strip()
    quantidade = int(request.form.get('quantidade',1) or 1)
    custo = float(request.form.get('custo_unitario',0) or 0)
    markup = float(request.form.get('markup',0) or 0)
    venda = float(request.form.get('valor_venda',0) or 0)
    margem = float(request.form.get('margem_lucro',0) or 0)
    custo_total = custo * quantidade
    valor_total = venda * quantidade
    try:
        cur.execute("""INSERT INTO estoque (referencia,modelo,descricao,tamanho,quantidade,estoque_inicial,
                       custo_unitario,markup,valor_venda,margem_lucro,custo_total,valor_total)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (referencia,modelo,descricao or None,tamanho,quantidade,quantidade,
                     custo,markup,venda,margem,custo_total,valor_total))
        conn.commit()
        flash('✅ Item cadastrado com sucesso!', 'ok')
    except Exception as e:
        flash(f'Erro ao cadastrar: {e}', 'erro')
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('estoque'))

@app.route('/estoque/modelo/novo', methods=['POST'])
@login_required
def novo_modelo():
    nome = request.form.get('nome','').strip()
    if nome:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO modelos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (nome,))
            conn.commit()
        except:
            pass
        finally:
            cur.close()
            conn.close()
    return redirect(url_for('estoque'))

@app.route('/estoque/tamanho/novo', methods=['POST'])
@login_required
def novo_tamanho():
    nome = request.form.get('nome','').strip()
    if nome:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO tamanhos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (nome,))
            conn.commit()
        except:
            pass
        finally:
            cur.close()
            conn.close()
    return redirect(url_for('estoque'))

@app.route('/estoque/etiquetas')
@login_required
def etiquetas():
    data = request.args.get('data', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""SELECT referencia, modelo, tamanho, valor_venda, quantidade
                   FROM estoque WHERE DATE(criado_em) = %s AND ativo = TRUE
                   ORDER BY id""", (data,))
    itens = cur.fetchall()
    cur.close()
    conn.close()
    return {'itens': [dict(i) for i in itens], 'data': data}


@app.route('/estoque/<int:eid>')
@login_required
def ficha_estoque(eid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM estoque WHERE id = %s", (eid,))
    item = cur.fetchone()
    cur.close()
    conn.close()
    if not item:
        flash('Produto não encontrado.', 'erro')
        return redirect(url_for('estoque'))
    hoje = datetime.now().date()
    item['dias_estoque'] = (hoje - item['criado_em'].date()).days
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
        custo_total = custo * quantidade
        valor_total = venda * quantidade
        cur.execute("""UPDATE estoque SET modelo=%s,descricao=%s,tamanho=%s,quantidade=%s,
                       custo_unitario=%s,markup=%s,valor_venda=%s,margem_lucro=%s,
                       custo_total=%s,valor_total=%s WHERE id=%s""",
                    (modelo,descricao or None,tamanho,quantidade,custo,markup,venda,margem,custo_total,valor_total,eid))
        conn.commit()
        cur.close()
        conn.close()
        flash('✅ Produto atualizado com sucesso!', 'ok')
        return redirect(url_for('ficha_estoque', eid=eid))
    cur.execute("SELECT * FROM estoque WHERE id = %s", (eid,))
    item = cur.fetchone()
    cur.execute("SELECT nome FROM modelos_estoque ORDER BY nome")
    modelos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT nome FROM tamanhos_estoque ORDER BY id")
    tamanhos = [r['nome'] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return render_template('editar_estoque.html', cliente=CLIENTE, item=item,
                           modelos=modelos, tamanhos=tamanhos,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/estoque/<int:eid>/excluir', methods=['POST'])
@login_required
def excluir_estoque(eid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM estoque WHERE id = %s", (eid,))
    conn.commit()
    cur.close()
    conn.close()
    flash('✅ Produto excluído com sucesso.', 'ok')
    return redirect(url_for('estoque'))


@app.route('/vendas')
@login_required
def vendas():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = cur.fetchall()
    cur.execute("SELECT id, nome FROM clientes WHERE ativo=TRUE ORDER BY nome")
    clientes = cur.fetchall()
    cur.execute(
        "SELECT v.*, COUNT(vi.id) as qtd_itens FROM vendas v "
        "LEFT JOIN venda_itens vi ON vi.venda_id=v.id "
        "GROUP BY v.id ORDER BY v.criado_em DESC"
    )
    lista_vendas = cur.fetchall()
    # Crediários
    cur.execute(
        "SELECT c.*, v.criado_em as data_venda FROM crediarios c "
        "JOIN vendas v ON v.id=c.venda_id ORDER BY c.criado_em DESC"
    )
    lista_crediarios = cur.fetchall()
    # Ranking vendedoras (mês atual)
    mes_ini = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cur.execute(
        "SELECT vendedora_nome, COALESCE(SUM(valor_total),0) as total, COUNT(id) as num_vendas, "
        "COUNT(DISTINCT cliente_id) as clientes "
        "FROM vendas WHERE criado_em >= %s GROUP BY vendedora_nome ORDER BY total DESC", (mes_ini,)
    )
    ranking = cur.fetchall()
    # Meses disponíveis
    cur.execute("SELECT DISTINCT DATE_TRUNC('month', criado_em) as mes FROM vendas ORDER BY mes DESC")
    meses_raw = cur.fetchall()
    # Converter lista_vendas e lista_crediarios para dict editável
    lista_vendas = [dict(v) for v in lista_vendas]
    lista_crediarios = [dict(c) for c in lista_crediarios]
    ranking = [dict(r) for r in ranking]
    cur.close()
    conn.close()
    now_mes = datetime.now().strftime('%Y-%m')
    now_mes_label = datetime.now().strftime('%B / %Y').capitalize()
    # Formatar meses no Python para evitar problemas no Jinja2
    meses = [{'mes_val': m['mes'].strftime('%Y-%m'), 'mes_label': m['mes'].strftime('%B / %Y').capitalize()} for m in meses_raw]
    return render_template('vendas.html', cliente=CLIENTE,
                           vendedoras=vendedoras, clientes=clientes,
                           lista_vendas=lista_vendas, lista_crediarios=lista_crediarios,
                           ranking=ranking, meses=meses,
                           now_mes=now_mes, now_mes_label=now_mes_label,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/vendas/nova', methods=['POST'])
@login_required
def nova_venda():
    conn = get_db()
    cur = conn.cursor()
    try:
        vendedora_id = request.form.get('vendedora_id')
        vendedora_nome = request.form.get('vendedora_nome','').strip()
        cliente_id = request.form.get('cliente_id')
        cliente_nome = request.form.get('cliente_nome','').strip()
        forma_pagamento = request.form.get('forma_pagamento','').strip()
        parcelas = int(request.form.get('parcelas',1) or 1)
        valor_total = float(request.form.get('valor_total',0) or 0)
        itens_json = request.form.get('itens','[]')
        itens = json.loads(itens_json)

        # Inserir venda
        cur.execute(
            "INSERT INTO vendas (vendedora_id,vendedora_nome,cliente_id,cliente_nome,valor_total,forma_pagamento,parcelas) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (vendedora_id or None, vendedora_nome, cliente_id or None, cliente_nome, valor_total, forma_pagamento, parcelas)
        )
        venda_id = cur.fetchone()['id']

        # Inserir itens e dar baixa no estoque
        for item in itens:
            estoque_id = item.get('estoque_id')
            qtd = int(item.get('quantidade',1))
            val_unit = float(item.get('valor_unitario',0))
            cur.execute(
                "INSERT INTO venda_itens (venda_id,estoque_id,referencia,modelo,descricao,tamanho,valor_unitario,quantidade,valor_total) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (venda_id, estoque_id or None, item.get('referencia'), item.get('modelo'),
                 item.get('descricao'), item.get('tamanho'), val_unit, qtd, val_unit*qtd)
            )
            if estoque_id:
                cur.execute(
                    "UPDATE estoque SET quantidade=quantidade-%s, ultima_venda=CURRENT_DATE WHERE id=%s",
                    (qtd, estoque_id)
                )

        # Se crediário, inserir parcelas
        if forma_pagamento == 'crediario':
            entrada = float(request.form.get('entrada',0) or 0)
            saldo = valor_total - entrada
            cur.execute(
                "INSERT INTO crediarios (venda_id,cliente_id,cliente_nome,valor_total,entrada,saldo_devedor) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (venda_id, cliente_id or None, cliente_nome, valor_total, entrada, saldo)
            )
            crediario_id = cur.fetchone()['id']
            parcelas_json = request.form.get('parcelas_datas','[]')
            parcelas_list = json.loads(parcelas_json)
            for i, p in enumerate(parcelas_list):
                cur.execute(
                    "INSERT INTO crediario_parcelas (crediario_id,numero_parcela,data_vencimento,valor) VALUES (%s,%s,%s,%s)",
                    (crediario_id, i+1, p.get('data'), float(p.get('valor',0)))
                )

        conn.commit()
        flash('✅ Venda registrada com sucesso!', 'ok')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao registrar venda: {e}', 'erro')
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('vendas'))

@app.route('/vendas/<int:vid>')
@login_required
def ficha_venda(vid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM vendas WHERE id=%s", (vid,))
    venda = cur.fetchone()
    cur.execute("SELECT * FROM venda_itens WHERE venda_id=%s", (vid,))
    itens = cur.fetchall()
    crediario = None
    if venda and venda['forma_pagamento'] == 'crediario':
        cur.execute("SELECT * FROM crediarios WHERE venda_id=%s", (vid,))
        crediario = cur.fetchone()
        if crediario:
            crediario = dict(crediario)
            cur.execute("SELECT * FROM crediario_parcelas WHERE crediario_id=%s ORDER BY numero_parcela", (crediario['id'],))
            crediario['parcelas'] = cur.fetchall()
    cur.close()
    conn.close()
    if not venda:
        flash('Venda não encontrada.', 'erro')
        return redirect(url_for('vendas'))
    conn2 = get_db()
    cur2 = conn2.cursor()
    cur2.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = cur2.fetchall()
    cur2.close()
    conn2.close()
    return render_template('ficha_venda.html', cliente=CLIENTE, venda=venda,
                           itens=itens, crediario=crediario, vendedoras=vendedoras,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/vendas/ranking')
@login_required
def ranking_vendedoras():
    mes = request.args.get('mes', datetime.now().strftime('%Y-%m'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT vendedora_nome, COALESCE(SUM(valor_total),0) as total, "
        "COUNT(id) as num_vendas, COUNT(DISTINCT cliente_id) as clientes "
        "FROM vendas WHERE TO_CHAR(criado_em,'YYYY-MM')=%s "
        "GROUP BY vendedora_nome ORDER BY total DESC", (mes,)
    )
    ranking = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return {'ranking': ranking}

@app.route('/vendas/buscar-ref')
@login_required
def buscar_ref_venda():
    ref = request.args.get('ref','').strip().upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id,referencia,modelo,descricao,tamanho,valor_venda,quantidade FROM estoque WHERE referencia=%s AND ativo=TRUE", (ref,))
    item = cur.fetchone()
    cur.close()
    conn.close()
    if item:
        return {'ok': True, 'item': dict(item)}
    return {'ok': False}

@app.route('/vendas/buscar-cliente')
@login_required
def buscar_cliente_venda():
    q = request.args.get('q','').strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id,nome,crediario FROM clientes WHERE ativo=TRUE AND LOWER(nome) LIKE %s ORDER BY nome LIMIT 8", (f'%{q.lower()}%',))
    clientes = [dict(c) for c in cur.fetchall()]
    cur.close()
    conn.close()
    return {'clientes': clientes}


@app.route('/crediarios/<int:cid>/parcela/<int:pid>/pagar', methods=['POST'])
@login_required
def pagar_parcela(cid, pid):
    vendedora_nome = request.form.get('vendedora_nome','').strip()
    valor_pago = float(request.form.get('valor_pago', 0) or 0)
    conn = get_db()
    cur = conn.cursor()
    try:
        # Buscar parcela e crediário
        cur.execute("SELECT * FROM crediario_parcelas WHERE id=%s AND crediario_id=%s", (pid, cid))
        parcela = cur.fetchone()
        cur.execute("SELECT * FROM crediarios WHERE id=%s", (cid,))
        crediario = dict(cur.fetchone())

        # Marcar parcela como paga
        cur.execute("UPDATE crediario_parcelas SET pago=TRUE, valor=%s, data_pagamento=CURRENT_DATE WHERE id=%s", (valor_pago, pid))

        # Calcular novo saldo devedor
        novo_saldo = float(crediario['saldo_devedor']) - valor_pago

        if novo_saldo <= 0.01:
            # Quitado — dar baixa e excluir parcelas restantes
            cur.execute("DELETE FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE", (cid,))
            cur.execute("UPDATE crediarios SET saldo_devedor=0, status='quitado' WHERE id=%s", (cid,))
            status_msg = 'quitado'
        else:
            # Redistribuir saldo nas parcelas restantes
            cur.execute("SELECT id FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE ORDER BY numero_parcela", (cid,))
            restantes = cur.fetchall()
            if restantes:
                import math
                val_por_parcela = math.ceil((novo_saldo / len(restantes)) * 100) / 100
                for i, p in enumerate(restantes):
                    if i == len(restantes) - 1:
                        # Última parcela pega o restante exato
                        val_ultima = round(novo_saldo - val_por_parcela * (len(restantes)-1), 2)
                        cur.execute("UPDATE crediario_parcelas SET valor=%s WHERE id=%s", (val_ultima, p['id']))
                    else:
                        cur.execute("UPDATE crediario_parcelas SET valor=%s WHERE id=%s", (val_por_parcela, p['id']))
            cur.execute("UPDATE crediarios SET saldo_devedor=%s WHERE id=%s", (round(novo_saldo, 2), cid))
            status_msg = 'atualizado'

        # Registrar no caixa
        cur.execute("""
            INSERT INTO caixa (descricao, valor, tipo, forma_pagamento, crediario_id, vendedora_nome, criado_em)
            VALUES (%s, %s, 'entrada', 'crediario', %s, %s, CURRENT_TIMESTAMP)
        """, (f"Recebimento crediário — {crediario['cliente_nome']}", valor_pago, cid, vendedora_nome))

        conn.commit()
        flash(f'✅ Parcela registrada! Crediário {status_msg}.', 'ok')
    except Exception as e:
        conn.rollback()
        flash(f'Erro: {e}', 'erro')
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('ficha_venda', vid=crediario['venda_id']))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"Erro ao inicializar banco: {e}")

if __name__ == '__main__':
    app.run(debug=False)
