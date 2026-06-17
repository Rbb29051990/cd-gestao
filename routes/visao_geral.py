"""Rota da Visão Geral: faturamento por forma (caixa real), estoque, crediários,
condicionais, despesas do período e lucro líquido."""
from flask import render_template, request
from datetime import date
from db import get_db, close_db
from config import agora_app, hoje_app
from auth import login_required, get_ctx
from utils import get_taxa_vigente, calcular_liquido


@login_required
def visao_geral():
    conn = get_db(); cur = conn.cursor()
    hoje = agora_app()
    # Período (mesmo padrão da aba Caixa)
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim    = request.args.get('data_fim',    hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = hoje.strftime('%Y-%m-%d')
    # Faturamento por forma = dinheiro REAL recebido (caixa entradas).
    # Crediário não aparece como forma própria: a entrada e as parcelas já
    # entram no caixa com a forma real (pix/dinheiro/cartão), então são contabilizadas aqui.
    formas = ['dinheiro', 'pix', 'debito', 'credito_vista', 'credito_parcelado', 'link']
    formas_com_taxa = ['credito_vista', 'credito_parcelado', 'debito', 'link']
    fat     = {f: 0.0 for f in formas}   # bruto por forma
    fat_liq = {f: 0.0 for f in formas}   # líquido por forma (após taxas de cartão)
    try:
        cur.execute("""SELECT forma_pagamento, valor, criado_em FROM caixa
                       WHERE tipo='entrada' AND DATE(criado_em) BETWEEN %s AND %s""", (data_inicio, data_fim))
        for r in cur.fetchall():
            f = r['forma_pagamento'] or ''
            if f not in fat: continue   # ignora 'crediario' legado / nulos
            bruto = float(r['valor'] or 0)
            fat[f] += bruto
            if f in formas_com_taxa:
                taxa_data = get_taxa_vigente(r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje_app())
                liq, _d, _p = calcular_liquido(bruto, f, taxa_data)
                fat_liq[f] += liq
            else:
                fat_liq[f] += bruto
    except Exception:
        pass
    fat     = {k: round(v, 2) for k, v in fat.items()}
    fat_liq = {k: round(v, 2) for k, v in fat_liq.items()}
    fat_total     = round(sum(fat.values()), 2)
    fat_total_liq = round(sum(fat_liq.values()), 2)
    # Estoque — custo, valor de venda, lucro potencial (sempre global, não filtra por período)
    try:
        cur.execute("""SELECT COALESCE(SUM(custo_unitario*quantidade),0) as ct,
                              COALESCE(SUM(valor_venda*quantidade),0)   as vt
                       FROM estoque WHERE ativo=TRUE""")
        r = cur.fetchone()
        custo_estoque   = round(float(r['ct']), 2)
        val_estoque     = round(float(r['vt']), 2)
        lucro_potencial = round(val_estoque - custo_estoque, 2)
    except: custo_estoque = val_estoque = lucro_potencial = 0.0
    # Crediários em aberto (global)
    try:
        cur.execute("SELECT COALESCE(SUM(saldo_devedor),0) as v FROM crediarios WHERE status='aberto'")
        val_crediarios = round(float(cur.fetchone()['v']), 2)
    except: val_crediarios = 0.0
    # Condicional / transferência em aberto (global)
    try:
        cur.execute("SELECT COALESCE(SUM(valor_total),0) as v, COUNT(*) as n FROM condicionais WHERE status='aberta'")
        rc = cur.fetchone()
        val_condicional = round(float(rc['v']), 2); n_condicional = int(rc['n'])
    except: val_condicional = 0.0; n_condicional = 0
    # Despesas do período pelo VENCIMENTO das parcelas (valores que SERÃO pagos
    # dentro do período selecionado), separadas em fixas e avulsas — mesmo
    # critério da aba Despesas (d.tipo = 'fixa'/'fixo' → fixa; o resto → avulsa).
    despesas_fixas = despesas_avulsas = 0.0
    try:
        cur.execute("""SELECT LOWER(COALESCE(d.tipo,'')) as tp, COALESCE(SUM(p.valor),0) as t
                       FROM despesa_parcelas p
                       JOIN despesas d ON d.id=p.despesa_id
                       WHERE DATE(p.data_vencimento) BETWEEN %s AND %s
                       GROUP BY LOWER(COALESCE(d.tipo,''))""", (data_inicio, data_fim))
        for r in cur.fetchall():
            if (r['tp'] or '') in ('fixa', 'fixo'): despesas_fixas += float(r['t'])
            else: despesas_avulsas += float(r['t'])
    except Exception:
        pass
    despesas_fixas   = round(despesas_fixas, 2)
    despesas_avulsas = round(despesas_avulsas, 2)
    val_despesas     = round(despesas_fixas + despesas_avulsas, 2)
    # Lucro líquido = entradas líquidas − (despesas fixas + avulsas) do período
    lucro_liquido = round(fat_total_liq - val_despesas, 2)
    # Movimentações recentes (filtradas pelo período)
    try:
        cur.execute("""SELECT id,criado_em,vendedora_nome,cliente_nome,valor_total,forma_pagamento
                       FROM vendas WHERE DATE(criado_em) BETWEEN %s AND %s
                       ORDER BY criado_em DESC LIMIT 8""", (data_inicio, data_fim))
        movs = [dict(r) for r in cur.fetchall()]
    except: movs = []
    try:
        cur.execute("SELECT codigo,modelo,tamanho,quantidade FROM estoque WHERE ativo=TRUE AND quantidade<=2 ORDER BY quantidade")
        estoque_baixo = [dict(r) for r in cur.fetchall()]
    except: estoque_baixo = []
    cur.close(); close_db(conn)
    ctx = get_ctx()
    ctx.update(fat=fat, fat_liq=fat_liq, fat_total=fat_total, fat_total_liq=fat_total_liq,
               custo_estoque=custo_estoque, val_estoque=val_estoque,
               lucro_potencial=lucro_potencial, val_crediarios=val_crediarios,
               val_condicional=val_condicional, n_condicional=n_condicional,
               val_despesas=val_despesas, despesas_fixas=despesas_fixas,
               despesas_avulsas=despesas_avulsas, lucro_liquido=lucro_liquido,
               movs=movs, estoque_baixo=estoque_baixo,
               data_inicio=data_inicio, data_fim=data_fim,
               mes_atual=hoje.strftime('%B / %Y').capitalize(),
               hoje=hoje.strftime('%A, %d de %B de %Y').capitalize())
    return render_template('visao_geral.html', **ctx)


def register(app):
    app.add_url_rule('/visao-geral', 'visao_geral', visao_geral)
