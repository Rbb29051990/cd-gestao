"""Rotas de Vendas: listagem com período, nova venda (com baixa de estoque e
crediário), ficha, exclusão (restaura estoque/caixa), edição, ranking e buscas."""
import json
from datetime import date
from flask import render_template, request, redirect, url_for, flash, jsonify
from db import get_db, close_db
from config import agora_app, hoje_app, fim_mes_app
from auth import login_required, get_ctx, pode_excluir
from utils import parse_brl, bloquear_estoque_negativo, audit_log, get_taxa_vigente, calcular_liquido

# Formas de cartão (sofrem taxa da maquininha no momento da venda à vista).
# Crediário/pix/dinheiro não têm taxa aqui — a taxa das parcelas aparece no Caixa.
FORMAS_CARTAO = ('credito_vista', 'credito_parcelado', 'debito', 'link')


def _fin_venda(v, taxa_cache):
    """Decompõe uma venda em (bruto, desconto, taxa, líquido).
    Líquido = bruto - desconto - taxa do cartão (o que de fato entra na conta)."""
    bruto = float(v.get('valor_total') or 0)
    desconto = float(v.get('desconto') or 0)
    pago = round(bruto - desconto, 2)
    forma = v.get('forma_pagamento') or ''
    if forma in FORMAS_CARTAO:
        d = v.get('criado_em')
        chave = d.date().isoformat() if hasattr(d, 'date') else 'hoje'
        if chave not in taxa_cache:
            taxa_cache[chave] = get_taxa_vigente(d.date() if hasattr(d, 'date') else None)
        liq, desc_taxa, _ = calcular_liquido(pago, forma, taxa_cache[chave], v.get('parcelas'))
        return bruto, desconto, desc_taxa, liq
    return bruto, desconto, 0.0, pago


@login_required
def vendas():
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE ativo=TRUE ORDER BY nome")
        vendedoras = [dict(u) for u in cur.fetchall()]
        cur.execute("SELECT id,codigo,nome,crediario FROM clientes WHERE ativo=TRUE ORDER BY nome")
        clientes_lista = [dict(c) for c in cur.fetchall()]
        hoje = hoje_app()
        data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
        data_fim    = request.args.get('data_fim',    fim_mes_app())
        try: date.fromisoformat(data_inicio)
        except: data_inicio = hoje.strftime('%Y-%m-01')
        try: date.fromisoformat(data_fim)
        except: data_fim = fim_mes_app()
        cur.execute("""SELECT v.*, COUNT(vi.id) as qtd_itens FROM vendas v
            LEFT JOIN venda_itens vi ON vi.venda_id=v.id
            WHERE DATE(v.criado_em) BETWEEN %s AND %s
            GROUP BY v.id ORDER BY v.criado_em DESC""", (data_inicio, data_fim))
        lista_vendas = [dict(v) for v in cur.fetchall()]
        cur.execute("""SELECT c.*,v.criado_em as data_venda FROM crediarios c
            JOIN vendas v ON v.id=c.venda_id ORDER BY c.criado_em DESC""")
        lista_crediarios = [dict(c) for c in cur.fetchall()]
        mes_ini = agora_app().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cur.execute("""SELECT vendedora_nome,COALESCE(SUM(valor_total),0) as total,
            COUNT(id) as num_vendas,COUNT(DISTINCT cliente_id) as clientes
            FROM vendas WHERE criado_em>=%s GROUP BY vendedora_nome ORDER BY total DESC""", (mes_ini,))
        ranking = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT DATE_TRUNC('month',criado_em) as mes FROM vendas ORDER BY mes DESC")
        meses = [{'mes_val': m['mes'].strftime('%Y-%m'), 'mes_label': m['mes'].strftime('%B / %Y').capitalize()} for m in cur.fetchall()]
        cur.close(); close_db(conn)
        now_mes = agora_app().strftime('%Y-%m')
        now_mes_label = agora_app().strftime('%B / %Y').capitalize()
        # Decompõe cada venda (bruto/desconto/taxa/líquido) e soma os totais do período
        taxa_cache = {}
        tot_bruto = tot_desc = tot_taxa = tot_liq = 0.0
        for v in lista_vendas:
            bruto, desc, taxa, liq = _fin_venda(v, taxa_cache)
            v['taxa_valor'] = round(taxa, 2)
            v['valor_liquido'] = round(liq, 2)
            tot_bruto += bruto; tot_desc += desc; tot_taxa += taxa; tot_liq += liq
        n_vendas = len(lista_vendas)
        ticket_liq = round(tot_liq / n_vendas, 2) if n_vendas else 0.0
        ctx = get_ctx()
        ctx.update(vendedoras=vendedoras, clientes=clientes_lista,
                   lista_vendas=lista_vendas, lista_crediarios=lista_crediarios,
                   ranking=ranking, meses=meses, now_mes=now_mes, now_mes_label=now_mes_label,
                   data_inicio=data_inicio, data_fim=data_fim,
                   total_bruto=round(tot_bruto, 2), total_desconto=round(tot_desc, 2),
                   total_taxa=round(tot_taxa, 2), total_liquido=round(tot_liq, 2),
                   n_vendas_periodo=n_vendas, ticket_liquido=ticket_liq)
        return render_template('vendas.html', **ctx)
    except Exception as e:
        return "<pre style='padding:20px'>ERRO VENDAS: " + str(e) + "</pre>", 500


