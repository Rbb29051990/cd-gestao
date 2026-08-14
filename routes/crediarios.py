"""Rotas de Crediários: dashboard agrupado por cliente (em dia × atraso, faixas,
top devedores) e pagamento de parcela com forma de pagamento real no caixa."""
import math
import calendar
from datetime import date as date_type
from collections import OrderedDict
from flask import render_template, request, redirect, url_for, flash, jsonify
from db import get_db, close_db
from config import hoje_app, fim_mes_app
from auth import login_required, get_ctx
from utils import get_taxa_vigente, parse_pagamentos, registrar_pagamentos_caixa


def _add_months(d, m):
    month = d.month - 1 + m
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date_type(year, month, day)


@login_required
def crediarios():
    # Pré-fixa o período no mês vigente (1º dia → último dia), igual às demais abas.
    # O botão "Todos" envia os campos vazios, caindo na listagem sem filtro.
    data_inicio = request.args.get('data_inicio', hoje_app().strftime('%Y-01-01'))
    data_fim = request.args.get('data_fim', hoje_app().strftime('%Y-%m-%d'))
    conn = get_db(); cur = conn.cursor()
    if data_inicio and data_fim:
        cur.execute("""SELECT c.*,v.codigo as codigo_venda,v.criado_em as data_venda
            FROM crediarios c LEFT JOIN vendas v ON v.id=c.venda_id
            WHERE (c.venda_id IS NULL OR DATE(v.criado_em) BETWEEN %s AND %s)
            ORDER BY c.status,c.criado_em DESC""", (data_inicio, data_fim))
    else:
        cur.execute("""SELECT c.*,v.codigo as codigo_venda,v.criado_em as data_venda
            FROM crediarios c LEFT JOIN vendas v ON v.id=c.venda_id ORDER BY c.status,c.criado_em DESC""")
    raw = [dict(c) for c in cur.fetchall()]
    for c in raw:
        cur.execute("SELECT * FROM crediario_parcelas WHERE crediario_id=%s ORDER BY numero_parcela", (c['id'],))
        c['parcelas'] = [dict(p) for p in cur.fetchall()]
        # GARANTIA: todo crediário com saldo em aberto precisa ter uma parcela em
        # aberto (senão o botão "Receber" não aparece). Se faltar, cria na hora —
        # isto conserta sozinho qualquer crediário que ficou travado.
        saldo_dev = float(c['saldo_devedor'] or 0)
        tem_aberta = any(not p.get('pago') for p in c['parcelas'])
        if saldo_dev > 0.01 and not tem_aberta:
            prox = max([p['numero_parcela'] for p in c['parcelas']], default=0) + 1
            cur.execute("""INSERT INTO crediario_parcelas
                (crediario_id,numero_parcela,data_vencimento,valor,pago)
                VALUES (%s,%s,%s,%s,FALSE) RETURNING *""", (c['id'], prox, hoje_app(), saldo_dev))
            c['parcelas'].append(dict(cur.fetchone()))
            conn.commit()
        # Forma de pagamento de cada parcela paga (gravada no caixa ao receber)
        cur.execute("""SELECT parcela_id, forma_pagamento, parcelas FROM caixa
                       WHERE crediario_id=%s AND parcela_id IS NOT NULL ORDER BY id""", (c['id'],))
        formas = {r['parcela_id']: r for r in cur.fetchall()}
        for p in c['parcelas']:
            cx = formas.get(p['id'])
            if cx:
                p['forma_pagamento'] = cx['forma_pagamento']
                p['forma_parcelas'] = cx['parcelas']
    # Agrupar por cliente
    agrupado = OrderedDict()
    for c in raw:
        nome = c['cliente_nome']
        if nome not in agrupado:
            agrupado[nome] = {'cliente_nome': nome, 'vendas': [], 'total': 0, 'pago': 0, 'saldo': 0}
        agrupado[nome]['vendas'].append(c)
        agrupado[nome]['total'] += float(c['valor_total'])
        agrupado[nome]['pago']  += float(c['valor_total']) - float(c['saldo_devedor'])
        agrupado[nome]['saldo'] += float(c['saldo_devedor'])
    clientes = list(agrupado.values())
    # ── Análise de atraso e distribuição por cliente (para os gráficos) ──
    hoje = hoje_app()
    for cli in clientes:
        atraso_val = 0.0; atraso_qtd = 0; dias_max = 0; prox_venc = None
        for c in cli['vendas']:
            for p in c['parcelas']:
                if not p.get('pago'):
                    venc = p.get('data_vencimento')
                    if venc and venc < hoje:
                        atraso_val += float(p['valor'] or 0); atraso_qtd += 1
                        dias_max = max(dias_max, (hoje - venc).days)
                    elif venc and (prox_venc is None or venc < prox_venc):
                        prox_venc = venc
        cli['atraso_valor'] = round(atraso_val, 2)
        cli['atraso_qtd'] = atraso_qtd
        cli['dias_atraso'] = dias_max
        cli['em_atraso'] = atraso_val > 0
        cli['prox_venc'] = prox_venc
    clientes_abertos = [c for c in clientes if c['saldo'] > 0.01]
    clientes_atraso = sorted([c for c in clientes_abertos if c['em_atraso']],
                             key=lambda c: c['atraso_valor'], reverse=True)
    top_devedores = sorted(clientes_abertos, key=lambda c: c['saldo'], reverse=True)[:8]
    valor_atraso = round(sum(c['atraso_valor'] for c in clientes_atraso), 2)
    valor_em_dia = round(sum(c['saldo'] for c in clientes_abertos) - valor_atraso, 2)
    # Faixas de valor em aberto (distribuição de clientes)
    faixas = [('Até R$ 200', 0, 200), ('R$ 200–500', 200, 500),
              ('R$ 500–1.000', 500, 1000), ('Acima de R$ 1.000', 1000, float('inf'))]
    faixas_dist = []
    for lbl, lo, hi in faixas:
        grp = [c for c in clientes_abertos if lo < c['saldo'] <= hi]
        faixas_dist.append({'label': lbl, 'qtd': len(grp),
                            'valor': round(sum(c['saldo'] for c in grp), 2)})
    cur.execute("SELECT COALESCE(SUM(saldo_devedor),0) as t FROM crediarios WHERE status='aberto'")
    total_aberto = float(cur.fetchone()['t'])
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u) for u in cur.fetchall()]
    cur.close(); close_db(conn)
    taxa_vigente = get_taxa_vigente()
    ctx = get_ctx(); ctx.update(clientes=clientes, total_aberto=total_aberto, vendedoras=vendedoras,
        taxa_vigente=taxa_vigente, data_inicio=data_inicio, data_fim=data_fim,
        n_abertos=len(clientes_abertos), n_atraso=len(clientes_atraso),
        valor_atraso=valor_atraso, valor_em_dia=valor_em_dia,
        clientes_atraso=clientes_atraso, top_devedores=top_devedores, faixas_dist=faixas_dist)
    return render_template('crediarios.html', **ctx)


