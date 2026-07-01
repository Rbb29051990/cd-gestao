"""Rotas de Clientes: listagem, cadastro, verificação de duplicidade, ficha,
edição e exclusão (exclusão só N1)."""
import random
from datetime import date
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from db import get_db, close_db
from config import CORES, hoje_app
from auth import login_required, get_ctx, pode_excluir
from utils import audit_log


@login_required
def clientes():
    conn = get_db(); cur = conn.cursor()
    hoje = hoje_app()
    # Período por data de CADASTRO do cliente — padrão: início do ano até hoje.
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-01-01'))
    data_fim = request.args.get('data_fim', hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except ValueError: data_inicio = hoje.strftime('%Y-01-01')
    try: date.fromisoformat(data_fim)
    except ValueError: data_fim = hoje.strftime('%Y-%m-%d')
    cur.execute("SELECT * FROM clientes WHERE ativo=TRUE AND DATE(criado_em) BETWEEN %s AND %s ORDER BY nome", (data_inicio, data_fim))
    lista = [dict(c) for c in cur.fetchall()]
    cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)), 0) as m FROM clientes WHERE codigo ~ '^C[0-9]+$'")
    n = cur.fetchone()['m']
    cur.close(); close_db(conn)
    for c in lista:
        p = c['nome'].split()
        c['iniciais'] = (p[0][0] + (p[1][0] if len(p) > 1 else p[0][-1])).upper()
    ctx = get_ctx(); ctx.update(clientes=lista, next_id=f"C{n+1}",
                                data_inicio=data_inicio, data_fim=data_fim)
    return render_template('clientes.html', **ctx)


