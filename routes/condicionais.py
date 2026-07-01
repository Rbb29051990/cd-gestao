"""Rotas de Condicional / Transferência: dashboard com período, nova, ficha,
gerar venda (peças que ficaram), devolução, confirmação de transferência e exclusão."""
import os
import json
from datetime import date
from flask import render_template, request, redirect, url_for, flash
from db import get_db, close_db
from config import hoje_app, fim_mes_app
from auth import login_required, get_ctx, pode_excluir
from utils import parse_brl, parse_pagamentos, registrar_pagamentos_caixa

# Destinos possíveis de uma transferência (as lojas do grupo). Configurável por
# env LOJAS_TRANSFERENCIA (separado por vírgula); padrão = as duas lojas atuais.
LOJAS_TRANSFERENCIA = [s.strip() for s in os.environ.get(
    'LOJAS_TRANSFERENCIA', 'CD Plus Size,CD Slim').split(',') if s.strip()]


@login_required
def condicionais():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u) for u in cur.fetchall()]
    cur.execute("SELECT id,codigo,nome,crediario FROM clientes WHERE ativo=TRUE ORDER BY nome")
    clientes_lista = [dict(c) for c in cur.fetchall()]
    hoje = hoje_app()
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-01-01'))
    data_fim    = request.args.get('data_fim',    hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-01-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = hoje.strftime('%Y-%m-%d')
    # Abertas no período (o filtro do topo conecta a tela toda)
    cur.execute("""SELECT c.*,
        COALESCE((SELECT SUM(quantidade) FROM condicional_itens WHERE condicional_id=c.id AND status='pendente'),0) as qtd_pecas
        FROM condicionais c WHERE c.status='aberta' AND DATE(c.criado_em) BETWEEN %s AND %s
        ORDER BY c.criado_em""", (data_inicio, data_fim))
    abertas = [dict(r) for r in cur.fetchall()]
    for c in abertas:
        c['dias'] = (hoje - c['criado_em'].date()).days
    # Histórico (filtrado pelo período)
    cur.execute("""SELECT c.*,
        COALESCE((SELECT SUM(quantidade) FROM condicional_itens WHERE condicional_id=c.id),0) as qtd_pecas
        FROM condicionais c WHERE c.status<>'aberta' AND DATE(c.criado_em) BETWEEN %s AND %s
        ORDER BY c.criado_em DESC""", (data_inicio, data_fim))
    historico = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)),0) as n FROM condicionais WHERE codigo ~ '^C[0-9]+$'")
    next_n = cur.fetchone()['n'] + 1
    cur.close(); close_db(conn)
    # ── KPIs / agregações ──
    total_aberto = round(sum(float(c['valor_total'] or 0) for c in abertas), 2)
    n_abertas = len(abertas)
    n_pecas = sum(int(c['qtd_pecas'] or 0) for c in abertas)
    cond_aberto  = round(sum(float(c['valor_total'] or 0) for c in abertas if c['tipo'] == 'condicional'), 2)
    transf_aberto = round(sum(float(c['valor_total'] or 0) for c in abertas if c['tipo'] == 'transferencia'), 2)
    n_cond  = sum(1 for c in abertas if c['tipo'] == 'condicional')
    n_transf = sum(1 for c in abertas if c['tipo'] == 'transferencia')
    # Aging — mais tempo em aberto
    aging = sorted(abertas, key=lambda c: c['dias'], reverse=True)[:8]
    # Maiores valores por cliente/destino
    por_cliente = {}
    for c in abertas:
        k = c['cliente_nome'] or '—'
        por_cliente[k] = por_cliente.get(k, 0.0) + float(c['valor_total'] or 0)
    maiores = sorted([{'nome': k, 'valor': round(v, 2)} for k, v in por_cliente.items()],
                     key=lambda x: x['valor'], reverse=True)[:8]
    ctx = get_ctx()
    ctx.update(vendedoras=vendedoras, clientes=clientes_lista, abertas=abertas, historico=historico,
               data_inicio=data_inicio, data_fim=data_fim, next_cod=f"C{next_n}",
               total_aberto=total_aberto, n_abertas=n_abertas, n_pecas=n_pecas,
               cond_aberto=cond_aberto, transf_aberto=transf_aberto, n_cond=n_cond, n_transf=n_transf,
               aging=aging, maiores=maiores, lojas_transf=LOJAS_TRANSFERENCIA)
    return render_template('condicionais.html', **ctx)


