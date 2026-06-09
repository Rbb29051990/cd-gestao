"""Rota de Dashboards: vendas por dia, top produtos, formas de pagamento,
ranking de vendedoras, fluxo de caixa, clientes novos e ticket médio (mês atual)."""
from flask import render_template
from db import get_db, close_db
from config import agora_app
from auth import login_required, get_ctx


@login_required
def dashboard_view():
    conn = get_db(); cur = conn.cursor()
    hoje = agora_app()
    mes_ini = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    try:
        cur.execute("SELECT DATE(criado_em) as dia,COUNT(*) as qtd,COALESCE(SUM(valor_total),0) as total FROM vendas WHERE criado_em>=%s GROUP BY DATE(criado_em) ORDER BY dia", (mes_ini,))
        vendas_dia = [dict(r) for r in cur.fetchall()]
    except: vendas_dia = []
    try:
        cur.execute("""SELECT vi.codigo_produto,vi.modelo,SUM(vi.quantidade) as qtd_vendida,SUM(vi.valor_total) as receita
            FROM venda_itens vi JOIN vendas v ON v.id=vi.venda_id WHERE v.criado_em>=%s
            GROUP BY vi.codigo_produto,vi.modelo ORDER BY qtd_vendida DESC LIMIT 10""", (mes_ini,))
        top_produtos = [dict(r) for r in cur.fetchall()]
    except: top_produtos = []
    try:
        cur.execute("SELECT forma_pagamento,COUNT(*) as qtd,COALESCE(SUM(valor_total),0) as total FROM vendas WHERE criado_em>=%s GROUP BY forma_pagamento ORDER BY total DESC", (mes_ini,))
        formas_pag = [dict(r) for r in cur.fetchall()]
    except: formas_pag = []
    try:
        cur.execute("SELECT vendedora_nome,COUNT(*) as qtd_vendas,COALESCE(SUM(valor_total),0) as total,COUNT(DISTINCT cliente_id) as clientes FROM vendas WHERE criado_em>=%s GROUP BY vendedora_nome ORDER BY total DESC", (mes_ini,))
        vendedoras_rank = [dict(r) for r in cur.fetchall()]
    except: vendedoras_rank = []
    try:
        cur.execute("SELECT COALESCE(SUM(CASE WHEN tipo='entrada' THEN valor ELSE 0 END),0) as ent,COALESCE(SUM(CASE WHEN tipo='saida' THEN valor ELSE 0 END),0) as sai FROM caixa WHERE criado_em>=%s", (mes_ini,))
        fluxo = dict(cur.fetchone())
    except: fluxo = {'ent': 0, 'sai': 0}
    try:
        cur.execute("SELECT COUNT(*) as t FROM clientes WHERE criado_em>=%s", (mes_ini,))
        clientes_novos = cur.fetchone()['t']
    except: clientes_novos = 0
    try:
        cur.execute("SELECT COALESCE(AVG(valor_total),0) as t FROM vendas WHERE criado_em>=%s", (mes_ini,))
        ticket_medio = float(cur.fetchone()['t'])
    except: ticket_medio = 0.0
    cur.close(); close_db(conn)
    ctx = get_ctx()
    ctx.update(vendas_dia=vendas_dia, top_produtos=top_produtos, formas_pag=formas_pag,
               vendedoras_rank=vendedoras_rank, fluxo=fluxo,
               clientes_novos=clientes_novos, ticket_medio=ticket_medio,
               mes_atual=hoje.strftime('%B / %Y').capitalize())
    return render_template('dashboard.html', **ctx)


def register(app):
    app.add_url_rule('/dashboard', 'dashboard_view', dashboard_view)
