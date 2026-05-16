from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import random
from werkzeug.security import generate_password_hash, check_password_hash

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