@login_required
def pagar_parcela(cid, pid):
    vendedora_nome = request.form.get('vendedora_nome', '').strip()
    valor_pago = float(request.form.get('valor_pago', 0) or 0)
    forma_pg = request.form.get('forma_pagamento', 'dinheiro').strip()
    parcelas_caixa = None
    if forma_pg == 'credito_parcelado':
        try: parcelas_caixa = int(request.form.get('parcelas_cartao', 0) or 0) or None
        except ValueError: parcelas_caixa = None
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM crediarios WHERE id=%s", (cid,))
        cred = dict(cur.fetchone())
        cur.execute("UPDATE crediario_parcelas SET pago=TRUE,valor=%s,data_pagamento=CURRENT_DATE WHERE id=%s", (valor_pago, pid))
        novo_saldo = round(float(cred['saldo_devedor']) - valor_pago, 2)
        if novo_saldo <= 0.01:
            cur.execute("DELETE FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE", (cid,))
            cur.execute("UPDATE crediarios SET saldo_devedor=0,status='quitado' WHERE id=%s", (cid,))
        else:
            cur.execute("SELECT id FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE ORDER BY numero_parcela", (cid,))
            rest = cur.fetchall()
            if rest:
                vp = math.ceil((novo_saldo / len(rest)) * 100) / 100
                for i, p in enumerate(rest):
                    v = round(novo_saldo - vp * (len(rest) - 1), 2) if i == len(rest) - 1 else vp
                    cur.execute("UPDATE crediario_parcelas SET valor=%s WHERE id=%s", (v, p['id']))
            else:
                # Recebimento parcial da última parcela em aberto: ainda sobra saldo,
                # mas não há parcela para recebê-lo. Cria uma nova para o restante.
                cur.execute("SELECT COALESCE(MAX(numero_parcela),0)+1 AS n FROM crediario_parcelas WHERE crediario_id=%s", (cid,))
                prox = cur.fetchone()['n']
                cur.execute("""INSERT INTO crediario_parcelas
                    (crediario_id,numero_parcela,data_vencimento,valor,pago)
                    VALUES (%s,%s,%s,%s,FALSE)""", (cid, prox, hoje_app(), novo_saldo))
            cur.execute("UPDATE crediarios SET saldo_devedor=%s WHERE id=%s", (novo_saldo, cid))
        # Gravar no caixa com a forma de pagamento real (para taxas serem aplicadas corretamente)
        if forma_pg == 'multiplo':
            # Recebimento dividido: cada forma vira uma linha no caixa (com sua taxa).
            pagamentos = parse_pagamentos(request.form.get('pagamentos'))
            if not pagamentos:
                raise ValueError('Pagamento dividido sem formas válidas.')
            soma = round(sum(p['valor'] for p in pagamentos), 2)
            if abs(soma - round(valor_pago, 2)) > 0.02:
                raise ValueError(f'A soma das formas (R$ {soma:.2f}) não bate com o valor recebido (R$ {valor_pago:.2f}).')
            registrar_pagamentos_caixa(cur, pagamentos, f"Crediário - {cred['cliente_nome']}",
                crediario_id=cid, parcela_id=pid, vendedora_nome=vendedora_nome)
        else:
            descr = f"Crediário - {cred['cliente_nome']} ({forma_pg.replace('_',' ')})"
            cur.execute("INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,crediario_id,parcela_id,vendedora_nome,parcelas) VALUES (%s,%s,'entrada',%s,%s,%s,%s,%s)",
                (descr, valor_pago, forma_pg, cid, pid, vendedora_nome, parcelas_caixa))
        conn.commit(); flash('Pagamento registrado!', 'ok')
    except Exception as e: conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('crediarios'))


