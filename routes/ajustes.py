"""Rotas de Ajustes Financeiros (V120).

Permite lançar entradas avulsas no caixa, principalmente para saldo inicial de
implantação, ajuste de caixa, recebimento avulso, aporte dos sócios,
transferência e outros.
"""
from datetime import date, datetime, time
from flask import render_template, request, redirect, url_for, session, flash
from db import get_db, close_db
from config import hoje_app, fim_mes_app
from auth import login_required, get_ctx, pode_excluir
from utils import parse_brl, audit_log, get_taxa_vigente, calcular_liquido

TIPOS_AJUSTE = [
    ('saldo_inicial', 'Saldo Inicial'),
    ('ajuste_caixa', 'Ajuste de Caixa'),
    ('recebimento_avulso', 'Recebimento Avulso'),
    ('aporte_socios', 'Aporte dos Sócios'),
    ('transferencia', 'Transferência'),
    ('outros', 'Outros'),
]

FORMAS_PAGAMENTO = [
    ('dinheiro', 'Dinheiro'),
    ('pix', 'PIX'),
    ('debito', 'Débito'),
    ('credito_vista', 'Crédito à Vista'),
    ('credito_parcelado', 'Crédito Parcelado'),
    ('link', 'Link'),
    ('transferencia', 'Transferência'),
]

TIPOS_DICT = dict(TIPOS_AJUSTE)
FORMAS_DICT = dict(FORMAS_PAGAMENTO)


def _parse_iso_date(value, default=None):
    try:
        return date.fromisoformat(value)
    except Exception:
        return default or hoje_app()


def _timestamp_do_ajuste(data_ajuste):
    """Mantém a data informada e usa o horário atual para ordenar no caixa."""
    agora = datetime.now().time().replace(microsecond=0)
    return datetime.combine(data_ajuste, agora)


def _enriquecer_liquido(lista):
    """Calcula valor_bruto, desconto_taxa e valor_liquido para cada ajuste."""
    taxas_cache = {}
    for a in lista:
        data = a.get('data_ajuste')
        data_key = data.strftime('%Y-%m-%d') if hasattr(data, 'strftime') else str(data or '')
        if data_key not in taxas_cache:
            taxas_cache[data_key] = get_taxa_vigente(data)
        taxa = taxas_cache[data_key]
        bruto = float(a.get('valor') or 0)
        liquido, desconto, taxa_pct = calcular_liquido(bruto, a.get('forma_pagamento'), taxa)
        a['valor_bruto'] = bruto
        a['desconto_taxa'] = desconto
        a['valor_liquido'] = liquido
        a['taxa_pct'] = taxa_pct


@login_required
def ajustes():
    conn = get_db(); cur = conn.cursor()
    hoje = hoje_app()
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim = request.args.get('data_fim', fim_mes_app())
    try: date.fromisoformat(data_inicio)
    except Exception: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except Exception: data_fim = fim_mes_app()

    cur.execute("""SELECT * FROM ajustes_financeiros
                   WHERE DATE(data_ajuste) BETWEEN %s AND %s
                   ORDER BY data_ajuste DESC, id DESC""", (data_inicio, data_fim))
    lista = [dict(a) for a in cur.fetchall()]

    cur.execute("""SELECT
        COALESCE(SUM(valor),0) AS total,
        COALESCE(SUM(CASE WHEN tipo_ajuste='saldo_inicial' THEN valor ELSE 0 END),0) AS saldo_inicial,
        COALESCE(SUM(CASE WHEN tipo_ajuste='ajuste_caixa' THEN valor ELSE 0 END),0) AS ajuste_caixa,
        COALESCE(SUM(CASE WHEN tipo_ajuste='recebimento_avulso' THEN valor ELSE 0 END),0) AS recebimento_avulso,
        COALESCE(SUM(CASE WHEN tipo_ajuste='aporte_socios' THEN valor ELSE 0 END),0) AS aporte_socios,
        COALESCE(SUM(CASE WHEN tipo_ajuste='transferencia' THEN valor ELSE 0 END),0) AS transferencia,
        COALESCE(SUM(CASE WHEN tipo_ajuste='outros' THEN valor ELSE 0 END),0) AS outros
        FROM ajustes_financeiros
        WHERE DATE(data_ajuste) BETWEEN %s AND %s""", (data_inicio, data_fim))
    totais = dict(cur.fetchone())
    cur.close(); close_db(conn)

    _enriquecer_liquido(lista)

    ctx = get_ctx()
    ctx.update(lista=lista, totais=totais, tipos_ajuste=TIPOS_AJUSTE,
               formas_pagamento=FORMAS_PAGAMENTO, tipos_dict=TIPOS_DICT,
               formas_dict=FORMAS_DICT, data_inicio=data_inicio, data_fim=data_fim,
               hoje=hoje.strftime('%Y-%m-%d'))
    return render_template('ajustes.html', **ctx)


