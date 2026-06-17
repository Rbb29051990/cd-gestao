"""Dashboard Executivo V123.

Versão compacta em 3 linhas:
  1. KPIs financeiros principais
  2. Tendências financeiras + taxas + top categorias
  3. Ranking vendedoras + estoque parado + top clientes
"""
from datetime import date, timedelta
from flask import render_template, request
from db import get_db, close_db
from config import hoje_app, inicio_mes_app, fim_mes_app
from auth import login_required, get_ctx
from utils import get_taxa_vigente, calcular_liquido

MESES_PT = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
FORMAS_COM_TAXA = ('credito_vista', 'credito_parcelado', 'debito', 'link')
FORMA_LABEL = {
    'dinheiro': 'Dinheiro', 'pix': 'PIX', 'debito': 'Débito',
    'credito_vista': 'Crédito à vista', 'credito_parcelado': 'Crédito parcelado',
    'link': 'Link', 'transferencia': 'Transferência', 'crediario': 'Crediário', 'outros': 'Outros'
}
FORMA_COR = {
    'dinheiro': '#16a34a', 'pix': '#0891b2', 'debito': '#2563eb',
    'credito_vista': '#7c3aed', 'credito_parcelado': '#9333ea',
    'link': '#f59e0b', 'transferencia': '#0284c7', 'crediario': '#db2777', 'outros': '#94a3b8'
}
PALETA = ['#2563eb', '#16a34a', '#7c3aed', '#f59e0b', '#db2777', '#0891b2', '#64748b']