@login_required
def corrigir_forma_parcela(cid, pid):
    """Corrige a forma de pagamento de uma parcela JÁ recebida, atualizando o
    lançamento no caixa (e, por consequência, a Visão Geral). Não muda o valor."""
    forma = request.form.get('forma_pagamento', '').strip()
    formas_validas = ['dinheiro', 'pix', 'debito', 'credito_vista', 'credito_parcelado', 'link', 'multiplo']
    if forma not in formas_validas:
        flash('Forma de pagamento inválida.', 'erro'); return redirect(url_for('crediarios'))
    # nº de parcelas do cartão — só faz sentido no crédito parcelado (puxa a taxa da parcela)
    if forma == 'credito_parcelado':
        try: parc = int(request.form.get('parcelas_cartao', 0) or 0) or None
        except ValueError: parc = None
    else:
        parc = None
    conn = get_db(); cur = conn.cursor()
    try:
        if forma == 'multiplo':
            # Converte o recebimento desta parcela em pagamento dividido: substitui a(s)
            # linha(s) do caixa por uma por forma, preservando a data do lançamento.
            pagamentos = parse_pagamentos(request.form.get('pagamentos'))
            if not pagamentos:
                raise ValueError('Pagamento dividido sem formas válidas.')
            cur.execute("""SELECT p.valor, c.cliente_nome FROM crediario_parcelas p
                           JOIN crediarios c ON c.id=p.crediario_id
                           WHERE p.id=%s AND p.crediario_id=%s""", (pid, cid))
            prow = cur.fetchone()
            if not prow:
                flash('Parcela não encontrada.', 'erro'); return redirect(url_for('crediarios'))
            valor_parc = round(float(prow['valor'] or 0), 2)
            soma = round(sum(p['valor'] for p in pagamentos), 2)
            if abs(soma - valor_parc) > 0.02:
                raise ValueError(f'A soma das formas (R$ {soma:.2f}) não bate com o valor recebido (R$ {valor_parc:.2f}).')
            cur.execute("""SELECT criado_em FROM caixa WHERE crediario_id=%s AND parcela_id=%s
                           AND venda_id IS NULL ORDER BY criado_em DESC LIMIT 1""", (cid, pid))
            crow = cur.fetchone()
            criado = crow['criado_em'] if crow else None
            cur.execute("DELETE FROM caixa WHERE crediario_id=%s AND parcela_id=%s AND venda_id IS NULL", (cid, pid))
            registrar_pagamentos_caixa(cur, pagamentos, f"Crediário - {prow['cliente_nome']}",
                crediario_id=cid, parcela_id=pid, criado_em=criado)
            conn.commit()
            flash('Forma de pagamento da parcela corrigida (dividido) no caixa!', 'ok')
            return redirect(url_for('crediarios'))
        # Caminho normal: lançamento marcado com este parcela_id
        cur.execute("""UPDATE caixa SET forma_pagamento=%s, parcelas=%s
                       WHERE crediario_id=%s AND parcela_id=%s AND venda_id IS NULL""",
                    (forma, parc, cid, pid))
        if cur.rowcount == 0:
            # Legado: pagamentos antigos não gravavam parcela_id — corrige a entrada
            # de parcela mais recente do crediário que ainda não tem parcela_id.
            cur.execute("""UPDATE caixa SET forma_pagamento=%s, parcelas=%s
                           WHERE id = (SELECT id FROM caixa
                                       WHERE crediario_id=%s AND venda_id IS NULL AND parcela_id IS NULL
                                       ORDER BY criado_em DESC LIMIT 1)""",
                        (forma, parc, cid))
        if cur.rowcount == 0:
            flash('Não encontrei o lançamento desta parcela no caixa para corrigir.', 'erro')
        else:
            flash('Forma de pagamento da parcela corrigida no caixa!', 'ok')
        conn.commit()
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('crediarios'))


