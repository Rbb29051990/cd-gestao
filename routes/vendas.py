"""Rotas de Vendas: listagem com período, nova venda (com baixa de estoque e
crediário), ficha, exclusão (restaura estoque/caixa), edição, ranking e buscas."""
import json
from datetime import date
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from db import get_db, close_db
from config import agora_app, hoje_app, fim_mes_app
from auth import login_required, get_ctx, pode_excluir
from utils import (parse_brl, bloquear_estoque_negativo, audit_log, get_taxa_vigente,
                   calcular_liquido, parse_pagamentos, registrar_pagamentos_caixa,
                   liquido_caixa_por_venda)
from routes.vales import gerar_vale, consumir_vale

# Formas de cartão (sofrem taxa da maquininha no momento da venda à vista).
# Crediário/pix/dinheiro não têm taxa aqui — a taxa das parcelas aparece no Caixa.
FORMAS_CARTAO = ('credito_vista', 'credito_parcelado', 'debito', 'link')
# Formas à vista que entram direto no caixa (1 linha por venda).
FORMAS_A_VISTA = ['pix', 'dinheiro', 'debito', 'credito_vista', 'credito_parcelado', 'link']


def _fin_venda(v, taxa_cache, split_map=None):
    """Decompõe uma venda em (bruto, desconto, taxa, líquido).
    Líquido = bruto - desconto - taxa do cartão (o que de fato entra na conta).
    Para pagamento dividido (forma='multiplo'), a taxa e o líquido vêm das linhas
    de caixa daquela venda (split_map: {venda_id: (bruto, taxa, liquido)})."""
    bruto = float(v.get('valor_total') or 0)
    desconto = float(v.get('desconto') or 0)
    pago = round(bruto - desconto, 2)
    forma = v.get('forma_pagamento') or ''
    if forma == 'multiplo':
        # Líquido vem das linhas do caixa desta venda (split / troca / vale). Sem linhas
        # (ex.: pago totalmente com vale), o líquido em caixa é 0.
        _b, taxa_split, liq_split = (split_map or {}).get(v.get('id'), (0.0, 0.0, 0.0))
        return bruto, desconto, round(taxa_split, 2), round(liq_split, 2)
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
        # Líquido das vendas com pagamento dividido vem das linhas do caixa.
        split_map = liquido_caixa_por_venda(cur, [v['id'] for v in lista_vendas if v.get('forma_pagamento') == 'multiplo'])
        # v141: quais vendas do período GERARAM um vale (para a etiqueta 🎟️ na lista).
        ids_periodo = [v['id'] for v in lista_vendas]
        vendas_com_vale = set()
        if ids_periodo:
            cur.execute("SELECT DISTINCT venda_origem FROM vales WHERE venda_origem = ANY(%s)", (ids_periodo,))
            vendas_com_vale = {r['venda_origem'] for r in cur.fetchall()}
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
            bruto, desc, taxa, liq = _fin_venda(v, taxa_cache, split_map)
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
                   n_vendas_periodo=n_vendas, ticket_liquido=ticket_liq,
                   vendas_com_vale=vendas_com_vale)
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
        # Valor final = total - desconto (enviado já calculado pelo JS; v141: também vale
        # para o crediário — o cliente deve entrada+parcelas sobre o valor JÁ com desconto).
        valor_final_form = parse_brl(request.form.get('valor_final', '0'))
        valor_final = valor_final_form if valor_final_form > 0 else round(valor_total - desconto, 2)
        if forma == 'crediario':
            entrada = parse_brl(request.form.get('entrada', '0'))
            saldo = round(valor_final - entrada, 2)
            cur.execute("""INSERT INTO crediarios (venda_id,cliente_id,cliente_nome,valor_total,entrada,saldo_devedor)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (venda_id, cliente_id or None, cliente_nome, valor_final, entrada, saldo))
            cred_id = cur.fetchone()['id']
            for i, p in enumerate(json.loads(request.form.get('parcelas_datas', '[]'))):
                cur.execute("INSERT INTO crediario_parcelas (crediario_id,numero_parcela,data_vencimento,valor) VALUES (%s,%s,%s,%s)",
                    (cred_id, i + 1, p.get('data'), float(p.get('valor', 0))))

        # ── Vale(s) (crédito da loja): abatem do valor da venda ANTES de registrar o caixa.
        # Pode combinar VÁRIOS vales (ex.: mãe + filha) — consumidos em ordem até cobrir o
        # valor da venda. Vale não gera taxa e não entra no caixa; só o restante (a pagar) é
        # registrado. O saldo que sobrar continua no vale. Não se aplica ao crediário. ──
        vales_ids = []
        try:
            vales_ids = [int(x) for x in json.loads(request.form.get('vales_ids', '[]')) if str(x).isdigit()]
        except Exception:
            vales_ids = []
        # Compatibilidade: aceita o formato antigo de vale único.
        if not vales_ids and request.form.get('vale_id', '').strip().isdigit():
            vales_ids = [int(request.form.get('vale_id').strip())]
        vale_usado = 0.0
        if vales_ids and forma != 'crediario':
            restante = valor_final
            for vid in vales_ids:
                if restante <= 0.01:
                    break
                u = consumir_vale(cur, vid, restante, venda_id)
                restante = round(restante - u, 2)
                vale_usado = round(vale_usado + u, 2)
            if vale_usado > 0:
                # A parte paga com vale não é caixa; o líquido sai das linhas restantes.
                cur.execute("UPDATE vendas SET forma_pagamento='multiplo' WHERE id=%s", (venda_id,))

        # Registrar no caixa conforme forma de pagamento
        if forma == 'multiplo':
            # Pagamento dividido à vista: cada forma escolhida vira uma entrada no caixa,
            # com sua própria taxa (Taxa Flex) — garantindo o líquido correto no caixa.
            alvo = round(valor_final - vale_usado, 2)   # o que sobra para as formas cobrirem
            pagamentos = parse_pagamentos(request.form.get('pagamentos'))
            if alvo > 0.01:
                if not pagamentos:
                    raise ValueError('Pagamento dividido sem formas válidas.')
                soma = round(sum(p['valor'] for p in pagamentos), 2)
                if abs(soma - alvo) > 0.02:
                    raise ValueError(f'A soma das formas (R$ {soma:.2f}) não bate com o valor a pagar (R$ {alvo:.2f}).')
                registrar_pagamentos_caixa(cur, pagamentos, f"Venda {cod} - {cliente_nome}",
                    venda_id=venda_id, usuario_id=usuario_id or None, vendedora_nome=vendedora_nome)
            # alvo <= 0: pago integralmente com o vale — nenhuma linha de caixa.
        elif forma in FORMAS_A_VISTA:
            # Entra tudo no caixa no dia. Guarda o nº de parcelas só p/ crédito parcelado
            # (usado no cálculo do líquido com a taxa da parcela correspondente).
            parcelas_caixa = parcelas if forma == 'credito_parcelado' else None
            a_receber = round(valor_final - vale_usado, 2)   # já descontado o vale
            if a_receber > 0.01:
                cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,usuario_id,vendedora_nome,parcelas)
                    VALUES (%s,%s,'entrada',%s,%s,%s,%s,%s)""",
                    (f"Venda {cod} - {cliente_nome}", a_receber, forma, venda_id, usuario_id or None, vendedora_nome, parcelas_caixa))
        elif forma == 'crediario':
            # Só registra a entrada paga (se houver) — com a forma de pagamento REAL da entrada
            if entrada > 0:
                entrada_forma = request.form.get('entrada_forma', 'dinheiro').strip() or 'dinheiro'
                if entrada_forma == 'multiplo':
                    # Entrada dividida em várias formas (cada uma vira uma linha no caixa).
                    ent_pgs = parse_pagamentos(request.form.get('entrada_pagamentos'))
                    if not ent_pgs:
                        raise ValueError('Entrada dividida sem formas válidas.')
                    soma_e = round(sum(p['valor'] for p in ent_pgs), 2)
                    if abs(soma_e - round(entrada, 2)) > 0.02:
                        raise ValueError(f'A soma das formas da entrada (R$ {soma_e:.2f}) não bate com a entrada (R$ {entrada:.2f}).')
                    registrar_pagamentos_caixa(cur, ent_pgs, f"Entrada crediário - {cliente_nome}",
                        venda_id=venda_id, crediario_id=cred_id, usuario_id=usuario_id or None, vendedora_nome=vendedora_nome)
                else:
                    if entrada_forma not in FORMAS_A_VISTA: entrada_forma = 'dinheiro'
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
    cur.execute("""SELECT vi.*, (e.foto IS NOT NULL) AS tem_foto
                   FROM venda_itens vi LEFT JOIN estoque e ON e.id = vi.produto_id
                   WHERE vi.venda_id=%s ORDER BY vi.id""", (vid,))
    itens = [dict(i) for i in cur.fetchall()]
    crediario = None
    if venda.get('forma_pagamento') == 'crediario':
        cur.execute("SELECT * FROM crediarios WHERE venda_id=%s", (vid,))
        c = cur.fetchone()
        if c:
            crediario = dict(c)
            cur.execute("SELECT * FROM crediario_parcelas WHERE crediario_id=%s ORDER BY numero_parcela", (crediario['id'],))
            crediario['parcelas'] = [dict(p) for p in cur.fetchall()]
    # Formas do pagamento dividido (linhas do caixa à-vista desta venda)
    pagamentos = []
    if venda.get('forma_pagamento') == 'multiplo':
        cur.execute("""SELECT forma_pagamento, valor, parcelas FROM caixa
                       WHERE venda_id=%s AND crediario_id IS NULL AND tipo='entrada' ORDER BY id""", (vid,))
        pagamentos = [dict(p) for p in cur.fetchall()]
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u) for u in cur.fetchall()]
    # v141: histórico de trocas/devoluções desta venda (o que voltou e o que entrou), com foto.
    cur.execute("SELECT * FROM trocas WHERE venda_id=%s ORDER BY criado_em", (vid,))
    trocas = [dict(t) for t in cur.fetchall()]
    for t in trocas:
        cur.execute("""SELECT ti.*, (e.foto IS NOT NULL) AS tem_foto
                       FROM troca_itens ti LEFT JOIN estoque e ON e.id = ti.produto_id
                       WHERE ti.troca_id=%s ORDER BY ti.direcao DESC, ti.id""", (t['id'],))
        rows = [dict(i) for i in cur.fetchall()]
        t['devolvidos'] = [i for i in rows if i.get('direcao') == 'devolvido']
        t['novos'] = [i for i in rows if i.get('direcao') == 'novo']
    cur.close(); close_db(conn)
    ctx = get_ctx(); ctx.update(venda=venda, itens=itens, crediario=crediario, vendedoras=vendedoras,
                                pagamentos=pagamentos, trocas=trocas)
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
            cur.execute("SELECT codigo, valor_total, desconto, forma_pagamento, usuario_id, criado_em FROM vendas WHERE id=%s", (vid,))
            vrow = dict(cur.fetchone())
            forma_atual = vrow['forma_pagamento']
            valor_final = round(float(vrow['valor_total'] or 0) - float(vrow['desconto'] or 0), 2)
            cur.execute("""UPDATE vendas SET cliente_nome=%s, vendedora_nome=%s,
                          forma_pagamento=%s, parcelas=%s WHERE id=%s""",
                       (cliente_nome, vendedora_nome, forma_pagamento, parcelas, vid))
            # Reconcilia o caixa à-vista desta venda (preservando a data original do
            # lançamento). NÃO mexe em vendas de crediário, cuja entrada/parcelas têm
            # tratamento próprio com a forma de pagamento real.
            formas_a_vista = ['pix', 'dinheiro', 'debito', 'credito_vista', 'credito_parcelado', 'link']
            if forma_atual != 'crediario' and forma_pagamento != 'crediario':
                cur.execute("DELETE FROM caixa WHERE venda_id=%s AND crediario_id IS NULL AND tipo='entrada'", (vid,))
                if forma_pagamento == 'multiplo':
                    pagamentos = parse_pagamentos(request.form.get('pagamentos'))
                    if not pagamentos:
                        raise ValueError('Pagamento dividido sem formas válidas.')
                    soma = round(sum(p['valor'] for p in pagamentos), 2)
                    if abs(soma - valor_final) > 0.02:
                        raise ValueError(f'A soma das formas (R$ {soma:.2f}) não bate com o valor da venda (R$ {valor_final:.2f}).')
                    registrar_pagamentos_caixa(cur, pagamentos, f"Venda {vrow['codigo']} - {cliente_nome}",
                        venda_id=vid, usuario_id=vrow.get('usuario_id'), vendedora_nome=vendedora_nome,
                        criado_em=vrow.get('criado_em'))
                elif forma_pagamento in formas_a_vista:
                    parcelas_caixa = parcelas if forma_pagamento == 'credito_parcelado' else None
                    cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,usuario_id,vendedora_nome,parcelas,criado_em)
                        VALUES (%s,%s,'entrada',%s,%s,%s,%s,%s,%s)""",
                        (f"Venda {vrow['codigo']} - {cliente_nome}", valor_final, forma_pagamento, vid,
                         vrow.get('usuario_id'), vendedora_nome, parcelas_caixa, vrow.get('criado_em')))
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
    valor_final = round(float(venda.get('valor_total') or 0) - float(venda.get('desconto') or 0), 2)
    # Split atual (se a venda já for dividida) p/ pré-carregar o editor
    pagamentos = []
    if venda.get('forma_pagamento') == 'multiplo':
        cur.execute("""SELECT forma_pagamento, valor, parcelas FROM caixa
                       WHERE venda_id=%s AND crediario_id IS NULL AND tipo='entrada' ORDER BY id""", (vid,))
        pagamentos = [{'forma': r['forma_pagamento'], 'valor': float(r['valor'] or 0),
                       'parcelas': r['parcelas']} for r in cur.fetchall()]
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u)['nome'] for u in cur.fetchall()]
    cur.close(); close_db(conn)
    ctx = get_ctx(); ctx.update(venda=venda, vendedoras=vendedoras, valor_final=valor_final, pagamentos=pagamentos)
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
    cur.execute("""SELECT id, vendedora_nome, valor_total, desconto, forma_pagamento, criado_em, cliente_id
        FROM vendas WHERE DATE(criado_em) BETWEEN %s AND %s""", (data_inicio, data_fim))
    vendas_periodo = [dict(r) for r in cur.fetchall()]
    split_map = liquido_caixa_por_venda(cur, [v['id'] for v in vendas_periodo if v.get('forma_pagamento') == 'multiplo'])
    cur.close(); close_db(conn)
    # Agrega por vendedora calculando o líquido (bruto - desconto - taxa)
    taxa_cache = {}
    agg = {}
    for v in vendas_periodo:
        nome = v.get('vendedora_nome') or '—'
        bruto, desc, taxa, liq = _fin_venda(v, taxa_cache, split_map)
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
    # v142: código completo agora (ex.: PL5, SL12) — não tem mais um prefixo único "P"
    # pra completar sozinho.
    busca = request.args.get('ref', '').strip().upper()
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


@login_required
def trocar_venda(vid):
    """Troca/Devolução: devolve itens (voltam ao estoque) e/ou adiciona peças novas.
    Calcula a diferença — se a cliente paga a mais, recebe na forma escolhida (com taxa
    no caixa); se sobra crédito (ou devolução pura), gera um VALE no valor da sobra."""
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM vendas WHERE id=%s", (vid,))
        row = cur.fetchone()
        if not row:
            flash('Venda não encontrada.', 'erro'); return redirect(url_for('vendas'))
        venda = dict(row)
        if venda.get('forma_pagamento') == 'crediario':
            raise ValueError('Troca/devolução em venda no crediário ainda não é suportada por aqui.')
        devolver_ids = [int(x) for x in request.form.get('devolver_ids', '').split(',') if x.strip().isdigit()]
        novos = json.loads(request.form.get('novos', '[]'))
        if not devolver_ids and not novos:
            raise ValueError('Selecione itens para devolver e/ou adicione peças novas.')
        # ── Itens devolvidos: voltam ao estoque e saem da venda (guardando o snapshot p/ registro) ──
        valor_devolvido = 0.0
        itens_devolvidos = []
        if devolver_ids:
            cur.execute("SELECT * FROM venda_itens WHERE id = ANY(%s) AND venda_id=%s", (devolver_ids, vid))
            for it in [dict(i) for i in cur.fetchall()]:
                valor_devolvido += float(it['valor_total'] or 0)
                itens_devolvidos.append(it)   # snapshot antes de apagar
                if it.get('produto_id'):
                    cur.execute("UPDATE estoque SET quantidade=quantidade+%s WHERE id=%s", (int(it['quantidade']), it['produto_id']))
                cur.execute("DELETE FROM venda_itens WHERE id=%s", (it['id'],))
        # ── Peças novas: entram na venda e saem do estoque ──
        valor_novos = 0.0
        itens_novos = []
        for it in novos:
            pid = it.get('produto_id'); qtd = int(it.get('quantidade', 1)); vu = float(it.get('valor_unitario', 0))
            valor_novos += vu * qtd
            itens_novos.append({'produto_id': pid, 'codigo': it.get('codigo'), 'modelo': it.get('modelo'),
                                'descricao': it.get('descricao'), 'tamanho': it.get('tamanho'),
                                'valor_unitario': vu, 'quantidade': qtd, 'valor_total': vu * qtd})
            cur.execute("""INSERT INTO venda_itens (venda_id,produto_id,codigo_produto,modelo,descricao,tamanho,valor_unitario,quantidade,valor_total)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (vid, pid or None, it.get('codigo'), it.get('modelo'), it.get('descricao'), it.get('tamanho'), vu, qtd, vu * qtd))
            if pid:
                bloquear_estoque_negativo(cur, pid, qtd)
        valor_devolvido = round(valor_devolvido, 2)
        valor_novos = round(valor_novos, 2)
        novo_total = round(float(venda['valor_total'] or 0) - valor_devolvido + valor_novos, 2)
        dif = round(valor_novos - valor_devolvido, 2)
        extra = ''
        forma_dif = None
        vale_id_gerado = None; vale_cod_gerado = None
        if dif > 0.01:
            # Cliente paga a diferença — entra no caixa com a forma escolhida (com taxa).
            forma = request.form.get('forma_pagamento', '').strip()
            if forma not in FORMAS_A_VISTA:
                raise ValueError('Escolha a forma de pagamento da diferença.')
            forma_dif = forma
            parcelas_caixa = (int(request.form.get('parcelas', 0) or 0) or None) if forma == 'credito_parcelado' else None
            cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,vendedora_nome,parcelas)
                VALUES (%s,%s,'entrada',%s,%s,%s,%s)""",
                (f"Troca {venda['codigo']} - diferença ({forma.replace('_',' ')})", dif, forma, vid, venda.get('vendedora_nome'), parcelas_caixa))
            extra = f"Diferença de R$ {dif:.2f} recebida ({forma.replace('_',' ')})."
        elif dif < -0.01:
            credito = round(-dif, 2)
            vale_id_gerado, vale_cod_gerado = gerar_vale(cur, cliente_id=venda.get('cliente_id'), cliente_nome=venda.get('cliente_nome'),
                                        valor=credito, venda_origem=vid, observacao=f"Troca/devolução da venda {venda['codigo']}")
            extra = f"Vale {vale_cod_gerado} de R$ {credito:.2f} gerado para {venda.get('cliente_nome') or 'a cliente'}."
        # ── Registro da troca/devolução (auditoria) — o que voltou e o que entrou ──
        cur.execute("""INSERT INTO trocas (venda_id,venda_codigo,valor_devolvido,valor_novos,diferenca,
                       forma_pagamento,vale_id,vale_codigo,usuario_id,usuario_nome)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (vid, venda['codigo'], valor_devolvido, valor_novos, dif, forma_dif,
             vale_id_gerado, vale_cod_gerado, session.get('uid'), session.get('nome')))
        troca_id = cur.fetchone()['id']
        for it in itens_devolvidos:
            cur.execute("""INSERT INTO troca_itens (troca_id,direcao,produto_id,codigo_produto,modelo,descricao,tamanho,valor_unitario,quantidade,valor_total)
                VALUES (%s,'devolvido',%s,%s,%s,%s,%s,%s,%s,%s)""",
                (troca_id, it.get('produto_id'), it.get('codigo_produto'), it.get('modelo'), it.get('descricao'),
                 it.get('tamanho'), it.get('valor_unitario'), it.get('quantidade'), it.get('valor_total')))
        for it in itens_novos:
            cur.execute("""INSERT INTO troca_itens (troca_id,direcao,produto_id,codigo_produto,modelo,descricao,tamanho,valor_unitario,quantidade,valor_total)
                VALUES (%s,'novo',%s,%s,%s,%s,%s,%s,%s,%s)""",
                (troca_id, it.get('produto_id'), it.get('codigo'), it.get('modelo'), it.get('descricao'),
                 it.get('tamanho'), it.get('valor_unitario'), it.get('quantidade'), it.get('valor_total')))
        # Líquido passa a ser calculado pelas linhas do caixa (forma interna 'multiplo'), mas a
        # forma ORIGINAL é preservada p/ exibição (não vira "Dividido" na lista). v141.
        forma_atual = venda.get('forma_pagamento') or ''
        forma_orig = venda.get('forma_original') or (forma_atual if forma_atual != 'multiplo' else None)
        cur.execute("UPDATE vendas SET valor_total=%s, forma_pagamento='multiplo', forma_original=%s, trocada=TRUE WHERE id=%s",
                    (novo_total, forma_orig, vid))
        audit_log(cur, 'TROCA_VENDA', 'vendas', vid,
                  {'codigo': venda['codigo'], 'devolvido': valor_devolvido, 'novos': valor_novos, 'diferenca': dif})
        conn.commit()
        flash(f"Troca/devolução concluída na venda {venda['codigo']}. {extra}".strip(), 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('ficha_venda', vid=vid))


def register(app):
    app.add_url_rule('/vendas', 'vendas', vendas)
    app.add_url_rule('/vendas/nova', 'nova_venda', nova_venda, methods=['POST'])
    app.add_url_rule('/vendas/<int:vid>/troca', 'trocar_venda', trocar_venda, methods=['POST'])
    app.add_url_rule('/vendas/<int:vid>', 'ficha_venda', ficha_venda)
    app.add_url_rule('/vendas/<int:vid>/excluir', 'excluir_venda', excluir_venda, methods=['POST'])
    app.add_url_rule('/vendas/<int:vid>/editar', 'editar_venda', editar_venda, methods=['GET', 'POST'])
    app.add_url_rule('/vendas/ranking', 'ranking_vendedoras', ranking_vendedoras)
    app.add_url_rule('/vendas/buscar-ref', 'buscar_ref', buscar_ref)
    app.add_url_rule('/vendas/buscar-cliente', 'buscar_cliente', buscar_cliente)