@login_required
def novo_cliente():
    nome = request.form.get('nome', '').strip()
    if not nome: flash('Nome obrigatorio.', 'erro'); return redirect(url_for('clientes'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM clientes WHERE LOWER(TRIM(nome))=LOWER(TRIM(%s))", (nome,))
    if cur.fetchone():
        cur.close(); close_db(conn)
        flash('DUPLICADO_NOME||' + nome, 'erro'); return redirect(url_for('clientes'))
    cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)), 0) as m FROM clientes WHERE codigo ~ '^C[0-9]+$'")
    n = cur.fetchone()['m']
    try:
        cur.execute("""INSERT INTO clientes (codigo,nome,cpf,data_nascimento,telefone,telefone2,
            cep,logradouro,numero,complemento,bairro,cidade,uf,promocoes,crediario,cor_avatar,usuario_id,usuario_nome)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (f"C{n+1}", nome,
             request.form.get('cpf', '').strip() or None,
             request.form.get('data_nascimento') or None,
             request.form.get('telefone', '').strip() or None,
             request.form.get('telefone2', '').strip() or None,
             request.form.get('cep', '').strip() or None,
             request.form.get('logradouro', '').strip() or None,
             request.form.get('numero', '').strip() or None,
             request.form.get('complemento', '').strip() or None,
             request.form.get('bairro', '').strip() or None,
             request.form.get('cidade', '').strip() or None,
             request.form.get('uf', '').strip() or None,
             request.form.get('promocoes', '0') == '1',
             request.form.get('crediario', '0') == '1',
             random.choice(CORES),
             session.get('uid'), session.get('nome')))
        conn.commit(); flash('SUCESSO||Cliente cadastrado!', 'ok')
    except Exception as e: conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('clientes'))


@login_required
def criar_cliente_rapido():
    """Cadastra um cliente e devolve JSON — usado para cadastrar SEM sair da venda.
    Se já existir um cliente com o mesmo nome, devolve o existente (não duplica)."""
    nome = request.form.get('nome', '').strip()
    if not nome:
        return jsonify({'ok': False, 'erro': 'Informe o nome do cliente.'})
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT id,codigo,nome,crediario FROM clientes WHERE LOWER(TRIM(nome))=LOWER(TRIM(%s))", (nome,))
        ex = cur.fetchone()
        if ex:
            c = dict(ex)
            return jsonify({'ok': True, 'existente': True,
                            'cliente': {'id': c['id'], 'codigo': c['codigo'], 'nome': c['nome'], 'crediario': bool(c['crediario'])}})
        cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)), 0) as m FROM clientes WHERE codigo ~ '^C[0-9]+$'")
        n = cur.fetchone()['m']
        cur.execute("""INSERT INTO clientes (codigo,nome,cpf,data_nascimento,telefone,telefone2,
            cep,logradouro,numero,complemento,bairro,cidade,uf,promocoes,crediario,cor_avatar,usuario_id,usuario_nome)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id,codigo,nome,crediario""",
            (f"C{n+1}", nome,
             request.form.get('cpf', '').strip() or None,
             request.form.get('data_nascimento') or None,
             request.form.get('telefone', '').strip() or None,
             request.form.get('telefone2', '').strip() or None,
             request.form.get('cep', '').strip() or None,
             request.form.get('logradouro', '').strip() or None,
             request.form.get('numero', '').strip() or None,
             request.form.get('complemento', '').strip() or None,
             request.form.get('bairro', '').strip() or None,
             request.form.get('cidade', '').strip() or None,
             request.form.get('uf', '').strip() or None,
             request.form.get('promocoes', '0') == '1',
             request.form.get('crediario', '0') == '1',
             random.choice(CORES),
             session.get('uid'), session.get('nome')))
        row = dict(cur.fetchone())
        conn.commit()
        return jsonify({'ok': True, 'cliente': {'id': row['id'], 'codigo': row['codigo'],
                                                'nome': row['nome'], 'crediario': bool(row['crediario'])}})
    except Exception as e:
        conn.rollback()
        return jsonify({'ok': False, 'erro': str(e)})
    finally:
        cur.close(); close_db(conn)


@login_required
def verificar_cliente():
    campo = request.args.get('campo'); valor = request.args.get('valor', '').strip()
    if not campo or not valor: return jsonify({'ok': True})
    conn = get_db(); cur = conn.cursor()
    if campo == 'nome': cur.execute("SELECT id FROM clientes WHERE LOWER(nome)=LOWER(%s)", (valor,))
    elif campo == 'cpf': cur.execute("SELECT id FROM clientes WHERE cpf=%s", (valor,))
    elif campo == 'telefone': cur.execute("SELECT id FROM clientes WHERE telefone=%s OR telefone2=%s", (valor, valor))
    row = cur.fetchone(); cur.close(); close_db(conn)
    return jsonify({'ok': not bool(row)})


@login_required
def ficha_cliente(cid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE id=%s", (cid,))
    row = cur.fetchone(); cur.close(); close_db(conn)
    if not row:
        flash('Cliente nao encontrado.', 'erro'); return redirect(url_for('clientes'))
    c = dict(row)
    p = c['nome'].split()
    c['iniciais'] = (p[0][0] + (p[1][0] if len(p) > 1 else p[0][-1])).upper()
    ctx = get_ctx(); ctx['c'] = c
    return render_template('ficha_cliente.html', **ctx)


@login_required
def editar_cliente(cid):
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        cur.execute("""UPDATE clientes SET nome=%s,cpf=%s,data_nascimento=%s,telefone=%s,
            telefone2=%s,cep=%s,logradouro=%s,numero=%s,complemento=%s,bairro=%s,
            cidade=%s,uf=%s,promocoes=%s,crediario=%s WHERE id=%s""",
            (request.form.get('nome', '').strip(),
             request.form.get('cpf', '').strip() or None,
             request.form.get('data_nascimento') or None,
             request.form.get('telefone', '').strip() or None,
             request.form.get('telefone2', '').strip() or None,
             request.form.get('cep', '').strip() or None,
             request.form.get('logradouro', '').strip() or None,
             request.form.get('numero', '').strip() or None,
             request.form.get('complemento', '').strip() or None,
             request.form.get('bairro', '').strip() or None,
             request.form.get('cidade', '').strip() or None,
             request.form.get('uf', '').strip() or None,
             request.form.get('promocoes', '0') == '1',
             request.form.get('crediario', '0') == '1', cid))
        conn.commit(); cur.close(); close_db(conn)
        flash('Cliente atualizado!', 'ok')
        return redirect(url_for('ficha_cliente', cid=cid))
    cur.execute("SELECT * FROM clientes WHERE id=%s", (cid,))
    c = cur.fetchone(); cur.close(); close_db(conn)
    if not c:
        flash('Cliente nao encontrado.', 'erro'); return redirect(url_for('clientes'))
    ctx = get_ctx(); ctx['c'] = c
    return render_template('editar_cliente.html', **ctx)


@login_required
def excluir_cliente(cid):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.', 'erro'); return redirect(url_for('clientes'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT codigo,nome FROM clientes WHERE id=%s", (cid,))
    _old = cur.fetchone()
    cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
    audit_log(cur, 'EXCLUIR_CLIENTE', 'clientes', cid, dict(_old) if _old else None)
    conn.commit(); cur.close(); close_db(conn)
    flash('Cliente excluido.', 'ok')
    return redirect(url_for('clientes'))


def register(app):
    app.add_url_rule('/clientes', 'clientes', clientes)
    app.add_url_rule('/clientes/novo', 'novo_cliente', novo_cliente, methods=['POST'])
    app.add_url_rule('/clientes/novo-rapido', 'criar_cliente_rapido', criar_cliente_rapido, methods=['POST'])
    app.add_url_rule('/clientes/verificar', 'verificar_cliente', verificar_cliente)
    app.add_url_rule('/clientes/<int:cid>', 'ficha_cliente', ficha_cliente)
    app.add_url_rule('/clientes/<int:cid>/editar', 'editar_cliente', editar_cliente, methods=['GET', 'POST'])
    app.add_url_rule('/clientes/<int:cid>/excluir', 'excluir_cliente', excluir_cliente, methods=['POST'])