@login_required
def editar_crediario(cid):
    valor_total  = float(request.form.get('valor_total', 0) or 0)
    saldo_devedor = float(request.form.get('saldo_devedor', 0) or 0)
    if valor_total <= 0:
        flash('Valor total inválido.', 'erro')
        return redirect(url_for('crediarios'))
    conn = get_db(); cur = conn.cursor()
    try:
        status = 'aberto' if saldo_devedor > 0.01 else 'quitado'
        cur.execute("UPDATE crediarios SET valor_total=%s, saldo_devedor=%s, status=%s WHERE id=%s",
                    (valor_total, saldo_devedor, status, cid))
        if saldo_devedor > 0.01:
            cur.execute("SELECT id FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE ORDER BY numero_parcela", (cid,))
            rest = cur.fetchall()
            if rest:
                n = len(rest)
                vp = round(saldo_devedor / n, 2)
                for i, p in enumerate(rest):
                    v = round(saldo_devedor - vp * (n - 1), 2) if i == n - 1 else vp
                    cur.execute("UPDATE crediario_parcelas SET valor=%s WHERE id=%s", (v, p['id']))
            else:
                # Não há parcela em aberto para abrigar o saldo (ex.: a última foi
                # recebida parcialmente). Cria uma nova parcela para o saldo informado,
                # destravando o recebimento do restante.
                cur.execute("SELECT COALESCE(MAX(numero_parcela),0)+1 AS n FROM crediario_parcelas WHERE crediario_id=%s", (cid,))
                prox = cur.fetchone()['n']
                cur.execute("""INSERT INTO crediario_parcelas
                    (crediario_id,numero_parcela,data_vencimento,valor,pago)
                    VALUES (%s,%s,%s,%s,FALSE)""", (cid, prox, hoje_app(), saldo_devedor))
        conn.commit()
        flash('Crediário atualizado!', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('crediarios'))