@login_required
def nova_venda():
    conn = get_db(); cur = conn.cursor()
    try:
        usuario_id = request.form.get('usuario_id')
        vendedora_nome = request.form.get('vendedora_nome', '').strip()
        cliente_id = request.form.get('cliente_id')
        cliente_nome = request.form.get('cliente_nome', '').strip()
        forma = request.form.get('forma_pagamento', '').strip()
        parcelas = int(request.form.get('parcelas', 1) or 1)
        valor_total  = parse_brl(request.form.get('valor_total', '0'))
        desconto     = parse_brl(request.form.get('desconto_valor', '0'))
        pct_desconto = min(100.0, max(0.0, parse_brl(request.form.get('pct_desconto', '0'))))
        desconto     = min(desconto, valor_total)  # desconto nunca maior que o total
        itens = json.loads(request.form.get('itens', '[]'))
        cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)),0) as n FROM vendas WHERE codigo ~ '^V[0-9]+$'")
        n = cur.fetchone()['n']
        cod = f"V{n+1}"
        cur.execute("""INSERT INTO vendas (codigo,usuario_id,vendedora_nome,cliente_id,cliente_nome,
            valor_total,desconto,pct_desconto,forma_pagamento,parcelas) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (cod, usuario_id or None, vendedora_nome, cliente_id or None, cliente_nome, valor_total, desconto, pct_desconto, forma, parcelas))
        venda_id = cur.fetchone()['id']
        for item in itens:
            pid = item.get('produto_id')
            qtd = int(item.get('quantidade', 1))
            vunit = float(item.get('valor_unitario', 0))
            cur.execute("""INSERT INTO venda_itens (venda_id,produto_id,codigo_produto,modelo,
                descricao,tamanho,valor_unitario,quantidade,valor_total)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (venda_id, pid or None, item.get('codigo'), item.get('modelo'),
                 item.get('descricao'), item.get('tamanho'), vunit, qtd, vunit * qtd))
            if pid:
                bloquear_estoque_negativo(cur, pid, qtd)
        if forma == 'crediario':
            entrada = parse_brl(request.form.get('entrada', '0'))
            saldo = valor_total - entrada
            cur.execute("""INSERT INTO crediarios (venda_id,cliente_id,cliente_nome,valor_total,entrada,saldo_devedor)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (venda_id, cliente_id or None, cliente_nome, valor_total, entrada, saldo))
            cred_id = cur.fetchone()['id']
            for i, p in enumerate(json.loads(request.form.get('parcelas_datas', '[]'))):
                cur.execute("INSERT INTO crediario_parcelas (crediario_id,numero_parcela,data_vencimento,valor) VALUES (%s,%s,%s,%s)",
                    (cred_id, i + 1, p.get('data'), float(p.get('valor', 0))))
        # Valor final = total - desconto (enviado já calculado pelo JS)
        valor_final_form = parse_brl(request.form.get('valor_final', '0'))
        valor_final = valor_final_form if valor_final_form > 0 else round(valor_total - desconto, 2)

        # Registrar no caixa conforme forma de pagamento
        formas_a_vista = ['pix', 'dinheiro', 'debito', 'credito_vista', 'credito_parcelado', 'link']
        if forma in formas_a_vista:
            # Entra tudo no caixa no dia. Guarda o nº de parcelas só p/ crédito parcelado
            # (usado no cálculo do líquido com a taxa da parcela correspondente).
            parcelas_caixa = parcelas if forma == 'credito_parcelado' else None
            cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,usuario_id,vendedora_nome,parcelas)
                VALUES (%s,%s,'entrada',%s,%s,%s,%s,%s)""",
                (f"Venda {cod} - {cliente_nome}", valor_final, forma, venda_id, usuario_id or None, vendedora_nome, parcelas_caixa))
        elif forma == 'crediario':
            # Só registra a entrada paga (se houver) — com a forma de pagamento REAL da entrada
            if entrada > 0:
                entrada_forma = request.form.get('entrada_forma', 'dinheiro').strip() or 'dinheiro'
                if entrada_forma not in formas_a_vista: entrada_forma = 'dinheiro'
                ent_parc = int(request.form.get('entrada_parcelas', 0) or 0) or None if entrada_forma == 'credito_parcelado' else None
                cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,crediario_id,usuario_id,vendedora_nome,parcelas)
                    VALUES (%s,%s,'entrada',%s,%s,%s,%s,%s,%s)""",
                    (f"Entrada crediário - {cliente_nome} ({entrada_forma.replace('_',' ')})", entrada, entrada_forma, venda_id, cred_id, usuario_id or None, vendedora_nome, ent_parc))

        audit_log(cur, 'CRIAR_VENDA', 'vendas', venda_id, {'codigo': cod, 'cliente': cliente_nome, 'valor_final': valor_final, 'forma_pagamento': forma, 'qtd_itens': len(itens)})
        conn.commit(); flash('Venda registrada!', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('vendas'))


@login_required
def ficha_venda(vid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM vendas WHERE id=%s", (vid,))
    row = cur.fetchone()
    if not row: flash('Venda nao encontrada.', 'erro'); return redirect(url_for('vendas'))
    venda = dict(row)
    cur.execute("SELECT * FROM venda_itens WHERE venda_id=%s", (vid,))
    itens = [dict(i) for i in cur.fetchall()]
    crediario = None
    if venda.get('forma_pagamento') == 'crediario':
        cur.execute("SELECT * FROM crediarios WHERE venda_id=%s", (vid,))
        c = cur.fetchone()
        if c:
            crediario = dict(c)
            cur.execute("SELECT * FROM crediario_parcelas WHERE crediario_id=%s ORDER BY numero_parcela", (crediario['id'],))
            crediario['parcelas'] = [dict(p) for p in cur.fetchall()]
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u) for u in cur.fetchall()]
    cur.close(); close_db(conn)
    ctx = get_ctx(); ctx.update(venda=venda, itens=itens, crediario=crediario, vendedoras=vendedoras)
    return render_template('ficha_venda.html', **ctx)


@login_required
def excluir_venda(vid):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.', 'erro')
        return redirect(url_for('ficha_venda', vid=vid))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM venda_itens WHERE venda_id=%s", (vid,))
        for item in cur.fetchall():
            if item['produto_id']:
                cur.execute("UPDATE estoque SET quantidade=quantidade+%s WHERE id=%s", (item['quantidade'], item['produto_id']))
        # Crediários gerados por esta venda
        cur.execute("SELECT id FROM crediarios WHERE venda_id=%s", (vid,))
        cred_ids = [r['id'] for r in cur.fetchall()]
        # Remover do caixa os lançamentos diretos da venda (à vista e entrada do crediário)
        cur.execute("DELETE FROM caixa WHERE venda_id=%s", (vid,))
        # Remover do caixa os recebimentos de parcela (gravados por crediario_id, sem venda_id)
        # e as parcelas desses crediários
        if cred_ids:
            cur.execute("DELETE FROM caixa WHERE crediario_id = ANY(%s)", (cred_ids,))
            cur.execute("DELETE FROM crediario_parcelas WHERE crediario_id = ANY(%s)", (cred_ids,))
        # Remover o(s) crediário(s) da venda
        cur.execute("DELETE FROM crediarios WHERE venda_id=%s", (vid,))
        cur.execute("SELECT codigo,cliente_nome,valor_total,forma_pagamento FROM vendas WHERE id=%s", (vid,))
        _old_venda = cur.fetchone()
        cur.execute("DELETE FROM vendas WHERE id=%s", (vid,))
        audit_log(cur, 'EXCLUIR_VENDA', 'vendas', vid, dict(_old_venda) if _old_venda else None)
        conn.commit(); flash('Venda excluída. Estoque e caixa restaurados.', 'ok')
    except Exception as e: conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('vendas'))


@login_required
def editar_venda(vid):
    # Edição liberada para quem tem acesso à aba Vendas (vendedor só não pode excluir).
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        try:
            cliente_nome = request.form.get('cliente_nome', '').strip()
            vendedora_nome = request.form.get('vendedora_nome', '').strip()
            forma_pagamento = request.form.get('forma_pagamento', '')
            parcelas = int(request.form.get('parcelas', 1) or 1)
            cur.execute("""UPDATE vendas SET cliente_nome=%s, vendedora_nome=%s,
                          forma_pagamento=%s, parcelas=%s WHERE id=%s""",
                       (cliente_nome, vendedora_nome, forma_pagamento, parcelas, vid))
            # Sincroniza a forma no Caixa (e, por consequência, na Visão Geral).
            # Atualiza só a entrada à-vista desta venda — não mexe na entrada/parcelas
            # de crediário (que têm a própria forma de pagamento).
            formas_a_vista = ['pix', 'dinheiro', 'debito', 'credito_vista', 'credito_parcelado', 'link']
            if forma_pagamento in formas_a_vista:
                parcelas_caixa = parcelas if forma_pagamento == 'credito_parcelado' else None
                cur.execute("""UPDATE caixa SET forma_pagamento=%s, parcelas=%s
                               WHERE venda_id=%s AND crediario_id IS NULL AND tipo='entrada'""",
                            (forma_pagamento, parcelas_caixa, vid))
            audit_log(cur, 'ALTERAR_VENDA', 'vendas', vid,
                      {'forma_pagamento': forma_pagamento, 'cliente': cliente_nome})
            conn.commit()
            flash('Venda atualizada com sucesso!', 'ok')
            return redirect(url_for('ficha_venda', vid=vid))
        except Exception as e:
            conn.rollback(); flash(str(e), 'erro')
        finally: cur.close(); close_db(conn)
        return redirect(url_for('ficha_venda', vid=vid))
    cur.execute("SELECT * FROM vendas WHERE id=%s", (vid,))
    row = cur.fetchone()
    if not row:
        flash('Venda não encontrada.', 'erro')
        return redirect(url_for('vendas'))
    venda = dict(row)
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u)['nome'] for u in cur.fetchall()]
    cur.close(); close_db(conn)
    ctx = get_ctx(); ctx.update(venda=venda, vendedoras=vendedoras)
    return render_template('editar_venda.html', **ctx)


@login_required
def ranking_vendedoras():
    hoje = hoje_app()
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim = request.args.get('data_fim', fim_mes_app())
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = fim_mes_app()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT vendedora_nome, valor_total, desconto, forma_pagamento, criado_em, cliente_id
        FROM vendas WHERE DATE(criado_em) BETWEEN %s AND %s""", (data_inicio, data_fim))
    vendas_periodo = [dict(r) for r in cur.fetchall()]
    cur.close(); close_db(conn)
    # Agrega por vendedora calculando o líquido (bruto - desconto - taxa)
    taxa_cache = {}
    agg = {}
    for v in vendas_periodo:
        nome = v.get('vendedora_nome') or '—'
        bruto, desc, taxa, liq = _fin_venda(v, taxa_cache)
        a = agg.setdefault(nome, {'vendedora_nome': nome, 'bruto': 0.0, 'desconto': 0.0,
                                  'taxa': 0.0, 'liquido': 0.0, 'num_vendas': 0, '_clientes': set()})
        a['bruto'] += bruto; a['desconto'] += desc; a['taxa'] += taxa; a['liquido'] += liq
        a['num_vendas'] += 1
        if v.get('cliente_id'):
            a['_clientes'].add(v['cliente_id'])
    ranking = []
    for a in agg.values():
        ranking.append({'vendedora_nome': a['vendedora_nome'],
                        'bruto': round(a['bruto'], 2), 'desconto': round(a['desconto'], 2),
                        'taxa': round(a['taxa'], 2), 'liquido': round(a['liquido'], 2),
                        'total': round(a['liquido'], 2),  # compat: ranking por líquido
                        'num_vendas': a['num_vendas'], 'clientes': len(a['_clientes'])})
    ranking.sort(key=lambda r: r['liquido'], reverse=True)
    return jsonify({'ranking': ranking})