@login_required
def nova_condicional():
    conn = get_db(); cur = conn.cursor()
    try:
        tipo = request.form.get('tipo', 'condicional').strip().lower()
        if tipo not in ('condicional', 'transferencia'): tipo = 'condicional'
        usuario_id = request.form.get('usuario_id')
        vendedora_nome = request.form.get('vendedora_nome', '').strip()
        if tipo == 'transferencia':
            destino = request.form.get('destino_transf', '').strip()
            if destino not in LOJAS_TRANSFERENCIA:
                destino = LOJAS_TRANSFERENCIA[0] if LOJAS_TRANSFERENCIA else 'Outra loja'
            cliente_id = None; cliente_nome = destino
        else:
            cliente_id = request.form.get('cliente_id') or None
            cliente_nome = request.form.get('cliente_nome', '').strip()
        obs = request.form.get('observacao', '').strip() or None
        itens = json.loads(request.form.get('itens', '[]'))
        if not itens:
            raise Exception('Adicione pelo menos um item.')
        if tipo == 'condicional' and not cliente_nome:
            raise Exception('Informe o cliente da condicional.')
        cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)),0) as n FROM condicionais WHERE codigo ~ '^C[0-9]+$'")
        n = cur.fetchone()['n']; cod = f"C{n+1}"
        total = sum(float(i.get('valor_unitario', 0)) * int(i.get('quantidade', 1)) for i in itens)
        cur.execute("""INSERT INTO condicionais (codigo,tipo,cliente_id,cliente_nome,usuario_id,vendedora_nome,valor_total,observacao)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (cod, tipo, cliente_id, cliente_nome, usuario_id or None, vendedora_nome, total, obs))
        cid = cur.fetchone()['id']
        for it in itens:
            pid = it.get('produto_id'); qtd = int(it.get('quantidade', 1)); vu = float(it.get('valor_unitario', 0))
            if pid:
                cur.execute("SELECT quantidade FROM estoque WHERE id=%s", (pid,))
                row = cur.fetchone(); disp = int(row['quantidade']) if row else 0
                if qtd > disp:
                    raise Exception(f"Saldo insuficiente para {it.get('codigo')} (disponível: {disp}).")
                cur.execute("UPDATE estoque SET quantidade=quantidade-%s, reservado=COALESCE(reservado,0)+%s WHERE id=%s", (qtd, qtd, pid))
            cur.execute("""INSERT INTO condicional_itens (condicional_id,produto_id,codigo_produto,modelo,descricao,tamanho,valor_unitario,quantidade)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (cid, pid or None, it.get('codigo'), it.get('modelo'), it.get('descricao'), it.get('tamanho'), vu, qtd))
        rotulo = 'Transferência' if tipo == 'transferencia' else 'Condicional'
        conn.commit(); flash(f'{rotulo} {cod} registrada! Itens reservados no estoque.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('condicionais'))


@login_required
def ficha_condicional(cid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM condicionais WHERE id=%s", (cid,))
    row = cur.fetchone()
    if not row:
        flash('Condicional não encontrada.', 'erro'); cur.close(); close_db(conn)
        return redirect(url_for('condicionais'))
    cond = dict(row)
    cur.execute("SELECT * FROM condicional_itens WHERE condicional_id=%s ORDER BY id", (cid,))
    itens = [dict(i) for i in cur.fetchall()]
    cur.execute("SELECT nome FROM usuarios WHERE ativo=TRUE ORDER BY nome")
    vendedoras = [dict(u) for u in cur.fetchall()]
    cliente_cred = False
    if cond.get('cliente_id'):
        cur.execute("SELECT crediario FROM clientes WHERE id=%s", (cond['cliente_id'],))
        cc = cur.fetchone(); cliente_cred = bool(cc and cc['crediario'])
    venda = None
    if cond.get('venda_id'):
        cur.execute("SELECT codigo FROM vendas WHERE id=%s", (cond['venda_id'],))
        vv = cur.fetchone(); venda = dict(vv) if vv else None
    cur.close(); close_db(conn)
    cond['dias'] = (hoje_app() - cond['criado_em'].date()).days
    ctx = get_ctx(); ctx.update(cond=cond, itens=itens, vendedoras=vendedoras,
                                cliente_cred=cliente_cred, venda=venda)
    return render_template('ficha_condicional.html', **ctx)


@login_required
def gerar_venda_condicional(cid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM condicionais WHERE id=%s", (cid,))
        cond = cur.fetchone()
        if not cond: raise Exception('Condicional não encontrada.')
        cond = dict(cond)
        if cond['status'] != 'aberta': raise Exception('Esta condicional já foi finalizada.')
        cur.execute("SELECT * FROM condicional_itens WHERE condicional_id=%s", (cid,))
        citens = [dict(i) for i in cur.fetchall()]
        usuario_id = request.form.get('usuario_id') or cond.get('usuario_id')
        vendedora_nome = request.form.get('vendedora_nome', '').strip() or cond.get('vendedora_nome')
        forma = request.form.get('forma_pagamento', '').strip()
        cliente_id = cond.get('cliente_id'); cliente_nome = cond.get('cliente_nome')
        # Quantas peças o cliente ficou (por item)
        kept_total = 0
        for it in citens:
            k = int(request.form.get(f'fica_{it["id"]}', 0) or 0)
            it['_kept'] = max(0, min(k, int(it['quantidade'])))
            kept_total += it['_kept']
        if kept_total == 0:
            raise Exception('Selecione ao menos uma peça que ficou com o cliente. Para devolver tudo, use "Devolver tudo".')
        if not forma:
            raise Exception('Selecione a forma de pagamento.')
        valor_total = round(sum(float(it['valor_unitario']) * it['_kept'] for it in citens if it['_kept'] > 0), 2)
        desconto = min(parse_brl(request.form.get('desconto_valor', '0')), valor_total)
        pct_desconto = min(100.0, max(0.0, parse_brl(request.form.get('pct_desconto', '0'))))
        valor_final = round(valor_total - desconto, 2)
        parcelas = int(request.form.get('parcelas', 1) or 1)
        cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)),0) as n FROM vendas WHERE codigo ~ '^V[0-9]+$'")
        vn = cur.fetchone()['n']; vcod = f"V{vn+1}"
        cur.execute("""INSERT INTO vendas (codigo,usuario_id,vendedora_nome,cliente_id,cliente_nome,valor_total,desconto,pct_desconto,forma_pagamento,parcelas)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (vcod, usuario_id or None, vendedora_nome, cliente_id or None, cliente_nome,
             valor_total, desconto, pct_desconto, forma, parcelas))
        venda_id = cur.fetchone()['id']
        for it in citens:
            k = it['_kept']; q = int(it['quantidade']); devolver = q - k; pid = it['produto_id']
            if k > 0:
                vu = float(it['valor_unitario'])
                cur.execute("""INSERT INTO venda_itens (venda_id,produto_id,codigo_produto,modelo,descricao,tamanho,valor_unitario,quantidade,valor_total)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (venda_id, pid or None, it['codigo_produto'], it['modelo'], it['descricao'], it['tamanho'], vu, k, vu * k))
                if pid:
                    cur.execute("UPDATE estoque SET reservado=GREATEST(0,COALESCE(reservado,0)-%s), ultima_venda=CURRENT_DATE WHERE id=%s", (k, pid))
            if devolver > 0 and pid:
                cur.execute("UPDATE estoque SET quantidade=quantidade+%s, reservado=GREATEST(0,COALESCE(reservado,0)-%s) WHERE id=%s", (devolver, devolver, pid))
            novo = 'vendido' if (k > 0 and devolver == 0) else ('parcial' if k > 0 else 'devolvido')
            cur.execute("UPDATE condicional_itens SET status=%s WHERE id=%s", (novo, it['id']))
        # Caixa / crediário
        formas_a_vista = ['pix', 'dinheiro', 'debito', 'credito_vista', 'credito_parcelado', 'link']
        if forma == 'multiplo':
            # Pagamento dividido: cada forma vira uma linha no caixa (com sua taxa).
            pagamentos = parse_pagamentos(request.form.get('pagamentos'))
            if not pagamentos:
                raise Exception('Pagamento dividido sem formas válidas.')
            soma = round(sum(p['valor'] for p in pagamentos), 2)
            if abs(soma - valor_final) > 0.02:
                raise Exception(f'A soma das formas (R$ {soma:.2f}) não bate com o valor da venda (R$ {valor_final:.2f}).')
            registrar_pagamentos_caixa(cur, pagamentos, f"Venda {vcod} - {cliente_nome} (condicional {cond['codigo']})",
                venda_id=venda_id, usuario_id=usuario_id or None, vendedora_nome=vendedora_nome)
        elif forma in formas_a_vista:
            parcelas_caixa = parcelas if forma == 'credito_parcelado' else None
            cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,usuario_id,vendedora_nome,parcelas)
                VALUES (%s,%s,'entrada',%s,%s,%s,%s,%s)""",
                (f"Venda {vcod} - {cliente_nome} (condicional {cond['codigo']})", valor_final, forma, venda_id, usuario_id or None, vendedora_nome, parcelas_caixa))
        elif forma == 'crediario':
            entrada = parse_brl(request.form.get('entrada', '0'))
            saldo = round(valor_final - entrada, 2)
            cur.execute("""INSERT INTO crediarios (venda_id,cliente_id,cliente_nome,valor_total,entrada,saldo_devedor)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (venda_id, cliente_id or None, cliente_nome, valor_final, entrada, saldo))
            cred_id = cur.fetchone()['id']
            for i, p in enumerate(json.loads(request.form.get('parcelas_datas', '[]'))):
                cur.execute("INSERT INTO crediario_parcelas (crediario_id,numero_parcela,data_vencimento,valor) VALUES (%s,%s,%s,%s)",
                    (cred_id, i + 1, p.get('data'), float(p.get('valor', 0))))
            if entrada > 0:
                entrada_forma = request.form.get('entrada_forma', 'dinheiro').strip() or 'dinheiro'
                if entrada_forma == 'multiplo':
                    ent_pgs = parse_pagamentos(request.form.get('entrada_pagamentos'))
                    if not ent_pgs:
                        raise Exception('Entrada dividida sem formas válidas.')
                    soma_e = round(sum(p['valor'] for p in ent_pgs), 2)
                    if abs(soma_e - round(entrada, 2)) > 0.02:
                        raise Exception(f'A soma das formas da entrada (R$ {soma_e:.2f}) não bate com a entrada (R$ {entrada:.2f}).')
                    registrar_pagamentos_caixa(cur, ent_pgs, f"Entrada crediário - {cliente_nome} (condicional {cond['codigo']})",
                        venda_id=venda_id, crediario_id=cred_id, usuario_id=usuario_id or None, vendedora_nome=vendedora_nome)
                else:
                    if entrada_forma not in formas_a_vista: entrada_forma = 'dinheiro'
                    ent_parc = int(request.form.get('entrada_parcelas', 0) or 0) or None if entrada_forma == 'credito_parcelado' else None
                    cur.execute("""INSERT INTO caixa (descricao,valor,tipo,forma_pagamento,venda_id,crediario_id,usuario_id,vendedora_nome,parcelas)
                        VALUES (%s,%s,'entrada',%s,%s,%s,%s,%s,%s)""",
                        (f"Entrada crediário - {cliente_nome} (condicional {cond['codigo']}, {entrada_forma.replace('_',' ')})", entrada, entrada_forma, venda_id, cred_id, usuario_id or None, vendedora_nome, ent_parc))
        cur.execute("UPDATE condicionais SET status='finalizada', venda_id=%s, finalizado_em=CURRENT_TIMESTAMP WHERE id=%s", (venda_id, cid))
        conn.commit(); flash(f'Venda {vcod} gerada da condicional {cond["codigo"]}! Peças não retiradas voltaram ao estoque.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
        cur.close(); close_db(conn)
        return redirect(url_for('ficha_condicional', cid=cid))
    cur.close(); close_db(conn)
    return redirect(url_for('ficha_venda', vid=venda_id))


@login_required
def devolver_condicional(cid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM condicionais WHERE id=%s", (cid,))
        cond = cur.fetchone()
        if not cond: raise Exception('Condicional não encontrada.')
        cond = dict(cond)
        if cond['status'] != 'aberta': raise Exception('Esta condicional já foi finalizada.')
        cur.execute("SELECT * FROM condicional_itens WHERE condicional_id=%s AND status='pendente'", (cid,))
        for it in cur.fetchall():
            if it['produto_id']:
                cur.execute("UPDATE estoque SET quantidade=quantidade+%s, reservado=GREATEST(0,COALESCE(reservado,0)-%s) WHERE id=%s",
                    (it['quantidade'], it['quantidade'], it['produto_id']))
        cur.execute("UPDATE condicional_itens SET status='devolvido' WHERE condicional_id=%s", (cid,))
        cur.execute("UPDATE condicionais SET status='devolvida', finalizado_em=CURRENT_TIMESTAMP WHERE id=%s", (cid,))
        conn.commit(); flash(f'Condicional {cond["codigo"]} devolvida. Peças retornaram ao estoque.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('condicionais'))


@login_required
def confirmar_transferencia(cid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM condicionais WHERE id=%s", (cid,))
        cond = cur.fetchone()
        if not cond: raise Exception('Registro não encontrado.')
        cond = dict(cond)
        if cond['status'] != 'aberta': raise Exception('Já finalizada.')
        cur.execute("SELECT * FROM condicional_itens WHERE condicional_id=%s AND status='pendente'", (cid,))
        for it in cur.fetchall():
            if it['produto_id']:
                cur.execute("UPDATE estoque SET reservado=GREATEST(0,COALESCE(reservado,0)-%s) WHERE id=%s", (it['quantidade'], it['produto_id']))
        cur.execute("UPDATE condicional_itens SET status='transferido' WHERE condicional_id=%s", (cid,))
        cur.execute("UPDATE condicionais SET status='finalizada', finalizado_em=CURRENT_TIMESTAMP WHERE id=%s", (cid,))
        conn.commit(); flash(f'Transferência {cond["codigo"]} confirmada. Peças baixadas (enviadas à {cond["cliente_nome"]}).', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('condicionais'))


@login_required
def excluir_condicional(cid):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.', 'erro'); return redirect(url_for('condicionais'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT status FROM condicionais WHERE id=%s", (cid,))
        r = cur.fetchone()
        if r and r['status'] == 'aberta':
            cur.execute("SELECT * FROM condicional_itens WHERE condicional_id=%s AND status='pendente'", (cid,))
            for it in cur.fetchall():
                if it['produto_id']:
                    cur.execute("UPDATE estoque SET quantidade=quantidade+%s, reservado=GREATEST(0,COALESCE(reservado,0)-%s) WHERE id=%s",
                        (it['quantidade'], it['quantidade'], it['produto_id']))
        cur.execute("DELETE FROM condicionais WHERE id=%s", (cid,))
        conn.commit(); flash('Condicional excluída.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('condicionais'))


def register(app):
    app.add_url_rule('/condicionais', 'condicionais', condicionais)
    app.add_url_rule('/condicionais/nova', 'nova_condicional', nova_condicional, methods=['POST'])
    app.add_url_rule('/condicionais/<int:cid>', 'ficha_condicional', ficha_condicional)
    app.add_url_rule('/condicionais/<int:cid>/gerar-venda', 'gerar_venda_condicional', gerar_venda_condicional, methods=['POST'])
    app.add_url_rule('/condicionais/<int:cid>/devolver', 'devolver_condicional', devolver_condicional, methods=['POST'])
    app.add_url_rule('/condicionais/<int:cid>/confirmar-transferencia', 'confirmar_transferencia', confirmar_transferencia, methods=['POST'])
    app.add_url_rule('/condicionais/<int:cid>/excluir', 'excluir_condicional', excluir_condicional, methods=['POST'])