@login_required
def excluir_crediario(cid):
    """Exclui o crediário inteiro (e suas parcelas em cascata). Para lançamentos
    feitos por engano. Lançamentos de caixa já recebidos NÃO são apagados."""
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM crediarios WHERE id=%s", (cid,))
        if not cur.fetchone():
            flash('Crediário não encontrado.', 'erro')
            return redirect(url_for('crediarios'))
        # crediario_parcelas tem ON DELETE CASCADE -> some junto
        cur.execute("DELETE FROM crediarios WHERE id=%s", (cid,))
        conn.commit()
        flash('Crediário excluído.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('crediarios'))


@login_required
def excluir_parcela(cid, pid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM crediario_parcelas WHERE id=%s AND crediario_id=%s AND pago=FALSE", (pid, cid))
        if not cur.fetchone():
            flash('Parcela não encontrada ou já está paga.', 'erro')
            return redirect(url_for('crediarios'))
        cur.execute("DELETE FROM crediario_parcelas WHERE id=%s", (pid,))
        cur.execute("SELECT saldo_devedor FROM crediarios WHERE id=%s", (cid,))
        saldo = float(cur.fetchone()['saldo_devedor'])
        cur.execute("SELECT id FROM crediario_parcelas WHERE crediario_id=%s AND pago=FALSE ORDER BY numero_parcela", (cid,))
        rest = cur.fetchall()
        if rest and saldo > 0.01:
            n = len(rest)
            vp = round(saldo / n, 2)
            for i, p in enumerate(rest):
                v = round(saldo - vp * (n - 1), 2) if i == n - 1 else vp
                cur.execute("UPDATE crediario_parcelas SET valor=%s WHERE id=%s", (v, p['id']))
        conn.commit()
        flash('Parcela excluída.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('crediarios'))


@login_required
def estornar_parcela(cid, pid):
    """Desfaz o pagamento de uma parcela: volta pago=FALSE, restaura saldo e remove do caixa."""
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM crediario_parcelas WHERE id=%s AND crediario_id=%s", (pid, cid))
        p = cur.fetchone()
        if not p or not p['pago']:
            flash('Parcela não encontrada ou já está em aberto.', 'erro')
            return redirect(url_for('crediarios'))

        valor_estorno = float(p['valor'] or 0)

        # Reverte a parcela
        cur.execute("""UPDATE crediario_parcelas SET pago=FALSE, data_pagamento=NULL
                       WHERE id=%s""", (pid,))

        # Restaura saldo devedor e reabre o crediário se estava quitado
        cur.execute("""UPDATE crediarios
                       SET saldo_devedor = saldo_devedor + %s, status = 'aberto'
                       WHERE id=%s""", (valor_estorno, cid))

        # Remove lançamento(s) do caixa desta parcela — pagamento dividido tem várias
        # linhas com o mesmo parcela_id, então apaga TODAS.
        cur.execute("""DELETE FROM caixa
            WHERE crediario_id=%s AND parcela_id=%s AND venda_id IS NULL""", (cid, pid))
        if cur.rowcount == 0:
            # Legado: sem parcela_id gravado — remove a entrada mais recente do crediário
            cur.execute("""DELETE FROM caixa WHERE id = (
                SELECT id FROM caixa
                WHERE crediario_id=%s AND venda_id IS NULL AND parcela_id IS NULL
                ORDER BY criado_em DESC LIMIT 1)""", (cid,))

        conn.commit()
        flash('Pagamento estornado com sucesso.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('crediarios'))


@login_required
def buscar_cliente_cred():
    """v143: busca de cliente pro autocomplete do 'Novo crediário'. Rota própria (em
    vez de reaproveitar /vendas/buscar-cliente) pra não depender da permissão da aba
    Vendas — um usuário pode ter acesso a Crediários sem ter acesso a Vendas."""
    q = request.args.get('q', '').strip()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id,codigo,nome FROM clientes WHERE ativo=TRUE AND (LOWER(nome) LIKE %s OR codigo ILIKE %s) ORDER BY nome LIMIT 8",
        (f'%{q.lower()}%', f'%{q}%'))
    lista = [dict(c) for c in cur.fetchall()]
    cur.close(); close_db(conn)
    return jsonify({'clientes': lista})


@login_required
def novo_crediario_avulso():
    cliente_nome = request.form.get('cliente_nome', '').strip()
    observacao   = request.form.get('observacao', '').strip()
    valor_total  = float(request.form.get('valor_total', 0) or 0)
    entrada      = float(request.form.get('entrada', 0) or 0)
    num_parcelas = max(1, int(request.form.get('num_parcelas', 1) or 1))
    data_primeira = request.form.get('data_primeira', '').strip()

    if not cliente_nome or valor_total <= 0:
        flash('Informe o cliente e o valor total.', 'erro')
        return redirect(url_for('crediarios'))

    saldo = round(valor_total - entrada, 2)
    if saldo <= 0:
        flash('A entrada já cobre o valor total — nada a lançar como devedor.', 'erro')
        return redirect(url_for('crediarios'))

    try:
        primeira = date_type.fromisoformat(data_primeira) if data_primeira else hoje_app()
    except ValueError:
        primeira = hoje_app()

    conn = get_db(); cur = conn.cursor()
    try:
        # v143: se o cliente foi escolhido na lista de sugestões, o id vem direto no
        # form — corrige o bug de não "puxar" o cliente (antes só existia o match por
        # NOME EXATO, que falhava silenciosamente pra qualquer nome digitado diferente
        # do cadastrado). Sem seleção (cliente ainda não cadastrado), cai no match antigo.
        cliente_id_form = request.form.get('cliente_id', '').strip()
        if cliente_id_form.isdigit():
            cur.execute("SELECT id, nome FROM clientes WHERE id=%s", (int(cliente_id_form),))
            row = cur.fetchone()
            cliente_id = row['id'] if row else None
            if row:
                cliente_nome = row['nome']
        else:
            cur.execute("SELECT id FROM clientes WHERE LOWER(nome)=LOWER(%s) LIMIT 1", (cliente_nome,))
            row = cur.fetchone()
            cliente_id = row['id'] if row else None

        cur.execute("""INSERT INTO crediarios
            (venda_id,cliente_id,cliente_nome,valor_total,entrada,saldo_devedor,status,observacao)
            VALUES (NULL,%s,%s,%s,%s,%s,'aberto',%s) RETURNING id""",
            (cliente_id, cliente_nome, valor_total, entrada, saldo, observacao or None))
        cred_id = cur.fetchone()['id']

        valor_parcela = round(saldo / num_parcelas, 2)
        for i in range(num_parcelas):
            venc = _add_months(primeira, i)
            v = round(saldo - valor_parcela * (num_parcelas - 1), 2) if i == num_parcelas - 1 else valor_parcela
            cur.execute("""INSERT INTO crediario_parcelas
                (crediario_id,numero_parcela,data_vencimento,valor,pago)
                VALUES (%s,%s,%s,%s,FALSE)""", (cred_id, i + 1, venc, v))

        conn.commit()
        flash('Crediário lançado com sucesso!', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('crediarios'))


def register(app):
    app.add_url_rule('/crediarios', 'crediarios', crediarios)
    app.add_url_rule('/crediarios/buscar-cliente', 'buscar_cliente_cred', buscar_cliente_cred)
    app.add_url_rule('/crediarios/avulso/novo', 'novo_crediario_avulso', novo_crediario_avulso, methods=['POST'])
    app.add_url_rule('/crediarios/<int:cid>/editar', 'editar_crediario', editar_crediario, methods=['POST'])
    app.add_url_rule('/crediarios/<int:cid>/excluir', 'excluir_crediario', excluir_crediario, methods=['POST'])
    app.add_url_rule('/crediarios/<int:cid>/parcela/<int:pid>/excluir', 'excluir_parcela', excluir_parcela, methods=['POST'])
    app.add_url_rule('/crediarios/<int:cid>/parcela/<int:pid>/estornar', 'estornar_parcela', estornar_parcela, methods=['POST'])
    app.add_url_rule('/crediarios/<int:cid>/parcela/<int:pid>/pagar', 'pagar_parcela', pagar_parcela, methods=['POST'])
    app.add_url_rule('/crediarios/<int:cid>/parcela/<int:pid>/corrigir-forma', 'corrigir_forma_parcela', corrigir_forma_parcela, methods=['POST'])
