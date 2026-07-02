"""Vales (crédito da loja a favor do cliente): gerados em trocas/devoluções e
usados como forma de pagamento numa compra futura. É um PASSIVO (a loja deve ao
cliente) — o oposto do crediário."""
from datetime import date
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from db import get_db, close_db
from config import hoje_app
from auth import login_required, get_ctx, pode_excluir


def _prox_codigo_vale(cur):
    cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 3) AS INTEGER)),0) AS n FROM vales WHERE codigo ~ '^VL[0-9]+$'")
    return f"VL{cur.fetchone()['n'] + 1}"


def gerar_vale(cur, *, cliente_id, cliente_nome, valor, venda_origem=None, observacao=None):
    """Cria um vale (crédito) e devolve (id, codigo). Não faz commit."""
    valor = round(float(valor or 0), 2)
    if valor <= 0:
        return None, None
    cod = _prox_codigo_vale(cur)
    cur.execute("""INSERT INTO vales (codigo,cliente_id,cliente_nome,valor,saldo,status,venda_origem,observacao,usuario_id,usuario_nome)
        VALUES (%s,%s,%s,%s,%s,'aberto',%s,%s,%s,%s) RETURNING id""",
        (cod, cliente_id, cliente_nome or 'Cliente', valor, valor, venda_origem, observacao,
         session.get('uid'), session.get('nome')))
    return cur.fetchone()['id'], cod


def consumir_vale(cur, vale_id, valor_uso, venda_uso=None):
    """Abate `valor_uso` do saldo do vale; marca 'usado' quando zera. Registra o uso em
    vale_usos (rastreio de ONDE foi gasto — mesmo em uso parcial ou em várias vendas) e
    guarda a última venda em venda_uso. Devolve o valor efetivamente consumido (limitado
    ao saldo). Não faz commit."""
    cur.execute("SELECT saldo FROM vales WHERE id=%s AND status='aberto'", (vale_id,))
    r = cur.fetchone()
    if not r:
        return 0.0
    saldo = float(r['saldo'] or 0)
    usar = round(min(saldo, float(valor_uso or 0)), 2)
    if usar <= 0:
        return 0.0
    novo = round(saldo - usar, 2)
    if novo <= 0.01:
        cur.execute("UPDATE vales SET saldo=0, status='usado', venda_uso=%s, usado_em=CURRENT_TIMESTAMP WHERE id=%s", (venda_uso, vale_id))
    else:
        # Uso parcial: reduz o saldo, mantém 'aberto' e registra a última venda onde foi usado.
        cur.execute("UPDATE vales SET saldo=%s, venda_uso=%s, usado_em=CURRENT_TIMESTAMP WHERE id=%s", (novo, venda_uso, vale_id))
    # Histórico de uso (origem do gasto — para auditoria e para ver os produtos da venda)
    cur.execute("""INSERT INTO vale_usos (vale_id, venda_id, valor, usuario_id, usuario_nome)
                   VALUES (%s,%s,%s,%s,%s)""",
                (vale_id, venda_uso, usar, session.get('uid'), session.get('nome')))
    return usar


@login_required
def vales():
    conn = get_db(); cur = conn.cursor()
    hoje = hoje_app()
    # Período por data de criação do vale — padrão: início do ano até hoje.
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-01-01'))
    data_fim = request.args.get('data_fim', hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except ValueError: data_inicio = hoje.strftime('%Y-01-01')
    try: date.fromisoformat(data_fim)
    except ValueError: data_fim = hoje.strftime('%Y-%m-%d')
    cur.execute("SELECT * FROM vales WHERE DATE(criado_em) BETWEEN %s AND %s ORDER BY (status='aberto') DESC, criado_em DESC", (data_inicio, data_fim))
    lista = [dict(v) for v in cur.fetchall()]
    # v140: histórico de uso de cada vale (onde foi gasto) para rastreio + link à ficha da venda.
    for v in lista:
        cur.execute("""SELECT u.venda_id, u.valor, u.criado_em, ve.codigo AS venda_codigo
                       FROM vale_usos u LEFT JOIN vendas ve ON ve.id = u.venda_id
                       WHERE u.vale_id = %s ORDER BY u.criado_em""", (v['id'],))
        v['usos'] = [dict(u) for u in cur.fetchall()]
    cur.execute("SELECT COALESCE(SUM(saldo),0) s, COUNT(*) n FROM vales WHERE status='aberto' AND DATE(criado_em) BETWEEN %s AND %s", (data_inicio, data_fim))
    t = cur.fetchone()
    cur.close(); close_db(conn)
    ctx = get_ctx(); ctx.update(vales=lista, total_aberto=float(t['s']), n_aberto=int(t['n']),
                                data_inicio=data_inicio, data_fim=data_fim)
    return render_template('vales.html', **ctx)


@login_required
def vales_cliente():
    """JSON: vales em aberto de um cliente (por id, ou nome) — para usar na venda."""
    cid = request.args.get('cliente_id', '').strip()
    nome = request.args.get('nome', '').strip()
    conn = get_db(); cur = conn.cursor()
    if cid.isdigit():
        cur.execute("SELECT id,codigo,saldo FROM vales WHERE status='aberto' AND cliente_id=%s ORDER BY criado_em", (int(cid),))
    elif nome:
        cur.execute("SELECT id,codigo,saldo FROM vales WHERE status='aberto' AND LOWER(cliente_nome)=LOWER(%s) ORDER BY criado_em", (nome,))
    else:
        cur.close(); close_db(conn); return jsonify({'vales': []})
    out = [{'id': r['id'], 'codigo': r['codigo'], 'saldo': float(r['saldo'] or 0)} for r in cur.fetchall()]
    cur.close(); close_db(conn)
    return jsonify({'vales': out})


@login_required
def buscar_vale():
    """JSON: busca UM vale em aberto pelo código (ex.: VL5 ou só 5) — usado para
    lançar o código do vale direto na venda. Retorna saldo e cliente."""
    cod = request.args.get('codigo', '').strip().upper()
    if cod.startswith('#'):
        cod = cod[1:]
    if cod and cod.isdigit():
        cod = 'VL' + cod
    if not cod:
        return jsonify({'ok': False, 'erro': 'Informe o código do vale.'})
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id,codigo,saldo,cliente_id,cliente_nome FROM vales WHERE UPPER(codigo)=%s", (cod,))
    r = cur.fetchone()
    cur.close(); close_db(conn)
    if not r:
        return jsonify({'ok': False, 'erro': f'Vale {cod} não encontrado.'})
    r = dict(r)
    saldo = float(r['saldo'] or 0)
    if saldo <= 0:
        return jsonify({'ok': False, 'erro': f'Vale {cod} já foi totalmente utilizado.'})
    return jsonify({'ok': True, 'vale': {'id': r['id'], 'codigo': r['codigo'], 'saldo': saldo,
                                         'cliente_id': r['cliente_id'], 'cliente_nome': r['cliente_nome']}})


@login_required
def excluir_vale(vid):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.', 'erro'); return redirect(url_for('vales'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM vales WHERE id=%s", (vid,))
        conn.commit(); flash('Vale excluído.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('vales'))


def register(app):
    app.add_url_rule('/vales', 'vales', vales)
    app.add_url_rule('/vales/cliente', 'vales_cliente', vales_cliente)
    app.add_url_rule('/vales/buscar', 'buscar_vale', buscar_vale)
    app.add_url_rule('/vales/<int:vid>/excluir', 'excluir_vale', excluir_vale, methods=['POST'])
