"""Rotas de Estoque: listagem, cadastro, nova entrada, modelos/tamanhos,
etiquetas (lista por data e busca por código), ficha, edição, exclusão e
exportação para .xlsx (v142)."""
import io
from datetime import date
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from db import get_db, close_db
from config import hoje_app, fim_mes_app
from auth import login_required, get_ctx, pode_excluir
from utils import parse_brl, audit_log


@login_required
def estoque():
    conn = get_db(); cur = conn.cursor()
    hoje = hoje_app()
    # Filtro de período por DATA DE LANÇAMENTO do produto (criado_em) — padrão das
    # demais abas: começa no mês vigente (1º dia → último dia).
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-01-01'))
    data_fim = request.args.get('data_fim', hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except ValueError: data_inicio = hoje.strftime('%Y-01-01')
    try: date.fromisoformat(data_fim)
    except ValueError: data_fim = hoje.strftime('%Y-%m-%d')
    cur.execute("SELECT * FROM estoque WHERE ativo=TRUE AND DATE(criado_em) BETWEEN %s AND %s ORDER BY criado_em", (data_inicio, data_fim))
    itens = [dict(i) for i in cur.fetchall()]
    cur.execute("SELECT COALESCE(SUM(custo_unitario*quantidade),0) as ct, COALESCE(SUM(valor_venda*quantidade),0) as vt FROM estoque WHERE ativo=TRUE AND DATE(criado_em) BETWEEN %s AND %s", (data_inicio, data_fim))
    tots = cur.fetchone()
    cur.execute("SELECT nome FROM modelos_estoque ORDER BY nome")
    modelos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT nome FROM tamanhos_estoque ORDER BY id")
    tamanhos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)), 0) as m FROM estoque WHERE codigo ~ '^P[0-9]+$'")
    n = cur.fetchone()['m']
    # Buscar total de entradas adicionais por item (mesma conexão, antes de fechar)
    cur.execute("SELECT estoque_id, COALESCE(SUM(quantidade),0) as total FROM estoque_entradas GROUP BY estoque_id")
    entradas_map = {r['estoque_id']: int(r['total']) for r in cur.fetchall()}
    cur.close(); close_db(conn)
    for i in itens:
        i['dias_estoque'] = (hoje - i['criado_em'].date()).days
        i['entradas_adicionais'] = entradas_map.get(i['id'], 0)
        i['saidas'] = max(0, (i['estoque_inicial'] or 0) + i['entradas_adicionais'] - i['quantidade'])
        dp = float(i.get('desconto_promo') or 0)
        i['valor_promo'] = round(float(i['valor_venda'] or 0) * (1 - dp / 100), 2) if dp > 0 else None
    ctx = get_ctx()
    ctx.update(itens=itens, modelos=modelos, tamanhos=tamanhos,
               custo_total=float(tots['ct']), valor_total=float(tots['vt']),
               lucro_potencial=float(tots['vt']) - float(tots['ct']),
               next_ref=f"P{n+1}", data_inicio=data_inicio, data_fim=data_fim)
    return render_template('estoque.html', **ctx)


