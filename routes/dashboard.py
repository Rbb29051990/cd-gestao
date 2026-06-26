"""Dashboard Executivo V137 — layout moderno em uma página só (estende base.html).

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
    # Paleta V130 (definida pelo cliente): cores por forma de pagamento
    'credito_parcelado': '#dc2626',  # vermelho
    'credito_vista': '#eab308',      # amarelo
    'debito': '#16a34a',             # verde
    'link': '#2563eb',               # azul
    'pix': '#f97316',                # laranja (não citado pelo cliente)
    'dinheiro': '#a855f7',           # roxo (não citado pelo cliente)
    'transferencia': '#0284c7', 'crediario': '#db2777', 'outros': '#94a3b8'
}
PALETA = ['#2563eb', '#16a34a', '#7c3aed', '#f59e0b', '#db2777', '#0891b2', '#64748b']


def _brl(v):
    return ("R$ " + f"{float(v or 0):,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def _kbrl(v):
    v = float(v or 0); s = '-' if v < 0 else ''; a = abs(v)
    if a >= 1000:
        return s + f"{a/1000:.1f}".replace('.', ',') + 'k'
    return s + f"{a:.0f}"


def _brl0(v):
    """Moeda BR arredondada sem centavos, para rótulos de gráfico (ex.: 'R$ 9.500')."""
    n = round(float(v or 0))
    return "R$ " + f"{n:,}".replace(",", ".")


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
    return {'txt': f"{abs(p):.0f}%", 'dir': 'up' if p >= 0 else 'down',
            'cls': 'pos' if p >= 0 else 'neg'}


def _delta_pp(atual_pp, anterior_pp):
    diff = round(float(atual_pp or 0) - float(anterior_pp or 0), 1)
    return {'txt': f"{abs(diff):.0f} p.p.", 'dir': 'up' if diff >= 0 else 'down',
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


def _liquido_com_taxa(bruto, forma, dt, taxa_cache, parcelas=None):
    bruto = float(bruto or 0); forma = forma or 'outros'
    if forma in FORMAS_COM_TAXA:
        k = dt.isoformat()
        if k not in taxa_cache:
            taxa_cache[k] = get_taxa_vigente(dt)
        liq, desc, pct = calcular_liquido(bruto, forma, taxa_cache[k], parcelas)
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
            cur.execute("""SELECT forma_pagamento, valor, criado_em, parcelas FROM caixa
                           WHERE tipo='entrada' AND DATE(criado_em) BETWEEN %s AND %s""", (ini, fim))
            for r in cur.fetchall():
                b = float(r['valor'] or 0)
                forma = r['forma_pagamento'] or 'outros'
                dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
                liq, desc, _ = _liquido_com_taxa(b, forma, dt, cache, r.get('parcelas'))
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
        'taxas': _brl(taxas_total), 'taxa_pct': f"{round(taxa_pct)}% do faturamento",
        'd_taxas': _delta(taxas_total, taxas_a),
        'fat_liquido': _brl(fat_liquido), 'd_fat_liquido': _delta(fat_liquido, fat_liquido_a),
        'despesas': _brl(desp_total), 'desp_fixas': _brl(desp_fixas), 'desp_avulsas': _brl(desp_avulsas),
        'd_despesas': _delta(desp_total, desp_total_a),
        'lucro': _brl(lucro), 'd_lucro': _delta(lucro, lucro_a), 'lucro_neg': lucro < 0,
        'margem': f"{round(margem)}%", 'margem_neg': margem < 0, 'saude_label': saude_label, 'saude_pos': saude_pos,
        'd_margem': _delta_pp(margem, margem_a),
        'ticket': _brl(ticket), 'qtd_vendas': qtd_vendas, 'd_ticket': _delta(ticket, ticket_a),
    }

    # ── Tendência: VALOR TOTAL POR MÊS dentro do período selecionado ──
    # O cliente pediu o total do mês (não dia a dia / semana a semana), mesmo
    # com o mês ainda em aberto. Cada barra/ponto = total consolidado do mês.
    gran_label = 'Por mês'
    trend = []
    buckets = []
    y, m = data_inicio.year, data_inicio.month
    while (y, m) <= (data_fim.year, data_fim.month):
        ny, nm = _add_months(y, m, 1)
        fim_mes = min(date(ny, nm, 1) - timedelta(days=1), data_fim)
        buckets.append({'ini': max(date(y, m, 1), data_inicio), 'fim': fim_mes, 'label': f'{MESES_PT[m-1]}/{str(y)[2:]}'})
        y, m = ny, nm
    buckets = buckets[-12:]

    trend_ini, trend_fim = buckets[0]['ini'].isoformat(), buckets[-1]['fim'].isoformat()

    def _bidx(dt):
        if hasattr(dt, 'date'):
            dt = dt.date()
        if not isinstance(dt, date):
            return None
        for i, b in enumerate(buckets):
            if b['ini'] <= dt <= b['fim']:
                return i
        return None

    try:
        agg = [{'bruto': 0.0, 'liquido': 0.0, 'fixas': 0.0, 'avulsas': 0.0} for _ in buckets]
        cache = {}
        cur.execute("SELECT forma_pagamento, valor, criado_em, parcelas FROM caixa WHERE tipo='entrada' AND DATE(criado_em) BETWEEN %s AND %s", (trend_ini, trend_fim))
        for r in cur.fetchall():
            dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
            i = _bidx(dt)
            if i is None:
                continue
            b = float(r['valor'] or 0)
            liq, _d, _p = _liquido_com_taxa(b, r['forma_pagamento'] or 'outros', dt, cache, r.get('parcelas'))
            agg[i]['bruto'] += b
            agg[i]['liquido'] += liq
        cur.execute("""SELECT p.data_vencimento dv, LOWER(COALESCE(d.tipo,'')) tp, p.valor v
                       FROM despesa_parcelas p JOIN despesas d ON d.id=p.despesa_id
                       WHERE DATE(p.data_vencimento) BETWEEN %s AND %s""", (trend_ini, trend_fim))
        for r in cur.fetchall():
            i = _bidx(r['dv']) if r['dv'] else None
            if i is None:
                continue
            v = float(r['v'] or 0)
            if (r['tp'] or '') in ('fixa', 'fixo'):
                agg[i]['fixas'] += v
            else:
                agg[i]['avulsas'] += v
        for i, b in enumerate(buckets):
            a = agg[i]
            trend.append({'label': b['label'], 'bruto': round(a['bruto'], 2), 'liquido': round(a['liquido'], 2),
                          'fixas': round(a['fixas'], 2), 'avulsas': round(a['avulsas'], 2),
                          'lucro': round(a['liquido'] - a['fixas'] - a['avulsas'], 2)})
    except Exception:
        rollback()

    # ── Preparação visual dos gráficos ──
    dense = len(trend) > 14
    passo_lbl = max(1, (len(trend) + 7) // 8) if dense else 1

    def _ticks_0(maxv):
        top = _nice_top(maxv)
        return [_kbrl(top), _kbrl(top * 0.75), _kbrl(top * 0.50), _kbrl(top * 0.25), '0']

    def _line_points(key, minv, maxv):
        pts = []
        n = max(len(trend) - 1, 1)
        span = (maxv - minv) or 1
        for i, t in enumerate(trend):
            xp = round(i / n * 100, 2)
            yp = round(100 - ((float(t.get(key, 0) or 0) - minv) / span * 100), 2)
            t[key + '_yp'] = max(0, min(100, yp))
            t['xp'] = xp
            pts.append(f"{xp},{t[key + '_yp']}")
        return ' '.join(pts)

    max_fat = max([float(t.get('bruto', 0) or 0) for t in trend] + [float(t.get('liquido', 0) or 0) for t in trend] + [1])
    top_fat = _nice_top(max_fat)
    eixo_fat_ticks = _ticks_0(max_fat)

    max_desp = max([float(t.get('fixas', 0) or 0) for t in trend] + [float(t.get('avulsas', 0) or 0) for t in trend] + [1])
    top_desp = _nice_top(max_desp)
    eixo_desp_ticks = _ticks_0(max_desp)

    luc_vals = [float(t.get('lucro', 0) or 0) for t in trend] or [0]
    luc_min = min(luc_vals + [0])
    luc_max = max(luc_vals + [0])
    luc_span = max(abs(luc_min), abs(luc_max), 1)
    luc_min, luc_max = -luc_span, luc_span
    eixo_lucro_ticks = [_kbrl(luc_max), _kbrl(luc_max/2), '0', _kbrl(luc_min/2), _kbrl(luc_min)]
    lucro_zero_yp = 50

    for i, t in enumerate(trend):
        t['show_lbl'] = (i % passo_lbl == 0) or (i == len(trend) - 1)
        # valores em R$ (com centavos) exibidos no tooltip ao passar o mouse
        t['bruto_k'] = _brl(t.get('bruto'))
        t['liquido_k'] = _brl(t.get('liquido'))
        t['fixas_k'] = _brl(t.get('fixas'))
        t['avulsas_k'] = _brl(t.get('avulsas'))
        t['lucro_k'] = _brl(t.get('lucro'))
        t['bruto_h'] = round((float(t.get('bruto', 0) or 0) / top_fat) * 100, 2) if top_fat else 0
        t['liquido_h'] = round((float(t.get('liquido', 0) or 0) / top_fat) * 100, 2) if top_fat else 0

    fix_poly = _line_points('fixas', 0, top_desp)
    avul_poly = _line_points('avulsas', 0, top_desp)
    lucro_poly = _line_points('lucro', luc_min, luc_max)

    # ── Taxas por forma (donut + rótulos internos) ──
    taxas_formas = []
    base_taxas = sum(taxas_por_forma.values()) or 1
    for i, (forma, valor) in enumerate(sorted(taxas_por_forma.items(), key=lambda kv: kv[1], reverse=True)):
        taxas_formas.append({'label': FORMA_LABEL.get(forma, forma.title()), 'valor': round(valor, 2),
                             'pct': round(valor / base_taxas * 100), 'cor': FORMA_COR.get(forma, PALETA[i % len(PALETA)])})
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

    # ── Top 5 categorias (modelo) com margem estimada ──
    top_categorias = []
    try:
        cur.execute("""SELECT COALESCE(NULLIF(vi.modelo,''),'Sem categoria') categoria,
                       COALESCE(SUM(vi.valor_total),0) receita,
                       COALESCE(SUM(vi.quantidade),0) pecas,
                       COALESCE(SUM(COALESCE(e.custo_unitario,0) * COALESCE(vi.quantidade,0)),0) custo
                       FROM venda_itens vi
                       JOIN vendas v ON v.id=vi.venda_id
                       LEFT JOIN estoque e ON e.id=vi.produto_id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s
                       GROUP BY 1 ORDER BY receita DESC LIMIT 5""", (di, df))
        top_categorias = [{'categoria': r['categoria'], 'receita': round(float(r['receita'] or 0), 2),
                           'pecas': int(r['pecas'] or 0), 'custo': round(float(r['custo'] or 0), 2)} for r in cur.fetchall()]
    except Exception:
        rollback()
    cat_total = round(sum(c['receita'] for c in top_categorias), 2)
    for c in top_categorias:
        c['pct_fat'] = round(c['receita'] / fat_liquido * 100) if fat_liquido else 0
        c['margem'] = round(((c['receita'] - c.get('custo', 0)) / c['receita']) * 100) if c['receita'] else 0
        c['markup'] = round(((c['receita'] - c.get('custo', 0)) / c['custo']) * 100) if c.get('custo') else 0
    cat_total_pct = round(cat_total / fat_liquido * 100) if fat_liquido else 0

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
        a['pct'] = round(a['valor'] / base_ag * 100)
    estoque_parado_60_pct = round(estoque_parado_60 / base_ag * 100)

    # ── Ranking de vendedoras (líquido) ──
    # "Qtd de clientes" = clientes distintos atendidos no período.
    # "Qtd de clientes cadastrados" = clientes que a funcionária CADASTROU na aba
    #   Clientes dentro do período (clientes.usuario_id), independente de venda.
    vendedoras = []
    try:
        cur.execute("""SELECT v.id, v.vendedora_nome, v.usuario_id, v.valor_total, v.forma_pagamento, v.parcelas, v.criado_em, v.cliente_id,
                       COALESCE(SUM(vi.quantidade),0) pecas, MAX(u.foto) AS foto
                       FROM vendas v
                       LEFT JOIN venda_itens vi ON vi.venda_id=v.id
                       LEFT JOIN usuarios u ON u.id=v.usuario_id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s
                       GROUP BY v.id, v.vendedora_nome, v.usuario_id, v.valor_total, v.forma_pagamento, v.parcelas, v.criado_em, v.cliente_id""", (di, df))
        tmp = {}; cache = {}
        for r in cur.fetchall():
            nome = r['vendedora_nome'] or '—'
            dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
            liq, _d, _p = _liquido_com_taxa(float(r['valor_total'] or 0), r['forma_pagamento'] or 'outros', dt, cache, r.get('parcelas'))
            o = tmp.setdefault(nome, {'nome': nome, 'uid': None, 'liquido': 0.0, 'vendas': 0, 'pecas': 0, 'cli': set(), 'foto': None})
            if r['usuario_id'] and not o['uid']:
                o['uid'] = r['usuario_id']
            if r.get('foto') and not o.get('foto'):
                foto = r['foto']
                # fotos de usuário são salvas como data URI; manter fallback para iniciais no template
                o['foto'] = foto if isinstance(foto, str) and foto.startswith('data:image/') else None
            o['liquido'] += liq; o['vendas'] += 1; o['pecas'] += int(r['pecas'] or 0)
            if r['cliente_id']:
                o['cli'].add(r['cliente_id'])
        # Quantos clientes cada usuário CADASTROU no período (independe de venda)
        cur.execute("""SELECT usuario_id, COUNT(*) c FROM clientes
                       WHERE DATE(criado_em) BETWEEN %s AND %s AND usuario_id IS NOT NULL
                       GROUP BY usuario_id""", (di, df))
        cad_por_uid = {row['usuario_id']: int(row['c'] or 0) for row in cur.fetchall()}
        vendedoras = sorted(tmp.values(), key=lambda x: x['liquido'], reverse=True)[:5]
        for v in vendedoras:
            v['clientes'] = len(v['cli'])
            v['clientes_cad'] = cad_por_uid.get(v['uid'], 0)
            v['ticket'] = round(v['liquido'] / v['vendas'], 2) if v['vendas'] else 0
            v['ini'] = ''.join([p[0] for p in v['nome'].split()[:2]]).upper() or '—'
            v['liquido'] = round(v['liquido'], 2)
    except Exception:
        rollback()
    vend_total = round(sum(v['liquido'] for v in vendedoras), 2)

    # ── Top 5 clientes (líquido) ──
    top_clientes = []
    try:
        cur.execute("""SELECT v.cliente_nome nome, v.valor_total, v.forma_pagamento, v.parcelas, v.criado_em, v.id,
                       COALESCE(SUM(vi.quantidade),0) pecas
                       FROM vendas v LEFT JOIN venda_itens vi ON vi.venda_id=v.id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s AND COALESCE(v.cliente_nome,'')<>''
                       GROUP BY v.id, v.cliente_nome, v.valor_total, v.forma_pagamento, v.parcelas, v.criado_em""", (di, df))
        tmp = {}; cache = {}
        for r in cur.fetchall():
            nome = r['nome'] or 'Cliente'
            dt = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
            liq, _d, _p = _liquido_com_taxa(float(r['valor_total'] or 0), r['forma_pagamento'] or 'outros', dt, cache, r.get('parcelas'))
            o = tmp.setdefault(nome, {'nome': nome, 'liquido': 0.0, 'compras': 0, 'pecas': 0, 'ultima': dt})
            o['liquido'] += liq; o['compras'] += 1; o['pecas'] += int(r['pecas'] or 0); o['ultima'] = max(o['ultima'], dt)
        top_clientes = sorted(tmp.values(), key=lambda x: x['liquido'], reverse=True)[:5]
        for c in top_clientes:
            c['ticket'] = round(c['liquido'] / c['compras'], 2) if c['compras'] else 0
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
        kpi=kpi, trend=trend, gran_label=gran_label, dense=dense,
        eixo_fat_ticks=eixo_fat_ticks, eixo_desp_ticks=eixo_desp_ticks, eixo_lucro_ticks=eixo_lucro_ticks,
        fix_poly=fix_poly, avul_poly=avul_poly, lucro_poly=lucro_poly, lucro_zero_yp=lucro_zero_yp,
        taxas_total=_brl(taxas_total), taxa_pct_fat=f"{round(taxa_pct)}% do faturamento bruto",
        taxas_formas=taxas_formas, taxas_conic=taxas_conic, donut_labels=donut_labels,
        top_categorias=top_categorias, cat_total=cat_total, cat_total_pct=cat_total_pct,
        aging=aging, estoque_parado_60=estoque_parado_60, estoque_parado_60_pct=estoque_parado_60_pct,
        vendedoras=vendedoras, vend_total=vend_total, top_clientes=top_clientes, cli_total=cli_total,
        insights=insights, insights_resumo=insights_resumo, todos_subindo=bool(todos_subindo),
        brl=_brl, kbrl=_kbrl)
    return render_template('dashboard.html', **ctx)


def register(app):
    app.add_url_rule('/dashboard', 'dashboard_view', dashboard_view)
