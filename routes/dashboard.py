"""Dashboard Executivo V124 — layout moderno em uma página só (estende base.html).

Estrutura:
  • Cabeçalho com período e comparação
  • 7 KPIs com ícone, valor, comparação com o período anterior e barra de saúde
  • Gráficos: faturamento bruto/líquido (barras com rótulo + eixo), despesas
    fixas × avulsas e evolução do lucro (linhas com rótulo), taxas por forma (donut)
  • Top categorias, ranking de vendedoras, estoque parado, top clientes
  • Alertas inteligentes no rodapé
"""
import math
from datetime import date, timedelta
from flask import render_template, request
from db import get_db, close_db
from config import hoje_app, agora_app, inicio_mes_app, fim_mes_app
from auth import login_required, get_ctx
from utils import get_taxa_vigente, calcular_liquido

MESES_PT = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
FORMAS_COM_TAXA = ('credito_vista', 'credito_parcelado', 'debito', 'link')
FORMA_LABEL = {
    'dinheiro': 'Dinheiro', 'pix': 'PIX', 'debito': 'Cartão de Débito',
    'credito_vista': 'Crédito à vista', 'credito_parcelado': 'Crédito parcelado',
    'link': 'Link', 'transferencia': 'Transferência', 'crediario': 'Crediário', 'outros': 'Outros'
}
FORMA_COR = {
    'dinheiro': '#f59e0b', 'pix': '#7c3aed', 'debito': '#16a34a',
    'credito_vista': '#2563eb', 'credito_parcelado': '#3b82f6',
    'link': '#0891b2', 'transferencia': '#0284c7', 'crediario': '#db2777', 'outros': '#94a3b8'
}
PALETA = ['#2563eb', '#16a34a', '#7c3aed', '#f59e0b', '#db2777', '#0891b2', '#64748b']