def _brl(v):
    return ("R$ " + f"{float(v or 0):,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def _kbrl(v):
    v = float(v or 0)
    s = '-' if v < 0 else ''
    a = abs(v)
    if a >= 1000:
        return s + f"{a/1000:.1f}".replace('.', ',') + 'k'
    return s + f"{a:.0f}"


def _add_months(y, m, delta):
    idx = (y * 12 + (m - 1)) + delta
    return idx // 12, idx % 12 + 1


def _month_start(d):
    return date(d.year, d.month, 1)


def _parse_date(value, fallback):
    try:
        return date.fromisoformat(value)
    except Exception:
        return date.fromisoformat(fallback)


def _pct_atual_anterior(atual, anterior):
    atual = float(atual or 0); anterior = float(anterior or 0)
    if anterior == 0:
        return None
    return round((atual - anterior) / anterior * 100, 1)


def _fmt_pct(v):
    if v is None:
        return '—'
    return (('+' if v >= 0 else '') + f"{v:.1f}%").replace('.', ',')


def _liquido_com_taxa(bruto, forma, dt, taxa_cache):
    bruto = float(bruto or 0)
    forma = forma or 'outros'
    if forma in FORMAS_COM_TAXA:
        k = dt.isoformat()
        if k not in taxa_cache:
            taxa_cache[k] = get_taxa_vigente(dt)
        liq, desc, pct = calcular_liquido(bruto, forma, taxa_cache[k])
        return float(liq or 0), float(desc or 0), float(pct or 0)
    return bruto, 0.0, 0.0


@login_required
def dashboard_view():
    conn = get_db(); cur = conn.cursor(); hoje = hoje_app()
    data_inicio = _parse_date(request.args.get('data_inicio'), inicio_mes_app())
    data_fim = _parse_date(request.args.get('data_fim'), fim_mes_app())
    if data_fim < data_inicio:
        data_inicio, data_fim = data_fim, data_inicio
    data_inicio_s = data_inicio.isoformat(); data_fim_s = data_fim.isoformat()

    def rollback():
        try: conn.rollback()
        except Exception: pass

    # Período anterior com a mesma duração
    dias = (data_fim - data_inicio).days + 1
    prev_fim = data_inicio - timedelta(days=1)
    prev_inicio = prev_fim - timedelta(days=dias - 1)

    # Entradas/faturamento bruto e líquido pelo caixa (base financeira real)
    def resumo_financeiro_periodo(ini, fim):
        bruto = liquido = taxas = 0.0
        por_forma_taxas = {}
        taxa_cache = {}
        try:
            cur.execute("""SELECT forma_pagamento, valor, criado_em FROM caixa
                           WHERE tipo='entrada' AND DATE(criado_em) BETWEEN %s AND %s""", (ini, fim))
            for r in cur.fetchall():
                b = float(r['valor'] or 0)
                forma = r['forma_pagamento'] or 'outros'
                dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
                liq, desc, _pct = _liquido_com_taxa(b, forma, dt, taxa_cache)
                bruto += b; liquido += liq; taxas += desc
                if desc:
                    por_forma_taxas[forma] = por_forma_taxas.get(forma, 0.0) + desc
        except Exception:
            rollback()
        return round(bruto, 2), round(liquido, 2), round(taxas, 2), por_forma_taxas

    faturamento_bruto, faturamento_liquido, taxas_total, taxas_formas_dict = resumo_financeiro_periodo(data_inicio_s, data_fim_s)
    fat_bruto_ant, fat_liq_ant, taxas_ant, _ = resumo_financeiro_periodo(prev_inicio.isoformat(), prev_fim.isoformat())

    # Despesas por tipo
    def despesas_periodo(ini, fim):
        fixas = avulsas = 0.0
        try:
            cur.execute("""SELECT LOWER(COALESCE(d.tipo,'')) AS tp, COALESCE(SUM(p.valor),0) AS total
                           FROM despesa_parcelas p JOIN despesas d ON d.id=p.despesa_id
                           WHERE DATE(p.data_vencimento) BETWEEN %s AND %s
                           GROUP BY LOWER(COALESCE(d.tipo,''))""", (ini, fim))
            for r in cur.fetchall():
                if (r['tp'] or '') in ('fixa', 'fixo'):
                    fixas += float(r['total'] or 0)
                else:
                    avulsas += float(r['total'] or 0)
        except Exception:
            rollback()
        return round(fixas, 2), round(avulsas, 2), round(fixas + avulsas, 2)

    despesas_fixas, despesas_avulsas, despesas_total = despesas_periodo(data_inicio_s, data_fim_s)
    desp_fixas_ant, desp_avulsas_ant, despesas_ant = despesas_periodo(prev_inicio.isoformat(), prev_fim.isoformat())
    lucro_liquido = round(faturamento_liquido - despesas_total, 2)
    lucro_ant = round(fat_liq_ant - despesas_ant, 2)
    margem_pct = round(lucro_liquido / faturamento_liquido * 100, 1) if faturamento_liquido else 0
    ticket_medio = 0.0; qtd_vendas = 0; qtd_clientes_cad = 0; qtd_clientes_cad_ant = 0
    try:
        cur.execute("SELECT COUNT(*) AS n, COALESCE(AVG(valor_total),0) AS ticket FROM vendas WHERE DATE(criado_em) BETWEEN %s AND %s", (data_inicio_s, data_fim_s))
        r = cur.fetchone(); qtd_vendas = int(r['n'] or 0); ticket_medio = round(float(r['ticket'] or 0), 2)
        cur.execute("SELECT COUNT(*) AS n FROM clientes WHERE DATE(criado_em) BETWEEN %s AND %s", (data_inicio_s, data_fim_s))
        qtd_clientes_cad = int(cur.fetchone()['n'] or 0)
        cur.execute("SELECT COUNT(*) AS n FROM clientes WHERE DATE(criado_em) BETWEEN %s AND %s", (prev_inicio.isoformat(), prev_fim.isoformat()))
        qtd_clientes_cad_ant = int(cur.fetchone()['n'] or 0)
    except Exception:
        rollback()
    try:
        cur.execute("SELECT COUNT(*) AS n, COALESCE(AVG(valor_total),0) AS ticket FROM vendas WHERE DATE(criado_em) BETWEEN %s AND %s", (prev_inicio.isoformat(), prev_fim.isoformat()))
        r = cur.fetchone(); ticket_ant = round(float(r['ticket'] or 0), 2)
    except Exception:
        rollback(); ticket_ant = 0.0

    taxa_pct = round(taxas_total / faturamento_bruto * 100, 1) if faturamento_bruto else 0
    saude_label = 'Negativa' if margem_pct < 0 else ('Atenção' if margem_pct < 5 else ('Regular' if margem_pct < 10 else ('Saudável' if margem_pct < 15 else 'Excelente')))
    saude_pct = max(0, min(100, round((margem_pct / 20) * 100))) if margem_pct > 0 else 0

    kpis = [
        {'titulo': 'Faturamento Bruto', 'valor': _brl(faturamento_bruto), 'sub': 'Antes das taxas', 'var': _fmt_pct(_pct_atual_anterior(faturamento_bruto, fat_bruto_ant)), 'tom': 'pos' if (faturamento_bruto >= fat_bruto_ant) else 'neg'},
        {'titulo': 'Total de Taxas', 'valor': _brl(taxas_total), 'sub': f'{taxa_pct}% do faturamento', 'var': _fmt_pct(_pct_atual_anterior(taxas_total, taxas_ant)), 'tom': 'neg' if (taxas_total > taxas_ant and taxas_ant) else 'pos'},
        {'titulo': 'Faturamento Líquido', 'valor': _brl(faturamento_liquido), 'sub': '', 'var': _fmt_pct(_pct_atual_anterior(faturamento_liquido, fat_liq_ant)), 'tom': 'pos' if faturamento_liquido >= fat_liq_ant else 'neg'},
        {'titulo': 'Total de Despesas', 'valor': _brl(despesas_total), 'sub': f'Fixas: {_brl(despesas_fixas)} · Avulsas: {_brl(despesas_avulsas)}', 'var': _fmt_pct(_pct_atual_anterior(despesas_total, despesas_ant)), 'tom': 'neg' if despesas_total > despesas_ant and despesas_ant else 'pos'},
        {'titulo': 'Lucro Líquido', 'valor': _brl(lucro_liquido), 'sub': 'Faturamento líquido − despesas', 'var': _fmt_pct(_pct_atual_anterior(lucro_liquido, lucro_ant)), 'tom': 'pos' if lucro_liquido >= 0 else 'neg'},
        {'titulo': 'Margem Líquida', 'valor': f'{str(margem_pct).replace(".", ",")}%', 'sub': saude_label, 'var': '', 'tom': 'pos' if margem_pct >= 10 else ('alerta' if margem_pct >= 0 else 'neg'), 'saude': saude_pct},
        {'titulo': 'Ticket Médio', 'valor': _brl(ticket_medio), 'sub': f'{qtd_vendas} vendas realizadas', 'var': _fmt_pct(_pct_atual_anterior(ticket_medio, ticket_ant)), 'tom': 'pos' if ticket_medio >= ticket_ant else 'neg'},
    ]

    # Tendência mensal: últimos até 12 meses com base no fim do filtro
    meses = []
    for back in range(11, -1, -1):
        y, m = _add_months(data_fim.year, data_fim.month, -back)
        meses.append({'ym': f'{y:04d}-{m:02d}', 'label': f'{MESES_PT[m-1]}/{str(y)[2:]}', 'y': y, 'm': m})

    trend = []
    try:
        # Entradas do caixa bruto/liquido/taxas
        ini_trend = date(meses[0]['y'], meses[0]['m'], 1)
        cur.execute("""SELECT forma_pagamento, valor, criado_em FROM caixa
                       WHERE tipo='entrada' AND criado_em >= %s""", (ini_trend,))
        mensal = {m['ym']: {'bruto': 0.0, 'liquido': 0.0, 'taxas': 0.0, 'fixas': 0.0, 'avulsas': 0.0} for m in meses}
        taxa_cache = {}
        for r in cur.fetchall():
            dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
            ym = dt.strftime('%Y-%m')
            if ym not in mensal: continue
            b = float(r['valor'] or 0); forma = r['forma_pagamento'] or 'outros'
            liq, desc, _ = _liquido_com_taxa(b, forma, dt, taxa_cache)
            mensal[ym]['bruto'] += b; mensal[ym]['liquido'] += liq; mensal[ym]['taxas'] += desc
        cur.execute("""SELECT to_char(date_trunc('month',p.data_vencimento),'YYYY-MM') AS ym,
                       LOWER(COALESCE(d.tipo,'')) AS tp, COALESCE(SUM(p.valor),0) AS total
                       FROM despesa_parcelas p JOIN despesas d ON d.id=p.despesa_id
                       WHERE p.data_vencimento >= %s GROUP BY 1,2""", (ini_trend,))
        for r in cur.fetchall():
            ym = r['ym']
            if ym not in mensal: continue
            if (r['tp'] or '') in ('fixa', 'fixo'):
                mensal[ym]['fixas'] += float(r['total'] or 0)
            else:
                mensal[ym]['avulsas'] += float(r['total'] or 0)
        max_bar = max([mensal[m['ym']]['bruto'] for m in meses] + [1])
        max_liq = max([mensal[m['ym']]['liquido'] for m in meses] + [1])
        max_desp = max([max(mensal[m['ym']]['fixas'], mensal[m['ym']]['avulsas']) for m in meses] + [1])
        lucros = [mensal[m['ym']]['liquido'] - mensal[m['ym']]['fixas'] - mensal[m['ym']]['avulsas'] for m in meses]
        max_abs_lucro = max([abs(x) for x in lucros] + [1])
        for m in meses:
            d = mensal[m['ym']]
            lucro = d['liquido'] - d['fixas'] - d['avulsas']
            trend.append({
                'label': m['label'],
                'bruto': round(d['bruto'], 2), 'liquido': round(d['liquido'], 2),
                'fixas': round(d['fixas'], 2), 'avulsas': round(d['avulsas'], 2), 'lucro': round(lucro, 2),
                'bruto_h': round(d['bruto'] / max_bar * 100) if max_bar else 0,
                'liquido_h': round(d['liquido'] / max_liq * 100) if max_liq else 0,
                'fixas_y': round(90 - (d['fixas'] / max_desp * 76)) if max_desp else 90,
                'avulsas_y': round(90 - (d['avulsas'] / max_desp * 76)) if max_desp else 90,
                'lucro_y': round(52 - (lucro / max_abs_lucro * 38)) if max_abs_lucro else 52,
            })
    except Exception:
        rollback()
    # x coords and SVG polylines
    for i, t in enumerate(trend):
        t['x'] = round(24 + i * (252 / max(len(trend)-1, 1)), 1)
    fix_poly = ' '.join(f"{t['x']},{t['fixas_y']}" for t in trend)
    avul_poly = ' '.join(f"{t['x']},{t['avulsas_y']}" for t in trend)
    lucro_poly = ' '.join(f"{t['x']},{t['lucro_y']}" for t in trend)

    # Taxas por forma de pagamento
    taxas_formas = []
    total_taxas_base = sum(taxas_formas_dict.values()) or 1
    for i, (forma, valor) in enumerate(sorted(taxas_formas_dict.items(), key=lambda kv: kv[1], reverse=True)):
        taxas_formas.append({'label': FORMA_LABEL.get(forma, forma.title()), 'valor': round(valor, 2), 'pct': round(valor / total_taxas_base * 100, 1), 'cor': FORMA_COR.get(forma, PALETA[i % len(PALETA)])})
    if not taxas_formas:
        taxas_formas = [{'label': 'Sem taxas', 'valor': 0, 'pct': 100, 'cor': '#e2e8f0'}]
    ang = 0; stops = []
    for s in taxas_formas:
        ini = ang; ang += s['pct'] * 3.6; stops.append(f"{s['cor']} {ini:.1f}deg {ang:.1f}deg")
    taxas_conic = 'conic-gradient(' + ', '.join(stops) + ')'

    # Top 5 categorias (receita bruta por itens; margem média de cadastro quando houver)
    top_categorias = []; cat_max = 1
    try:
        cur.execute("""SELECT COALESCE(NULLIF(vi.modelo,''),'Sem categoria') AS categoria,
                       COALESCE(SUM(vi.valor_total),0) AS receita, COALESCE(SUM(vi.quantidade),0) AS pecas
                       FROM venda_itens vi JOIN vendas v ON v.id=vi.venda_id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s
                       GROUP BY 1 ORDER BY receita DESC LIMIT 5""", (data_inicio_s, data_fim_s))
        top_categorias = [{'categoria': r['categoria'], 'receita': round(float(r['receita'] or 0), 2), 'pecas': int(r['pecas'] or 0)} for r in cur.fetchall()]
        cat_max = max([c['receita'] for c in top_categorias] + [1])
        for c in top_categorias:
            c['pct'] = round(c['receita'] / cat_max * 100, 1)
    except Exception:
        rollback()

    # Estoque parado com valor e peças
    aging = []; aging_total = estoque_parado_60 = estoque_parado_90 = 0.0; aging_max = 1
    try:
        cur.execute("""SELECT
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))<=30 THEN custo_unitario*quantidade ELSE 0 END),0) AS b0,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em))) BETWEEN 31 AND 60 THEN custo_unitario*quantidade ELSE 0 END),0) AS b1,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em))) BETWEEN 61 AND 90 THEN custo_unitario*quantidade ELSE 0 END),0) AS b2,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))>90 THEN custo_unitario*quantidade ELSE 0 END),0) AS b3,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))<=30 THEN quantidade ELSE 0 END),0) AS q0,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em))) BETWEEN 31 AND 60 THEN quantidade ELSE 0 END),0) AS q1,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em))) BETWEEN 61 AND 90 THEN quantidade ELSE 0 END),0) AS q2,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))>90 THEN quantidade ELSE 0 END),0) AS q3,
            COALESCE(SUM(custo_unitario*quantidade),0) AS total
            FROM estoque WHERE ativo=TRUE AND quantidade>0""")
        a = cur.fetchone()
        aging = [
            {'faixa': '0–30 dias', 'valor': round(float(a['b0']), 2), 'pecas': int(a['q0'] or 0), 'cor': '#16a34a'},
            {'faixa': '31–60 dias', 'valor': round(float(a['b1']), 2), 'pecas': int(a['q1'] or 0), 'cor': '#f59e0b'},
            {'faixa': '61–90 dias', 'valor': round(float(a['b2']), 2), 'pecas': int(a['q2'] or 0), 'cor': '#ea580c'},
            {'faixa': '+90 dias', 'valor': round(float(a['b3']), 2), 'pecas': int(a['q3'] or 0), 'cor': '#dc2626'},
        ]
        aging_total = round(float(a['total']), 2)
        estoque_parado_60 = round(float(a['b2']) + float(a['b3']), 2)
        estoque_parado_90 = round(float(a['b3']), 2)
        aging_max = max([x['valor'] for x in aging] + [1])
    except Exception:
        rollback()

    # Ranking de vendedoras por valor líquido, com peças e clientes cadastrados no período
    vendedoras = []
    try:
        cur.execute("""SELECT v.id, v.vendedora_nome, v.valor_total, v.forma_pagamento, v.criado_em,
                       COALESCE(SUM(vi.quantidade),0) AS pecas
                       FROM vendas v LEFT JOIN venda_itens vi ON vi.venda_id=v.id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s
                       GROUP BY v.id, v.vendedora_nome, v.valor_total, v.forma_pagamento, v.criado_em""", (data_inicio_s, data_fim_s))
        tmp = {}; taxa_cache = {}
        for r in cur.fetchall():
            nome = r['vendedora_nome'] or '—'
            dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
            liq, _desc, _ = _liquido_com_taxa(float(r['valor_total'] or 0), r['forma_pagamento'] or 'outros', dt, taxa_cache)
            obj = tmp.setdefault(nome, {'nome': nome, 'liquido': 0.0, 'vendas': 0, 'pecas': 0, 'clientes': 0})
            obj['liquido'] += liq; obj['vendas'] += 1; obj['pecas'] += int(r['pecas'] or 0)
        try:
            cur.execute("""SELECT COALESCE(u.nome,'—') AS nome, COUNT(c.id) AS clientes
                           FROM clientes c LEFT JOIN usuarios u ON u.id = NULL
                           WHERE 1=0 GROUP BY 1""")
        except Exception:
            rollback()
        # Clientes cadastrados por vendedora não possui vínculo direto no schema atual; manter 0 até existir o vínculo.
        vendedoras = sorted(tmp.values(), key=lambda x: x['liquido'], reverse=True)[:5]
        for v in vendedoras:
            v['liquido'] = round(v['liquido'], 2)
            v['ticket'] = round(v['liquido'] / v['vendas'], 2) if v['vendas'] else 0
    except Exception:
        rollback()

    # Top 5 clientes por valor líquido
    top_clientes = []
    try:
        cur.execute("""SELECT v.cliente_nome AS nome, v.valor_total, v.forma_pagamento, v.criado_em,
                       v.id, COALESCE(SUM(vi.quantidade),0) AS pecas
                       FROM vendas v LEFT JOIN venda_itens vi ON vi.venda_id=v.id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s AND COALESCE(v.cliente_nome,'') <> ''
                       GROUP BY v.id, v.cliente_nome, v.valor_total, v.forma_pagamento, v.criado_em""", (data_inicio_s, data_fim_s))
        tmp = {}; taxa_cache = {}
        for r in cur.fetchall():
            nome = r['nome'] or 'Cliente não informado'
            dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
            liq, _desc, _ = _liquido_com_taxa(float(r['valor_total'] or 0), r['forma_pagamento'] or 'outros', dt, taxa_cache)
            obj = tmp.setdefault(nome, {'nome': nome, 'liquido': 0.0, 'compras': 0, 'pecas': 0, 'ultima': dt})
            obj['liquido'] += liq; obj['compras'] += 1; obj['pecas'] += int(r['pecas'] or 0); obj['ultima'] = max(obj['ultima'], dt)
        top_clientes = sorted(tmp.values(), key=lambda x: x['liquido'], reverse=True)[:5]
        for c in top_clientes:
            c['liquido'] = round(c['liquido'], 2)
            c['ticket'] = round(c['liquido'] / c['compras'], 2) if c['compras'] else 0
            c['ultima_fmt'] = c['ultima'].strftime('%d/%m/%y')
    except Exception:
        rollback()

    # Alertas inteligentes do rodapé
    insights = []
    fat_var = _pct_atual_anterior(faturamento_liquido, fat_liq_ant)
    luc_var = _pct_atual_anterior(lucro_liquido, lucro_ant)
    tick_var = _pct_atual_anterior(ticket_medio, ticket_ant)
    cli_var = _pct_atual_anterior(qtd_clientes_cad, qtd_clientes_cad_ant)
    if fat_var is not None:
        insights.append({'tom': 'bom' if fat_var >= 0 else 'alerta', 'tx': f"Faturamento líquido {'cresceu' if fat_var >= 0 else 'caiu'} {abs(fat_var)}% em relação ao período anterior."})
    if luc_var is not None:
        insights.append({'tom': 'bom' if luc_var >= 0 else 'ruim', 'tx': f"Lucro líquido {'cresceu' if luc_var >= 0 else 'caiu'} {abs(luc_var)}% em relação ao período anterior."})
    if tick_var is not None:
        insights.append({'tom': 'bom' if tick_var >= 0 else 'alerta', 'tx': f"Ticket médio {'cresceu' if tick_var >= 0 else 'caiu'} {abs(tick_var)}% em relação ao período anterior."})
    if cli_var is not None:
        insights.append({'tom': 'bom' if cli_var >= 0 else 'alerta', 'tx': f"Clientes cadastrados {'cresceram' if cli_var >= 0 else 'caíram'} {abs(cli_var)}% em relação ao período anterior."})
    if estoque_parado_90 > 0:
        insights.append({'tom': 'alerta', 'tx': f"Estoque parado acima de 90 dias: {_brl(estoque_parado_90)}."})

    cur.close(); close_db(conn)
    periodo_label = f"{data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}"
    ctx = get_ctx()
    ctx.update(
        data_inicio=data_inicio_s, data_fim=data_fim_s, periodo_label=periodo_label,
        hoje=hoje.strftime('%A, %d de %B de %Y').capitalize(),
        kpis=kpis, resultado={'faturamento_bruto': faturamento_bruto, 'taxas_total': taxas_total,
                               'faturamento_liquido': faturamento_liquido, 'despesas': despesas_total,
                               'despesas_fixas': despesas_fixas, 'despesas_avulsas': despesas_avulsas,
                               'lucro_liquido': lucro_liquido, 'margem_pct': margem_pct, 'ticket_medio': ticket_medio},
        trend=trend, fix_poly=fix_poly, avul_poly=avul_poly, lucro_poly=lucro_poly,
        taxas_formas=taxas_formas, taxas_conic=taxas_conic, top_categorias=top_categorias, cat_max=cat_max,
        aging=aging, aging_total=aging_total, aging_max=aging_max, estoque_parado_60=estoque_parado_60,
        vendedoras=vendedoras, top_clientes=top_clientes, insights=insights, brl=_brl, kbrl=_kbrl)
    return render_template('dashboard.html', **ctx)


def register(app):
    app.add_url_rule('/dashboard', 'dashboard_view', dashboard_view)
