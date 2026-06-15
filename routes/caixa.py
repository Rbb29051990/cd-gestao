"""Rota de Caixa: movimentações do período, totais por categoria de entrada,
cálculo de líquido/descontos por forma e por categoria de crediário."""
from datetime import date
from flask import render_template, request, redirect, url_for, flash
from db import get_db, close_db
from config import hoje_app
from auth import login_required, get_ctx, pode_excluir
from utils import get_taxa_vigente, calcular_liquido, audit_log


@login_required
def caixa():
    conn = get_db(); cur = conn.cursor()
    hoje = hoje_app()
    # Suporte a filtro por data_inicio e data_fim
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim    = request.args.get('data_fim',    hoje.strftime('%Y-%m-%d'))
    # Garantir formato correto
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = hoje.strftime('%Y-%m-%d')
    cur.execute("SELECT * FROM caixa WHERE DATE(criado_em) BETWEEN %s AND %s ORDER BY criado_em DESC", (data_inicio, data_fim))
    movs = [dict(m) for m in cur.fetchall()]
    # Categorias de entrada:
    #   • Venda à vista:  venda_id NÃO nulo, crediario_id nulo, forma <> 'crediario'
    #   • Crediário entrada: venda_id NÃO nulo E (crediario_id NÃO nulo OU forma='crediario' [legado])
    #   • Crediário parcela: crediario_id NÃO nulo E venda_id nulo
    cur.execute("""SELECT
        COALESCE(SUM(CASE WHEN tipo='entrada' THEN valor ELSE 0 END),0) as entradas,
        COALESCE(SUM(CASE WHEN tipo='saida' THEN valor ELSE 0 END),0) as saidas,
        COALESCE(SUM(CASE WHEN tipo='entrada' AND venda_id IS NOT NULL AND crediario_id IS NULL AND COALESCE(forma_pagamento,'')<>'crediario' THEN valor ELSE 0 END),0) as entradas_vendas,
        COALESCE(SUM(CASE WHEN tipo='entrada' AND venda_id IS NOT NULL AND (crediario_id IS NOT NULL OR forma_pagamento='crediario') THEN valor ELSE 0 END),0) as entradas_cred_entrada,
        COALESCE(SUM(CASE WHEN tipo='entrada' AND crediario_id IS NOT NULL AND venda_id IS NULL THEN valor ELSE 0 END),0) as entradas_cred_parcelas
        FROM caixa WHERE DATE(criado_em) BETWEEN %s AND %s""", (data_inicio, data_fim))
    tots = cur.fetchone()
    entradas = float(tots['entradas']); saidas = float(tots['saidas'])
    entradas_vendas        = float(tots['entradas_vendas'])
    entradas_cred_entrada  = float(tots['entradas_cred_entrada'])
    entradas_cred_parcelas = float(tots['entradas_cred_parcelas'])
    entradas_crediarios    = round(entradas_cred_entrada + entradas_cred_parcelas, 2)
    cur.close(); close_db(conn)
    taxa_vigente_hoje = get_taxa_vigente()
    ctx = get_ctx()
    # Calcular líquido por movimento + desconto por forma E por categoria de crediário
    total_desconto = 0
    desconto_formas = {'credito_vista': 0.0, 'credito_parcelado': 0.0, 'debito': 0.0, 'link': 0.0}
    desconto_vendas = 0.0; desconto_cred_entrada = 0.0; desconto_cred_parcela = 0.0
    for m in movs:
        if m['tipo'] == 'entrada' and m.get('forma_pagamento') in ['credito_vista', 'credito_parcelado', 'debito', 'link']:
            taxa_data = get_taxa_vigente(m['criado_em'].date() if hasattr(m.get('criado_em', ''), 'date') else hoje_app())
            liq, desc, ptc = calcular_liquido(float(m['valor']), m['forma_pagamento'], taxa_data)
            m['valor_liquido'] = liq
            m['desconto_taxa'] = desc
            m['taxa_total_pct'] = ptc
            total_desconto += desc
            desconto_formas[m['forma_pagamento']] += desc
            vid = m.get('venda_id'); crid = m.get('crediario_id')
            if crid and not vid:
                desconto_cred_parcela += desc
            elif crid and vid:
                desconto_cred_entrada += desc
            else:
                desconto_vendas += desc
        else:
            m['valor_liquido'] = float(m['valor'])
            m['desconto_taxa'] = 0
            m['taxa_total_pct'] = 0
    saldo_bruto   = round(entradas - total_desconto, 2)
    saldo_liquido = round(saldo_bruto - saidas, 2)
    ctx.update(movs=movs, entradas=entradas, saidas=saidas,
               entradas_vendas=entradas_vendas, entradas_crediarios=entradas_crediarios,
               entradas_cred_entrada=entradas_cred_entrada,
               entradas_cred_parcelas=entradas_cred_parcelas,
               saldo=round(entradas - saidas, 2),
               saldo_bruto=saldo_bruto,
               total_desconto=round(total_desconto, 2), saldo_liquido=saldo_liquido,
               desconto_formas={k: round(v, 2) for k, v in desconto_formas.items()},
               desconto_vendas=round(desconto_vendas, 2),
               desconto_cred_entrada=round(desconto_cred_entrada, 2),
               desconto_cred_parcela=round(desconto_cred_parcela, 2),
               taxa_vigente=taxa_vigente_hoje,
               data_inicio=data_inicio, data_fim=data_fim)
    return render_template('caixa.html', **ctx)


@login_required
def excluir_caixa(mid):
    """Exclui um lançamento avulso do caixa. Restrito ao Administrador N1.
    Serve para remover lançamentos órfãos (de vendas/crediários já apagados)."""
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir lançamentos do caixa.', 'erro')
        return redirect(url_for('caixa'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT descricao,valor,tipo,forma_pagamento,venda_id,crediario_id,despesa_id FROM caixa WHERE id=%s", (mid,))
        _old = cur.fetchone()
        cur.execute("DELETE FROM caixa WHERE id=%s", (mid,))
        if cur.rowcount:
            audit_log(cur, 'EXCLUIR_CAIXA', 'caixa', mid, dict(_old) if _old else None)
            flash('Lançamento excluído do caixa.', 'ok')
        else:
            flash('Lançamento não encontrado.', 'erro')
        conn.commit()
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally:
        cur.close(); close_db(conn)
    data_inicio = request.form.get('data_inicio', '')
    data_fim = request.form.get('data_fim', '')
    if data_inicio and data_fim:
        return redirect(url_for('caixa', data_inicio=data_inicio, data_fim=data_fim))
    return redirect(url_for('caixa'))


def register(app):
    app.add_url_rule('/caixa', 'caixa', caixa)
    app.add_url_rule('/caixa/<int:mid>/excluir', 'excluir_caixa', excluir_caixa, methods=['POST'])