@login_required
def novo_ajuste():
    data_ajuste = _parse_iso_date(request.form.get('data_ajuste'), hoje_app())
    tipo_ajuste = request.form.get('tipo_ajuste') or ''
    forma_pagamento = request.form.get('forma_pagamento') or ''
    descricao = (request.form.get('descricao') or '').strip()
    observacao = (request.form.get('observacao') or '').strip()
    valor = parse_brl(request.form.get('valor'))

    if tipo_ajuste not in TIPOS_DICT:
        flash('Selecione um tipo de ajuste válido.', 'erro')
        return redirect(url_for('ajustes'))
    if forma_pagamento not in FORMAS_DICT:
        flash('Selecione uma forma de pagamento válida.', 'erro')
        return redirect(url_for('ajustes'))
    if valor <= 0:
        flash('Informe um valor maior que zero.', 'erro')
        return redirect(url_for('ajustes'))
    if not descricao:
        descricao = TIPOS_DICT.get(tipo_ajuste, 'Ajuste financeiro')

    criado_em = _timestamp_do_ajuste(data_ajuste)
    desc_caixa = f"Ajuste Financeiro - {TIPOS_DICT[tipo_ajuste]}: {descricao}"

    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("""INSERT INTO caixa
            (descricao, valor, tipo, forma_pagamento, usuario_id, vendedora_nome, criado_em)
            VALUES (%s,%s,'entrada',%s,%s,%s,%s) RETURNING id""",
            (desc_caixa, valor, forma_pagamento, session.get('uid'), session.get('nome'), criado_em))
        caixa_id = cur.fetchone()['id']

        cur.execute("""INSERT INTO ajustes_financeiros
            (data_ajuste, tipo_ajuste, descricao, forma_pagamento, valor, observacao,
             caixa_id, usuario_id, usuario_nome, criado_em)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (data_ajuste, tipo_ajuste, descricao, forma_pagamento, valor, observacao or None,
             caixa_id, session.get('uid'), session.get('nome'), criado_em))
        ajuste_id = cur.fetchone()['id']
        audit_log(cur, 'CRIAR_AJUSTE_FINANCEIRO', 'ajustes_financeiros', ajuste_id,
                  {'tipo': tipo_ajuste, 'forma': forma_pagamento, 'valor': valor, 'caixa_id': caixa_id})
        conn.commit()
        flash('Ajuste financeiro lançado e integrado ao caixa.', 'sucesso')
    except Exception as exc:
        conn.rollback()
        flash(f'Erro ao lançar ajuste financeiro: {exc}', 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('ajustes'))


@login_required
def editar_ajuste(ajuste_id):
    if session.get('perfil') not in ('admin_n1', 'admin_n2'):
        flash('Apenas administradores podem editar ajustes financeiros.', 'erro')
        return redirect(url_for('ajustes'))

    data_ajuste = _parse_iso_date(request.form.get('data_ajuste'), hoje_app())
    tipo_ajuste = request.form.get('tipo_ajuste') or ''
    forma_pagamento = request.form.get('forma_pagamento') or ''
    descricao = (request.form.get('descricao') or '').strip()
    observacao = (request.form.get('observacao') or '').strip()
    valor = parse_brl(request.form.get('valor'))

    if tipo_ajuste not in TIPOS_DICT:
        flash('Tipo de ajuste inválido.', 'erro')
        return redirect(url_for('ajustes'))
    if forma_pagamento not in FORMAS_DICT:
        flash('Forma de pagamento inválida.', 'erro')
        return redirect(url_for('ajustes'))
    if valor <= 0:
        flash('Informe um valor maior que zero.', 'erro')
        return redirect(url_for('ajustes'))
    if not descricao:
        descricao = TIPOS_DICT.get(tipo_ajuste, 'Ajuste financeiro')

    criado_em = _timestamp_do_ajuste(data_ajuste)
    desc_caixa = f"Ajuste Financeiro - {TIPOS_DICT[tipo_ajuste]}: {descricao}"

    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute('SELECT * FROM ajustes_financeiros WHERE id=%s', (ajuste_id,))
        ajuste = cur.fetchone()
        if not ajuste:
            flash('Ajuste não encontrado.', 'erro')
            return redirect(url_for('ajustes'))

        cur.execute("""UPDATE ajustes_financeiros
            SET data_ajuste=%s, tipo_ajuste=%s, descricao=%s, forma_pagamento=%s,
                valor=%s, observacao=%s, criado_em=%s
            WHERE id=%s""",
            (data_ajuste, tipo_ajuste, descricao, forma_pagamento, valor,
             observacao or None, criado_em, ajuste_id))

        caixa_id = ajuste.get('caixa_id')
        if caixa_id:
            cur.execute("""UPDATE caixa SET descricao=%s, valor=%s, forma_pagamento=%s, criado_em=%s
                WHERE id=%s""",
                (desc_caixa, valor, forma_pagamento, criado_em, caixa_id))

        audit_log(cur, 'EDITAR_AJUSTE_FINANCEIRO', 'ajustes_financeiros', ajuste_id,
                  {'tipo': tipo_ajuste, 'forma': forma_pagamento, 'valor': valor, 'caixa_id': caixa_id})
        conn.commit()
        flash('Ajuste financeiro atualizado.', 'sucesso')
    except Exception as exc:
        conn.rollback()
        flash(f'Erro ao atualizar ajuste: {exc}', 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('ajustes'))


@login_required
def excluir_ajuste(ajuste_id):
    if not pode_excluir():
        flash('Apenas Administrador N1 pode excluir ajustes financeiros.', 'erro')
        return redirect(url_for('ajustes'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute('SELECT * FROM ajustes_financeiros WHERE id=%s', (ajuste_id,))
        ajuste = cur.fetchone()
        if not ajuste:
            flash('Ajuste financeiro não encontrado.', 'erro')
            return redirect(url_for('ajustes'))
        caixa_id = ajuste.get('caixa_id')
        cur.execute('DELETE FROM ajustes_financeiros WHERE id=%s', (ajuste_id,))
        if caixa_id:
            cur.execute('DELETE FROM caixa WHERE id=%s AND venda_id IS NULL AND crediario_id IS NULL AND despesa_id IS NULL', (caixa_id,))
        audit_log(cur, 'EXCLUIR_AJUSTE_FINANCEIRO', 'ajustes_financeiros', ajuste_id,
                  {'caixa_id': caixa_id, 'valor': float(ajuste.get('valor') or 0), 'tipo': ajuste.get('tipo_ajuste')})
        conn.commit()
        flash('Ajuste financeiro excluído do histórico e do caixa.', 'sucesso')
    except Exception as exc:
        conn.rollback(); flash(f'Erro ao excluir ajuste: {exc}', 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('ajustes'))


def register(app):
    app.add_url_rule('/ajustes', 'ajustes', ajustes)
    app.add_url_rule('/ajustes/novo', 'novo_ajuste', novo_ajuste, methods=['POST'])
    app.add_url_rule('/ajustes/<int:ajuste_id>/editar', 'editar_ajuste', editar_ajuste, methods=['POST'])
    app.add_url_rule('/ajustes/excluir/<int:ajuste_id>', 'excluir_ajuste', excluir_ajuste, methods=['POST'])