@login_required
def novo_estoque():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)), 0) as m FROM estoque WHERE codigo ~ '^P[0-9]+$'")
    n = cur.fetchone()['m']
    qtd = int(request.form.get('quantidade', 1) or 1)
    custo_raw = request.form.get('custo_unitario', '').strip()
    venda_raw = request.form.get('valor_venda', '').strip()
    if not custo_raw or parse_brl(custo_raw) <= 0:
        flash('O custo unitário é obrigatório e deve ser maior que zero.', 'erro')
        cur.close(); close_db(conn)
        return redirect(url_for('estoque'))
    if not venda_raw or parse_brl(venda_raw) <= 0:
        flash('O valor de venda é obrigatório e deve ser maior que zero.', 'erro')
        cur.close(); close_db(conn)
        return redirect(url_for('estoque'))
    foto = request.form.get('foto', '').strip() or None
    # Segurança: só aceita data URI de imagem e limita o tamanho (~1.5MB de base64)
    if foto and (not foto.startswith('data:image/') or len(foto) > 1_500_000):
        foto = None
    try:
        cur.execute("""INSERT INTO estoque (codigo,modelo,descricao,tamanho,quantidade,estoque_inicial,
            custo_unitario,markup,valor_venda,margem_lucro,foto) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (f"P{n+1}", request.form.get('modelo', '').strip(),
             request.form.get('descricao', '').strip() or None,
             request.form.get('tamanho', '').strip(), qtd, qtd,
             parse_brl(request.form.get('custo_unitario', '0')),
             parse_brl(request.form.get('markup', '0')),
             parse_brl(request.form.get('valor_venda', '0')),
             parse_brl(request.form.get('margem_lucro', '0')), foto))
        conn.commit(); flash('Produto cadastrado!', 'ok')
    except Exception as e: conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('estoque'))


@login_required
def nova_entrada_estoque(eid):
    conn = get_db(); cur = conn.cursor()
    try:
        qtd = int(request.form.get('quantidade', 0) or 0)
        custo = parse_brl(request.form.get('custo_unitario', '0'))
        markup = parse_brl(request.form.get('markup', '0'))
        venda = parse_brl(request.form.get('valor_venda', '0'))
        margem = parse_brl(request.form.get('margem_lucro', '0'))
        if qtd <= 0:
            flash('Informe uma quantidade válida.', 'erro')
            return redirect(url_for('ficha_estoque', eid=eid))
        if custo <= 0:
            flash('O custo unitário é obrigatório para nova entrada.', 'erro')
            return redirect(url_for('ficha_estoque', eid=eid))
        if venda <= 0:
            flash('O valor de venda é obrigatório para nova entrada.', 'erro')
            return redirect(url_for('ficha_estoque', eid=eid))
        # Registrar entrada
        cur.execute("""INSERT INTO estoque_entradas (estoque_id, quantidade, custo_unitario, valor_venda, markup, margem_lucro)
                       VALUES (%s,%s,%s,%s,%s,%s)""", (eid, qtd, custo, venda, markup, margem))
        # Atualizar saldo e último custo/venda do produto
        cur.execute("""UPDATE estoque SET
                       quantidade = quantidade + %s,
                       custo_unitario = %s,
                       valor_venda = %s,
                       markup = %s,
                       margem_lucro = %s
                       WHERE id = %s""", (qtd, custo, venda, markup, margem, eid))
        conn.commit()
        flash(f'Nova entrada de {qtd} unidade(s) registrada com sucesso!', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('ficha_estoque', eid=eid))


@login_required
def novo_modelo():
    nome = request.form.get('nome', '').strip()
    if nome:
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO modelos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (nome,))
        conn.commit(); cur.close(); close_db(conn)
    return redirect(url_for('estoque'))


@login_required
def novo_tamanho():
    nome = request.form.get('nome', '').strip()
    if not nome:
        return jsonify({'ok': False, 'erro': 'Nome vazio'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO tamanhos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (nome,))
    conn.commit(); cur.close(); close_db(conn)
    return jsonify({'ok': True, 'nome': nome})


@login_required
def etiquetas():
    data = request.args.get('data', hoje_app().isoformat())
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT codigo,modelo,descricao,tamanho,valor_venda,quantidade FROM estoque WHERE DATE(criado_em)=%s AND ativo=TRUE ORDER BY id", (data,))
    itens = [dict(i) for i in cur.fetchall()]
    cur.close(); close_db(conn)
    return jsonify({'itens': itens, 'data': data})


@login_required
def etiqueta_busca():
    cod = request.args.get('codigo', '').strip().upper()
    if cod and not cod.startswith('P'): cod = 'P' + cod
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id,codigo,modelo,descricao,tamanho,valor_venda,quantidade FROM estoque WHERE codigo=%s AND ativo=TRUE", (cod,))
    item = cur.fetchone(); cur.close(); close_db(conn)
    if item: return jsonify({'ok': True, 'item': dict(item)})
    return jsonify({'ok': False})


@login_required
def ficha_estoque(eid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM estoque WHERE id=%s", (eid,))
    row = cur.fetchone(); cur.close(); close_db(conn)
    if not row:
        flash('Produto nao encontrado.', 'erro'); return redirect(url_for('estoque'))
    item = dict(row)
    item['dias_estoque'] = (hoje_app() - item['criado_em'].date()).days
    item['saidas'] = (item['estoque_inicial'] or 0) - item['quantidade']
    ctx = get_ctx(); ctx['item'] = item
    return render_template('ficha_estoque.html', **ctx)


@login_required
def editar_estoque(eid):
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        qtd = int(request.form.get('quantidade', 1) or 1)
        campos = (request.form.get('modelo', '').strip(),
                  request.form.get('descricao', '').strip() or None,
                  request.form.get('tamanho', '').strip(), qtd,
                  parse_brl(request.form.get('custo_unitario', '0')),
                  parse_brl(request.form.get('markup', '0')),
                  parse_brl(request.form.get('valor_venda', '0')),
                  parse_brl(request.form.get('margem_lucro', '0')))
        # Só mexe na foto se o usuário trocou/removeu (senão preserva a existente).
        if request.form.get('foto_alterada') == '1':
            foto = request.form.get('foto', '').strip() or None
            cur.execute("""UPDATE estoque SET modelo=%s,descricao=%s,tamanho=%s,quantidade=%s,
                custo_unitario=%s,markup=%s,valor_venda=%s,margem_lucro=%s,foto=%s WHERE id=%s""",
                campos + (foto, eid))
        else:
            cur.execute("""UPDATE estoque SET modelo=%s,descricao=%s,tamanho=%s,quantidade=%s,
                custo_unitario=%s,markup=%s,valor_venda=%s,margem_lucro=%s WHERE id=%s""",
                campos + (eid,))
        conn.commit(); cur.close(); close_db(conn)
        flash('Produto atualizado!', 'ok')
        return redirect(url_for('ficha_estoque', eid=eid))
    cur.execute("SELECT * FROM estoque WHERE id=%s", (eid,))
    item = cur.fetchone()
    if not item:
        cur.close(); close_db(conn)
        flash('Produto nao encontrado.', 'erro'); return redirect(url_for('estoque'))
    cur.execute("SELECT nome FROM modelos_estoque ORDER BY nome")
    modelos = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT nome FROM tamanhos_estoque ORDER BY id")
    tamanhos = [r['nome'] for r in cur.fetchall()]
    cur.close(); close_db(conn)
    ctx = get_ctx(); ctx.update(item=item, modelos=modelos, tamanhos=tamanhos)
    return render_template('editar_estoque.html', **ctx)


@login_required
def aplicar_promocao():
    """Aplica ou remove o % de desconto promocional em vários produtos de uma vez.
    O preço original (valor_venda) NÃO é alterado — a promoção é só uma camada."""
    ids_raw = request.form.get('ids', '')
    ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    acao = request.form.get('acao', 'aplicar')
    if not ids:
        flash('Selecione ao menos um produto.', 'erro')
        return redirect(url_for('estoque'))
    # Modo de desconto: por VALOR (R$ fixo, convertido em % por produto) ou por %.
    valor_desc = parse_brl(request.form.get('valor_desconto', '0')) if acao != 'remover' else 0.0
    pct = 0.0
    if acao != 'remover' and valor_desc <= 0:
        pct = parse_brl(request.form.get('percentual', '0'))
        if pct <= 0 or pct >= 100:
            flash('Informe um percentual (1 a 99) ou um valor de desconto.', 'erro')
            return redirect(url_for('estoque'))
    conn = get_db(); cur = conn.cursor()
    try:
        if acao != 'remover' and valor_desc > 0:
            # R$ fixo: cada produto recebe o % equivalente ao seu próprio preço.
            cur.execute("SELECT id, valor_venda FROM estoque WHERE id = ANY(%s)", (ids,))
            for r in cur.fetchall():
                preco = float(r['valor_venda'] or 0)
                p = round(valor_desc / preco * 100, 2) if preco > 0 else 0.0
                p = max(0.0, min(99.0, p))
                cur.execute("UPDATE estoque SET desconto_promo=%s WHERE id=%s", (p, r['id']))
            flash(f'Desconto de R$ {valor_desc:.2f} aplicado em {len(ids)} produto(s).', 'ok')
        else:
            cur.execute("UPDATE estoque SET desconto_promo=%s WHERE id = ANY(%s)", (pct, ids))
            if acao == 'remover':
                flash(f'Promoção removida de {len(ids)} produto(s).', 'ok')
            else:
                flash(f'Desconto de {pct:.0f}% aplicado em {len(ids)} produto(s).', 'ok')
        conn.commit()
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('estoque'))


@login_required
def excluir_estoque(eid):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.', 'erro'); return redirect(url_for('estoque'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT codigo,modelo,descricao,tamanho,quantidade FROM estoque WHERE id=%s", (eid,))
    _old = cur.fetchone()
    cur.execute("DELETE FROM estoque WHERE id=%s", (eid,))
    audit_log(cur, 'EXCLUIR_PRODUTO', 'estoque', eid, dict(_old) if _old else None)
    conn.commit(); cur.close(); close_db(conn)
    flash('Produto excluido.', 'ok')
    return redirect(url_for('estoque'))


@login_required
def exportar_estoque():
    """v142: gera um .xlsx com os produtos do período filtrado (mesmo filtro da tela de
    Estoque — data de lançamento) para download. Uma linha por produto, com saldo,
    entradas/saídas, custo/venda e a promoção vigente."""
    conn = get_db(); cur = conn.cursor()
    hoje = hoje_app()
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-01-01'))
    data_fim = request.args.get('data_fim', hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except ValueError: data_inicio = hoje.strftime('%Y-01-01')
    try: date.fromisoformat(data_fim)
    except ValueError: data_fim = hoje.strftime('%Y-%m-%d')
    cur.execute("SELECT * FROM estoque WHERE ativo=TRUE AND DATE(criado_em) BETWEEN %s AND %s ORDER BY criado_em", (data_inicio, data_fim))
    itens = [dict(i) for i in cur.fetchall()]
    cur.execute("SELECT estoque_id, COALESCE(SUM(quantidade),0) as total FROM estoque_entradas GROUP BY estoque_id")
    entradas_map = {r['estoque_id']: int(r['total']) for r in cur.fetchall()}
    cur.close(); close_db(conn)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Estoque'

    headers = ['Código', 'Data lançamento', 'Modelo', 'Descrição', 'Tamanho',
               'Estoque inicial', 'Entradas adicionais', 'Saídas', 'Saldo atual',
               'Custo unitário (R$)', 'Markup (%)', 'Valor de venda (R$)',
               'Margem de lucro (%)', 'Desconto promo (%)', 'Valor promocional (R$)',
               'Dias em estoque', 'Custo total do saldo (R$)', 'Valor total do saldo (R$)']
    ws.append(headers)
    header_fill = PatternFill(start_color='E65100', end_color='E65100', fill_type='solid')
    for col in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = header_fill
        c.alignment = Alignment(horizontal='center', vertical='center')

    money_cols = {10, 12, 15, 17, 18}
    pct_cols = {11, 13, 14}
    for item in itens:
        entradas_adicionais = entradas_map.get(item['id'], 0)
        saldo = int(item.get('quantidade') or 0)
        saidas = max(0, (item.get('estoque_inicial') or 0) + entradas_adicionais - saldo)
        dias = (hoje - item['criado_em'].date()).days if item.get('criado_em') else None
        custo = float(item.get('custo_unitario') or 0)
        venda = float(item.get('valor_venda') or 0)
        dp = float(item.get('desconto_promo') or 0)
        valor_promo = round(venda * (1 - dp / 100), 2) if dp > 0 else None
        ws.append([
            item.get('codigo'),
            item['criado_em'].strftime('%d/%m/%Y') if item.get('criado_em') else '',
            item.get('modelo') or '', item.get('descricao') or '', item.get('tamanho') or '',
            item.get('estoque_inicial') or 0, entradas_adicionais, saidas, saldo,
            custo, float(item.get('markup') or 0), venda, float(item.get('margem_lucro') or 0),
            dp if dp > 0 else None, valor_promo, dias,
            round(custo * saldo, 2), round(venda * saldo, 2),
        ])
        row = ws.max_row
        for col in money_cols:
            ws.cell(row=row, column=col).number_format = '#,##0.00'
        for col in pct_cols:
            ws.cell(row=row, column=col).number_format = '0.00'

    widths = [10, 14, 20, 28, 9, 10, 12, 9, 10, 15, 10, 16, 14, 13, 16, 12, 18, 18]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nome_arquivo = f"estoque_{data_inicio}_a_{data_fim}.xlsx"
    return send_file(buf, as_attachment=True, download_name=nome_arquivo,
                      mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def register(app):
    app.add_url_rule('/estoque', 'estoque', estoque)
    app.add_url_rule('/estoque/novo', 'novo_estoque', novo_estoque, methods=['POST'])
    app.add_url_rule('/estoque/<int:eid>/nova-entrada', 'nova_entrada_estoque', nova_entrada_estoque, methods=['POST'])
    app.add_url_rule('/estoque/modelo/novo', 'novo_modelo', novo_modelo, methods=['POST'])
    app.add_url_rule('/estoque/tamanho/novo', 'novo_tamanho', novo_tamanho, methods=['POST'])
    app.add_url_rule('/estoque/etiquetas', 'etiquetas', etiquetas)
    app.add_url_rule('/estoque/etiqueta-busca', 'etiqueta_busca', etiqueta_busca)
    app.add_url_rule('/estoque/promocao', 'aplicar_promocao', aplicar_promocao, methods=['POST'])
    app.add_url_rule('/estoque/exportar', 'exportar_estoque', exportar_estoque)
    app.add_url_rule('/estoque/<int:eid>', 'ficha_estoque', ficha_estoque)
    app.add_url_rule('/estoque/<int:eid>/editar', 'editar_estoque', editar_estoque, methods=['GET', 'POST'])
    app.add_url_rule('/estoque/<int:eid>/excluir', 'excluir_estoque', excluir_estoque, methods=['POST'])