@login_required
def buscar_ref():
    ref = request.args.get('ref', '').strip().upper()
    busca = ref if ref.startswith('P') else f"P{ref}"
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id as produto_id,codigo,modelo,descricao,tamanho,valor_venda,desconto_promo,quantidade FROM estoque WHERE codigo=%s AND ativo=TRUE AND quantidade>0", (busca,))
    item = cur.fetchone(); cur.close(); close_db(conn)
    if item:
        it = dict(item)
        dp = float(it.get('desconto_promo') or 0)
        it['valor_original'] = float(it['valor_venda'] or 0)
        it['desconto_promo'] = dp
        it['valor_final'] = round(it['valor_original'] * (1 - dp / 100), 2) if dp > 0 else it['valor_original']
        return jsonify({'ok': True, 'item': it})
    return jsonify({'ok': False})


@login_required
def buscar_cliente():
    q = request.args.get('q', '').strip()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id,codigo,nome,crediario FROM clientes WHERE ativo=TRUE AND (LOWER(nome) LIKE %s OR codigo ILIKE %s) ORDER BY nome LIMIT 8",
        (f'%{q.lower()}%', f'%{q}%'))
    lista = [dict(c) for c in cur.fetchall()]
    cur.close(); close_db(conn)
    return jsonify({'clientes': lista})


def register(app):
    app.add_url_rule('/vendas', 'vendas', vendas)
    app.add_url_rule('/vendas/nova', 'nova_venda', nova_venda, methods=['POST'])
    app.add_url_rule('/vendas/<int:vid>', 'ficha_venda', ficha_venda)
    app.add_url_rule('/vendas/<int:vid>/excluir', 'excluir_venda', excluir_venda, methods=['POST'])
    app.add_url_rule('/vendas/<int:vid>/editar', 'editar_venda', editar_venda, methods=['GET', 'POST'])
    app.add_url_rule('/vendas/ranking', 'ranking_vendedoras', ranking_vendedoras)
    app.add_url_rule('/vendas/buscar-ref', 'buscar_ref', buscar_ref)
    app.add_url_rule('/vendas/buscar-cliente', 'buscar_cliente', buscar_cliente)