def _brl(v):
    return ("R$ " + f"{float(v or 0):,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def _kbrl(v):
    v = float(v or 0); s = '-' if v < 0 else ''; a = abs(v)
    if a >= 1000:
        return s + f"{a/1000:.1f}".replace('.', ',') + 'k'
    return s + f"{a:.0f}"


def _add_months(y, m, delta):
    idx = (y * 12 + (m - 1)) + delta
    return idx // 12, idx % 12 + 1


def _parse_date(value, fallback):
    try:
        return date.fromisoformat(value)
    except Exception:
        return date.fromisoformat(fallback)


def _pct(atual, anterior):
    atual = float(atual or 0); anterior = float(anterior or 0)
    if anterior == 0:
        return None
    return round((atual - anterior) / anterior * 100, 1)


def _delta(atual, anterior):
    """Dict de comparação: texto, direção (up/down) e classe de cor (pos/neg)."""
    p = _pct(atual, anterior)
    if p is None:
        return None
    return {'txt': f"{abs(p):.1f}".replace('.', ',') + '%', 'dir': 'up' if p >= 0 else 'down',
            'cls': 'pos' if p >= 0 else 'neg'}


def _delta_pp(atual_pp, anterior_pp):
    diff = round(float(atual_pp or 0) - float(anterior_pp or 0), 1)
    return {'txt': f"{abs(diff):.1f}".replace('.', ',') + ' p.p.', 'dir': 'up' if diff >= 0 else 'down',
            'cls': 'pos' if diff >= 0 else 'neg'}


def _nice_top(maxv):
    """Topo 'redondo' do eixo Y (4 divisões agradáveis) acima do valor máximo."""
    maxv = float(maxv or 0)
    if maxv <= 0:
        return 1.0
    raw = maxv / 4.0
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for mult in (1, 2, 2.5, 5, 10):
        if mult * mag * 4 >= maxv:
            return mult * mag * 4
    return 10 * mag * 4


def _liquido_com_taxa(bruto, forma, dt, taxa_cache):
    bruto = float(bruto or 0); forma = forma or 'outros'
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
    di, df = data_inicio.isoformat(), data_fim.isoformat()

    def rollback():
        try: conn.rollback()
        except Exception: pass

    dias = (data_fim - data_inicio).days + 1
    prev_fim = data_inicio - timedelta(days=1)
    prev_inicio = prev_fim - timedelta(days=dias - 1)
    pi, pf = prev_inicio.isoformat(), prev_fim.isoformat()

    # ── Faturamento bruto/líquido/taxas pelo caixa (base financeira real) ──
    def financeiro(ini, fim):
        bruto = liquido = taxas = 0.0
        por_forma = {}
        cache = {}
        try:
            cur.execute("""SELECT forma_pagamento, valor, criado_em FROM caixa
                           WHERE tipo='entrada' AND DATE(criado_em) BETWEEN %s AND %s""", (ini, fim))
            for r in cur.fetchall():
                b = float(r['valor'] or 0)
                forma = r['forma_pagamento'] or 'outros'
                dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
                liq, desc, _ = _liquido_com_taxa(b, forma, dt, cache)
                bruto += b; liquido += liq; taxas += desc
                if desc:
                    por_forma[forma] = por_forma.get(forma, 0.0) + desc
        except Exception:
            rollback()
        return round(bruto, 2), round(liquido, 2), round(taxas, 2), por_forma

    fat_bruto, fat_liquido, taxas_total, taxas_por_forma = financeiro(di, df)
    fat_bruto_a, fat_liquido_a, taxas_a, _ = financeiro(pi, pf)

    # ── Despesas por tipo ──
    def despesas(ini, fim):
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

    desp_fixas, desp_avulsas, desp_total = despesas(di, df)
    _df_a, _da_a, desp_total_a = despesas(pi, pf)

    lucro = round(fat_liquido - desp_total, 2)
    lucro_a = round(fat_liquido_a - desp_total_a, 2)
    margem = round(lucro / fat_liquido * 100, 1) if fat_liquido else 0
    margem_a = round(lucro_a / fat_liquido_a * 100, 1) if fat_liquido_a else 0
    taxa_pct = round(taxas_total / fat_bruto * 100, 1) if fat_bruto else 0

    # Ticket médio / vendas / clientes
    ticket = ticket_a = 0.0; qtd_vendas = 0; cli_cad = cli_cad_a = 0
    try:
        cur.execute("SELECT COUNT(*) n, COALESCE(AVG(valor_total),0) t FROM vendas WHERE DATE(criado_em) BETWEEN %s AND %s", (di, df))
        r = cur.fetchone(); qtd_vendas = int(r['n'] or 0); ticket = round(float(r['t'] or 0), 2)
        cur.execute("SELECT COALESCE(AVG(valor_total),0) t FROM vendas WHERE DATE(criado_em) BETWEEN %s AND %s", (pi, pf))
        ticket_a = round(float(cur.fetchone()['t'] or 0), 2)
        cur.execute("SELECT COUNT(*) n FROM clientes WHERE DATE(criado_em) BETWEEN %s AND %s", (di, df))
        cli_cad = int(cur.fetchone()['n'] or 0)
        cur.execute("SELECT COUNT(*) n FROM clientes WHERE DATE(criado_em) BETWEEN %s AND %s", (pi, pf))
        cli_cad_a = int(cur.fetchone()['n'] or 0)
    except Exception:
        rollback()

    saude_label = ('Negativa' if margem < 0 else 'Atenção' if margem < 5 else 'Regular'
                   if margem < 10 else 'Saudável' if margem < 15 else 'Excelente')
    saude_pos = max(4, min(96, round(margem / 20 * 100))) if margem > 0 else 2

    kpi = {
        'fat_bruto': _brl(fat_bruto), 'd_fat_bruto': _delta(fat_bruto, fat_bruto_a),
        'taxas': _brl(taxas_total), 'taxa_pct': f"{taxa_pct}".replace('.', ',') + '% do faturamento',
        'd_taxas': _delta(taxas_total, taxas_a),
        'fat_liquido': _brl(fat_liquido), 'd_fat_liquido': _delta(fat_liquido, fat_liquido_a),
        'despesas': _brl(desp_total), 'desp_fixas': _brl(desp_fixas), 'desp_avulsas': _brl(desp_avulsas),
        'd_despesas': _delta(desp_total, desp_total_a),
        'lucro': _brl(lucro), 'd_lucro': _delta(lucro, lucro_a),
        'margem': f"{margem}".replace('.', ',') + '%', 'saude_label': saude_label, 'saude_pos': saude_pos,
        'd_margem': _delta_pp(margem, margem_a),
        'ticket': _brl(ticket), 'qtd_vendas': qtd_vendas, 'd_ticket': _delta(ticket, ticket_a),
    }

    # ── Tendência: 12 meses ──
    meses = []
    for back in range(11, -1, -1):
        y, m = _add_months(data_fim.year, data_fim.month, -back)
        meses.append({'ym': f'{y:04d}-{m:02d}', 'label': f'{MESES_PT[m-1]}/{str(y)[2:]}'})
    trend = []
    try:
        ini_trend = date.fromisoformat(meses[0]['ym'] + '-01')
        mensal = {mm['ym']: {'bruto': 0.0, 'liquido': 0.0, 'fixas': 0.0, 'avulsas': 0.0} for mm in meses}
        cache = {}
        cur.execute("SELECT forma_pagamento, valor, criado_em FROM caixa WHERE tipo='entrada' AND criado_em >= %s", (ini_trend,))
        for r in cur.fetchall():
            dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
            ym = dt.strftime('%Y-%m')
            if ym not in mensal: continue
            b = float(r['valor'] or 0)
            liq, _d, _p = _liquido_com_taxa(b, r['forma_pagamento'] or 'outros', dt, cache)
            mensal[ym]['bruto'] += b; mensal[ym]['liquido'] += liq
        cur.execute("""SELECT to_char(date_trunc('month',p.data_vencimento),'YYYY-MM') ym,
                       LOWER(COALESCE(d.tipo,'')) tp, COALESCE(SUM(p.valor),0) total
                       FROM despesa_parcelas p JOIN despesas d ON d.id=p.despesa_id
                       WHERE p.data_vencimento >= %s GROUP BY 1,2""", (ini_trend,))
        for r in cur.fetchall():
            ym = r['ym']
            if ym not in mensal: continue
            if (r['tp'] or '') in ('fixa', 'fixo'):
                mensal[ym]['fixas'] += float(r['total'] or 0)
            else:
                mensal[ym]['avulsas'] += float(r['total'] or 0)
        for mm in meses:
            d = mensal[mm['ym']]
            trend.append({'label': mm['label'], 'bruto': round(d['bruto'], 2), 'liquido': round(d['liquido'], 2),
                          'fixas': round(d['fixas'], 2), 'avulsas': round(d['avulsas'], 2),
                          'lucro': round(d['liquido'] - d['fixas'] - d['avulsas'], 2)})
    except Exception:
        rollback()

    # Eixos + alturas + rótulos
    eixo_fat = _nice_top(max([t['bruto'] for t in trend] + [t['liquido'] for t in trend] + [1]))
    eixo_desp = _nice_top(max([max(t['fixas'], t['avulsas']) for t in trend] + [1]))
    lucros = [t['lucro'] for t in trend] or [0]
    lhi = _nice_top(max(lucros + [0]))
    llo = -_nice_top(-min(lucros + [0])) if min(lucros + [0]) < 0 else 0
    lrng = (lhi - llo) or 1
    n = len(trend)
    for i, t in enumerate(trend):
        t['xp'] = round(i / max(n - 1, 1) * 100, 2)
        t['bruto_h'] = round(t['bruto'] / eixo_fat * 100, 1)
        t['liquido_h'] = round(t['liquido'] / eixo_fat * 100, 1)
        t['fixas_yp'] = round((eixo_desp - t['fixas']) / eixo_desp * 100, 2)
        t['avulsas_yp'] = round((eixo_desp - t['avulsas']) / eixo_desp * 100, 2)
        t['lucro_yp'] = round((lhi - t['lucro']) / lrng * 100, 2)
        t['bruto_k'] = _kbrl(t['bruto']); t['liquido_k'] = _kbrl(t['liquido'])
        t['fixas_k'] = _kbrl(t['fixas']); t['avulsas_k'] = _kbrl(t['avulsas']); t['lucro_k'] = _kbrl(t['lucro'])
    fix_poly = ' '.join(f"{t['xp']},{t['fixas_yp']}" for t in trend)
    avul_poly = ' '.join(f"{t['xp']},{t['avulsas_yp']}" for t in trend)
    lucro_poly = ' '.join(f"{t['xp']},{t['lucro_yp']}" for t in trend)
    lucro_zero_yp = round((lhi - 0) / lrng * 100, 2)
    eixo_fat_ticks = [_kbrl(eixo_fat * i / 4) for i in (4, 3, 2, 1, 0)]
    eixo_desp_ticks = [_kbrl(eixo_desp * i / 4) for i in (4, 3, 2, 1, 0)]
    eixo_lucro_ticks = [_kbrl(lhi - (lhi - llo) * i / 4) for i in range(5)]

    # ── Taxas por forma (donut + rótulos internos) ──
    taxas_formas = []
    base_taxas = sum(taxas_por_forma.values()) or 1
    for i, (forma, valor) in enumerate(sorted(taxas_por_forma.items(), key=lambda kv: kv[1], reverse=True)):
        taxas_formas.append({'label': FORMA_LABEL.get(forma, forma.title()), 'valor': round(valor, 2),
                             'pct': round(valor / base_taxas * 100, 1), 'cor': FORMA_COR.get(forma, PALETA[i % len(PALETA)])})
    if not taxas_formas:
        taxas_formas = [{'label': 'Sem taxas no período', 'valor': 0, 'pct': 100, 'cor': '#e2e8f0'}]
    ang = 0.0; stops = []; donut_labels = []
    for s in taxas_formas:
        sweep = s['pct'] * 3.6
        stops.append(f"{s['cor']} {ang:.1f}deg {ang+sweep:.1f}deg")
        if s['pct'] >= 5:
            mid = math.radians(ang + sweep / 2 - 90)
            donut_labels.append({'pct': f"{round(s['pct'])}%", 'x': round(50 + 37 * math.cos(mid), 1),
                                 'y': round(50 + 37 * math.sin(mid), 1)})
        ang += sweep
    taxas_conic = 'conic-gradient(' + ', '.join(stops) + ')'

    # ── Top 5 categorias (modelo) ──
    top_categorias = []
    try:
        cur.execute("""SELECT COALESCE(NULLIF(vi.modelo,''),'Sem categoria') categoria,
                       COALESCE(SUM(vi.valor_total),0) receita, COALESCE(SUM(vi.quantidade),0) pecas
                       FROM venda_itens vi JOIN vendas v ON v.id=vi.venda_id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s GROUP BY 1 ORDER BY receita DESC LIMIT 5""", (di, df))
        top_categorias = [{'categoria': r['categoria'], 'receita': round(float(r['receita'] or 0), 2),
                           'pecas': int(r['pecas'] or 0)} for r in cur.fetchall()]
    except Exception:
        rollback()
    cat_max = max([c['receita'] for c in top_categorias] + [1])
    cat_total = round(sum(c['receita'] for c in top_categorias), 2)
    for c in top_categorias:
        c['bar'] = round(c['receita'] / cat_max * 100, 1)
        c['pct_fat'] = round(c['receita'] / fat_bruto * 100, 1) if fat_bruto else 0
    cat_total_pct = round(cat_total / fat_bruto * 100, 1) if fat_bruto else 0

    # ── Estoque parado (aging) ──
    aging = []; aging_total = estoque_parado_60 = 0.0
    try:
        cur.execute("""SELECT
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))<=30 THEN custo_unitario*quantidade ELSE 0 END),0) b0,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em))) BETWEEN 31 AND 60 THEN custo_unitario*quantidade ELSE 0 END),0) b1,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em))) BETWEEN 61 AND 90 THEN custo_unitario*quantidade ELSE 0 END),0) b2,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))>90 THEN custo_unitario*quantidade ELSE 0 END),0) b3,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))<=30 THEN quantidade ELSE 0 END),0) q0,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em))) BETWEEN 31 AND 60 THEN quantidade ELSE 0 END),0) q1,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em))) BETWEEN 61 AND 90 THEN quantidade ELSE 0 END),0) q2,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))>90 THEN quantidade ELSE 0 END),0) q3,
            COALESCE(SUM(custo_unitario*quantidade),0) total
            FROM estoque WHERE ativo=TRUE AND quantidade>0""")
        a = cur.fetchone()
        aging = [
            {'faixa': '0 - 30 dias', 'valor': round(float(a['b0']), 2), 'pecas': int(a['q0'] or 0), 'cor': '#16a34a'},
            {'faixa': '31 - 60 dias', 'valor': round(float(a['b1']), 2), 'pecas': int(a['q1'] or 0), 'cor': '#eab308'},
            {'faixa': '61 - 90 dias', 'valor': round(float(a['b2']), 2), 'pecas': int(a['q2'] or 0), 'cor': '#f97316'},
            {'faixa': '+ 90 dias', 'valor': round(float(a['b3']), 2), 'pecas': int(a['q3'] or 0), 'cor': '#dc2626'},
        ]
        aging_total = round(float(a['total']), 2)
        estoque_parado_60 = round(float(a['b2']) + float(a['b3']), 2)
    except Exception:
        rollback()
    base_ag = aging_total or 1
    for a in aging:
        a['pct'] = round(a['valor'] / base_ag * 100, 1)
    estoque_parado_60_pct = round(estoque_parado_60 / base_ag * 100, 1)

    # ── Ranking de vendedoras (líquido) ──
    vendedoras = []
    try:
        cur.execute("""SELECT v.id, v.vendedora_nome, v.valor_total, v.forma_pagamento, v.criado_em, v.cliente_id,
                       COALESCE(SUM(vi.quantidade),0) pecas
                       FROM vendas v LEFT JOIN venda_itens vi ON vi.venda_id=v.id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s
                       GROUP BY v.id, v.vendedora_nome, v.valor_total, v.forma_pagamento, v.criado_em, v.cliente_id""", (di, df))
        tmp = {}; cache = {}
        for r in cur.fetchall():
            nome = r['vendedora_nome'] or '—'
            dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
            liq, _d, _p = _liquido_com_taxa(float(r['valor_total'] or 0), r['forma_pagamento'] or 'outros', dt, cache)
            o = tmp.setdefault(nome, {'nome': nome, 'liquido': 0.0, 'vendas': 0, 'pecas': 0, 'cli': set()})
            o['liquido'] += liq; o['vendas'] += 1; o['pecas'] += int(r['pecas'] or 0)
            if r['cliente_id']:
                o['cli'].add(r['cliente_id'])
        vendedoras = sorted(tmp.values(), key=lambda x: x['liquido'], reverse=True)[:5]
        vmax = max([v['liquido'] for v in vendedoras] + [1])
        for v in vendedoras:
            v['clientes'] = len(v['cli'])
            v['ticket'] = round(v['liquido'] / v['vendas'], 2) if v['vendas'] else 0
            v['bar'] = round(v['liquido'] / vmax * 100, 1)
            v['ini'] = ''.join([p[0] for p in v['nome'].split()[:2]]).upper() or '—'
            v['liquido'] = round(v['liquido'], 2)
    except Exception:
        rollback()
    vend_total = round(sum(v['liquido'] for v in vendedoras), 2)

    # ── Top 5 clientes (líquido) ──
    top_clientes = []
    try:
        cur.execute("""SELECT v.cliente_nome nome, v.valor_total, v.forma_pagamento, v.criado_em, v.id,
                       COALESCE(SUM(vi.quantidade),0) pecas
                       FROM vendas v LEFT JOIN venda_itens vi ON vi.venda_id=v.id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s AND COALESCE(v.cliente_nome,'')<>''
                       GROUP BY v.id, v.cliente_nome, v.valor_total, v.forma_pagamento, v.criado_em""", (di, df))
        tmp = {}; cache = {}
        for r in cur.fetchall():
            nome = r['nome'] or 'Cliente'
            dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
            liq, _d, _p = _liquido_com_taxa(float(r['valor_total'] or 0), r['forma_pagamento'] or 'outros', dt, cache)
            o = tmp.setdefault(nome, {'nome': nome, 'liquido': 0.0, 'compras': 0, 'pecas': 0, 'ultima': dt})
            o['liquido'] += liq; o['compras'] += 1; o['pecas'] += int(r['pecas'] or 0); o['ultima'] = max(o['ultima'], dt)
        top_clientes = sorted(tmp.values(), key=lambda x: x['liquido'], reverse=True)[:5]
        cmax = max([c['liquido'] for c in top_clientes] + [1])
        for c in top_clientes:
            c['ticket'] = round(c['liquido'] / c['compras'], 2) if c['compras'] else 0
            c['bar'] = round(c['liquido'] / cmax * 100, 1)
            c['ultima_fmt'] = c['ultima'].strftime('%d/%m/%Y')
            c['liquido'] = round(c['liquido'], 2)
    except Exception:
        rollback()
    cli_total = round(sum(c['liquido'] for c in top_clientes), 2)

    # ── Alertas inteligentes ──
    insights = []
    def _ins(rotulo, atual, anterior, icon):
        d = _delta(atual, anterior)
        if d is None:
            return
        cresceu = d['dir'] == 'up'
        insights.append({'icon': icon, 'cls': 'bom' if cresceu else 'alerta', 'titulo': rotulo,
                         'txt': f"{'cresceu' if cresceu else 'caiu'} {d['txt']} em relação ao período anterior"})
    _ins('Faturamento líquido', fat_liquido, fat_liquido_a, 'fat')
    _ins('Lucro líquido', lucro, lucro_a, 'lucro')
    _ins('Ticket médio', ticket, ticket_a, 'ticket')
    _ins('Clientes cadastrados', cli_cad, cli_cad_a, 'cli')
    todos_subindo = all(i['cls'] == 'bom' for i in insights) and insights
    insights_resumo = ('Todos os indicadores estratégicos apresentaram crescimento no período!'
                       if todos_subindo else 'Acompanhe os indicadores em queda para corrigir a rota.')

    cur.close(); close_db(conn)
    periodo_label = f"{data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}"
    atualizado = agora_app().strftime('%d/%m/%Y às %H:%M')

    ctx = get_ctx()
    ctx.update(
        data_inicio=di, data_fim=df, periodo_label=periodo_label, atualizado=atualizado,
        kpi=kpi, trend=trend,
        eixo_fat_ticks=eixo_fat_ticks, eixo_desp_ticks=eixo_desp_ticks, eixo_lucro_ticks=eixo_lucro_ticks,
        fix_poly=fix_poly, avul_poly=avul_poly, lucro_poly=lucro_poly, lucro_zero_yp=lucro_zero_yp,
        taxas_total=_brl(taxas_total), taxa_pct_fat=f"{taxa_pct}".replace('.', ',') + '% do faturamento bruto',
        taxas_formas=taxas_formas, taxas_conic=taxas_conic, donut_labels=donut_labels,
        top_categorias=top_categorias, cat_total=cat_total, cat_total_pct=cat_total_pct,
        aging=aging, estoque_parado_60=estoque_parado_60, estoque_parado_60_pct=estoque_parado_60_pct,
        vendedoras=vendedoras, vend_total=vend_total, top_clientes=top_clientes, cli_total=cli_total,
        insights=insights, insights_resumo=insights_resumo, todos_subindo=bool(todos_subindo),
        brl=_brl, kbrl=_kbrl)
    return render_template('dashboard.html', **ctx)


def register(app):
    app.add_url_rule('/dashboard', 'dashboard_view', dashboard_view)
