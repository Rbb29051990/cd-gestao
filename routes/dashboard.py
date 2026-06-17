"""Rota de Dashboards estratégicos (v122).

Reúne 11 visões gerenciais + cartões de insight automáticos, com filtro de
período pré-fixado no mês corrente (1º → último dia), igual às demais abas:

  1. Resultado do período (receita bruta → taxas → CMV → despesas → lucro líquido)
  2. Tendência dos últimos 6 meses (faturamento × lucro)
  3. Fluxo de caixa acumulado
  4. Top produtos por receita e margem (curva ABC)
  5. Mix por categoria/modelo
  6. Vendas por tamanho
  7. Estoque parado (aging do capital empatado)
  8. Inadimplência do crediário por faixa
  9. Conversão de condicional
 10. Desempenho por vendedora (ticket médio e peças/venda)
 11. Desconto concedido × margem
"""
from datetime import date
from flask import render_template, request
from db import get_db, close_db
from config import hoje_app, inicio_mes_app, fim_mes_app
from auth import login_required, get_ctx
from utils import get_taxa_vigente, calcular_liquido

MESES_PT = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
FORMAS_COM_TAXA = ('credito_vista', 'credito_parcelado', 'debito', 'link')
PALETA = ['#1565c0', '#2e7d32', '#6a1b9a', '#e65100', '#c0396b', '#00838f', '#f9a825', '#5e35b1']


def _add_months(y, m, delta):
    idx = (y * 12 + (m - 1)) + delta
    return idx // 12, idx % 12 + 1


def _brl(v):
    return ("R$ " + f"{float(v or 0):,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


@login_required
def dashboard_view():
    conn = get_db(); cur = conn.cursor()
    hoje = hoje_app()
    data_inicio = request.args.get('data_inicio', inicio_mes_app())
    data_fim = request.args.get('data_fim', fim_mes_app())
    try: date.fromisoformat(data_inicio)
    except Exception: data_inicio = inicio_mes_app()
    try: date.fromisoformat(data_fim)
    except Exception: data_fim = fim_mes_app()

    def rollback():
        try: conn.rollback()
        except Exception: pass

    # ── 1. Resultado do período (PIZZA): entradas líquidas × despesas ──
    # "Entradas líquidas" = entradas do caixa menos a taxa do cartão (mesma base
    # do saldo_bruto da aba Caixa). A origem é detalhada por forma de pagamento.
    FORMA_LABEL = {'dinheiro': 'Dinheiro', 'pix': 'PIX', 'debito': 'Débito',
                   'credito_vista': 'Crédito à vista', 'credito_parcelado': 'Crédito parcelado',
                   'link': 'Link', 'transferencia': 'Transferência', 'crediario': 'Crediário',
                   'outros': 'Outros'}
    FORMA_COR = {'dinheiro': '#2e7d32', 'pix': '#00838f', 'debito': '#1565c0',
                 'credito_vista': '#5e35b1', 'credito_parcelado': '#6a1b9a',
                 'link': '#f9a825', 'transferencia': '#0277bd', 'crediario': '#c0396b',
                 'outros': '#90a4ae'}
    entradas_liquidas = 0.0
    por_forma = {}
    try:
        cur.execute("""SELECT forma_pagamento, valor, criado_em FROM caixa
                       WHERE tipo='entrada' AND DATE(criado_em) BETWEEN %s AND %s""", (data_inicio, data_fim))
        taxa_cache = {}
        for r in cur.fetchall():
            bruto = float(r['valor'] or 0)
            f = r['forma_pagamento'] or 'outros'
            if f in FORMAS_COM_TAXA:
                d = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje
                key = d.isoformat()
                if key not in taxa_cache:
                    taxa_cache[key] = get_taxa_vigente(d)
                liq, _desc, _pct = calcular_liquido(bruto, f, taxa_cache[key])
            else:
                liq = bruto
            entradas_liquidas += liq
            por_forma[f] = por_forma.get(f, 0.0) + liq
    except Exception:
        rollback()
    entradas_liquidas = round(entradas_liquidas, 2)
    entradas_origem = [{'label': FORMA_LABEL.get(f, f.title()), 'valor': round(v, 2),
                        'cor': FORMA_COR.get(f, '#90a4ae')}
                       for f, v in sorted(por_forma.items(), key=lambda kv: kv[1], reverse=True)
                       if round(v, 2) != 0]

    # Despesas do período por vencimento (fixa + avulsa) — mesmo critério das demais abas
    despesas_fixas = despesas_avulsas = 0.0
    try:
        cur.execute("""SELECT LOWER(COALESCE(d.tipo,'')) AS tp, COALESCE(SUM(p.valor),0) AS t
                       FROM despesa_parcelas p JOIN despesas d ON d.id=p.despesa_id
                       WHERE DATE(p.data_vencimento) BETWEEN %s AND %s
                       GROUP BY LOWER(COALESCE(d.tipo,''))""", (data_inicio, data_fim))
        for r in cur.fetchall():
            if (r['tp'] or '') in ('fixa', 'fixo'): despesas_fixas += float(r['t'])
            else: despesas_avulsas += float(r['t'])
    except Exception:
        rollback()
    despesas_fixas = round(despesas_fixas, 2)
    despesas_avulsas = round(despesas_avulsas, 2)
    despesas_total = round(despesas_fixas + despesas_avulsas, 2)

    lucro_liquido = round(entradas_liquidas - despesas_total, 2)
    margem_pct = round(lucro_liquido / entradas_liquidas * 100, 1) if entradas_liquidas else 0

    # Pizza com 3 fatias: entradas líquidas, despesas fixas, despesas avulsas
    pie_segments = [
        {'label': 'Entradas líquidas', 'valor': entradas_liquidas, 'cor': '#2e7d32'},
        {'label': 'Despesas fixas', 'valor': despesas_fixas, 'cor': '#e65100'},
        {'label': 'Despesas avulsas', 'valor': despesas_avulsas, 'cor': '#c62828'},
    ]
    pie_base = sum(s['valor'] for s in pie_segments) or 1
    ang = 0.0; stops = []
    for s in pie_segments:
        s['pct'] = round(s['valor'] / pie_base * 100, 1)
        ini = round(ang, 2); ang += s['valor'] / pie_base * 360; fim = round(ang, 2)
        stops.append(f"{s['cor']} {ini}deg {fim}deg")
    pie_conic = ('conic-gradient(' + ', '.join(stops) + ')') if pie_base > 1 else 'conic-gradient(#eee 0deg 360deg)'

    resultado = {
        'entradas_liquidas': entradas_liquidas,
        'despesas_fixas': despesas_fixas, 'despesas_avulsas': despesas_avulsas,
        'despesas': despesas_total, 'lucro_liquido': lucro_liquido, 'margem_pct': margem_pct,
    }

    # ── 2. Tendência dos últimos 6 meses (faturamento × lucro aprox.) ──
    tendencia = []
    fat_max_trend = 1.0
    try:
        ya, ma = _add_months(hoje.year, hoje.month, -5)
        ini_trend = date(ya, ma, 1)
        cur.execute("""SELECT to_char(date_trunc('month',criado_em),'YYYY-MM') AS ym, COALESCE(SUM(valor_total),0) AS v
                       FROM vendas WHERE criado_em>=%s GROUP BY 1""", (ini_trend,))
        fat_mes = {r['ym']: float(r['v']) for r in cur.fetchall()}
        cur.execute("""SELECT to_char(date_trunc('month',v.criado_em),'YYYY-MM') AS ym,
                       COALESCE(SUM(vi.quantidade*COALESCE(e.custo_unitario,0)),0) AS v
                       FROM venda_itens vi JOIN vendas v ON v.id=vi.venda_id
                       LEFT JOIN estoque e ON e.id=vi.produto_id
                       WHERE v.criado_em>=%s GROUP BY 1""", (ini_trend,))
        cmv_mes = {r['ym']: float(r['v']) for r in cur.fetchall()}
        cur.execute("""SELECT to_char(date_trunc('month',data_vencimento),'YYYY-MM') AS ym, COALESCE(SUM(valor),0) AS v
                       FROM despesa_parcelas WHERE data_vencimento>=%s GROUP BY 1""", (ini_trend,))
        desp_mes = {r['ym']: float(r['v']) for r in cur.fetchall()}
        for back in range(5, -1, -1):
            y, m = _add_months(hoje.year, hoje.month, -back)
            ym = f"{y:04d}-{m:02d}"
            fat = round(fat_mes.get(ym, 0), 2)
            lucro = round(fat - cmv_mes.get(ym, 0) - desp_mes.get(ym, 0), 2)
            tendencia.append({'label': f"{MESES_PT[m-1]}/{str(y)[2:]}", 'fat': fat, 'lucro': lucro})
        fat_max_trend = max([t['fat'] for t in tendencia] + [1])
        for t in tendencia:
            t['fat_h'] = round(t['fat'] / fat_max_trend * 100)
            t['luc_h'] = round(abs(t['lucro']) / fat_max_trend * 100)
            t['luc_neg'] = t['lucro'] < 0
    except Exception:
        rollback()

    # ── 3. Fluxo de caixa acumulado no período ──
    fluxo = {'entradas': 0.0, 'saidas': 0.0, 'saldo': 0.0}
    fluxo_pts = ''; fluxo_zero_y = 35.0
    try:
        cur.execute("""SELECT DATE(criado_em) AS dia,
                       COALESCE(SUM(CASE WHEN tipo='entrada' THEN valor ELSE 0 END),0) AS ent,
                       COALESCE(SUM(CASE WHEN tipo='saida' THEN valor ELSE 0 END),0) AS sai
                       FROM caixa WHERE DATE(criado_em) BETWEEN %s AND %s
                       GROUP BY DATE(criado_em) ORDER BY dia""", (data_inicio, data_fim))
        acum = 0.0; tot_e = tot_s = 0.0; serie = []
        for r in cur.fetchall():
            e = float(r['ent']); s = float(r['sai']); acum += e - s
            tot_e += e; tot_s += s; serie.append(acum)
        fluxo = {'entradas': round(tot_e, 2), 'saidas': round(tot_s, 2), 'saldo': round(tot_e - tot_s, 2)}
        if serie:
            lo = min(serie + [0]); hi = max(serie + [0]); rng = (hi - lo) or 1
            n = len(serie); W = 300.0; H = 70.0
            pts = []
            for i, v in enumerate(serie):
                x = round(i / max(n - 1, 1) * W, 1)
                y = round(H - (v - lo) / rng * H, 1)
                pts.append(f"{x},{y}")
            fluxo_pts = ' '.join(pts)
            fluxo_zero_y = round(H - (0 - lo) / rng * H, 1)
    except Exception:
        rollback()

    # ── 4. Top produtos por receita e margem (curva ABC) ──
    top_produtos = []; rec_max = 1.0
    try:
        cur.execute("""SELECT vi.modelo, vi.descricao, vi.codigo_produto,
                       SUM(vi.quantidade) AS qtd, SUM(vi.valor_total) AS receita,
                       COALESCE(SUM(vi.quantidade*COALESCE(e.custo_unitario,0)),0) AS custo
                       FROM venda_itens vi JOIN vendas v ON v.id=vi.venda_id
                       LEFT JOIN estoque e ON e.id=vi.produto_id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s
                       GROUP BY vi.modelo, vi.descricao, vi.codigo_produto
                       ORDER BY receita DESC LIMIT 10""", (data_inicio, data_fim))
        for r in cur.fetchall():
            receita = float(r['receita'] or 0); custo = float(r['custo'] or 0)
            lucro = round(receita - custo, 2)
            top_produtos.append({
                'nome': (r['descricao'] or r['modelo'] or r['codigo_produto'] or '—'),
                'modelo': r['modelo'] or '', 'qtd': int(r['qtd'] or 0),
                'receita': round(receita, 2), 'lucro': lucro,
                'margem': round(lucro / receita * 100, 1) if receita else 0})
        rec_max = max([p['receita'] for p in top_produtos] + [1])
        cur.execute("""SELECT COALESCE(SUM(vi.valor_total),0) AS t
                       FROM venda_itens vi JOIN vendas v ON v.id=vi.venda_id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s""", (data_inicio, data_fim))
        rec_itens_total = float(cur.fetchone()['t'] or 0) or 1
        cum = 0.0
        for p in top_produtos:
            cum += p['receita']
            p['acum_pct'] = round(cum / rec_itens_total * 100, 1)
            p['classe'] = 'A' if p['acum_pct'] <= 80 else ('B' if p['acum_pct'] <= 95 else 'C')
    except Exception:
        rollback()

    # ── 5. Mix por categoria/modelo (donut) ──
    mix = []; mix_total = 0.0; mix_conic = 'conic-gradient(#eee 0deg 360deg)'
    try:
        cur.execute("""SELECT COALESCE(NULLIF(vi.modelo,''),'Outros') AS modelo,
                       SUM(vi.valor_total) AS receita, SUM(vi.quantidade) AS qtd
                       FROM venda_itens vi JOIN vendas v ON v.id=vi.venda_id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s
                       GROUP BY 1 ORDER BY receita DESC""", (data_inicio, data_fim))
        rows = cur.fetchall()
        mix_total = round(sum(float(r['receita'] or 0) for r in rows), 2)
        base = mix_total or 1
        ang = 0.0; stops = []
        for i, r in enumerate(rows[:8]):
            rec = float(r['receita'] or 0)
            pct = round(rec / base * 100, 1)
            cor = PALETA[i % len(PALETA)]
            ini = round(ang, 2); ang += pct * 3.6; fim = round(ang, 2)
            stops.append(f"{cor} {ini}deg {fim}deg")
            mix.append({'label': r['modelo'], 'valor': round(rec, 2), 'qtd': int(r['qtd'] or 0),
                        'pct': pct, 'cor': cor})
        if stops:
            mix_conic = 'conic-gradient(' + ', '.join(stops) + ')'
    except Exception:
        rollback()

    # ── 6. Vendas por tamanho ──
    tamanhos = []; tam_max = 1
    try:
        cur.execute("""SELECT COALESCE(NULLIF(vi.tamanho,''),'—') AS tam,
                       SUM(vi.quantidade) AS qtd, SUM(vi.valor_total) AS receita
                       FROM venda_itens vi JOIN vendas v ON v.id=vi.venda_id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s
                       GROUP BY 1 ORDER BY qtd DESC LIMIT 12""", (data_inicio, data_fim))
        tamanhos = [{'tam': r['tam'], 'qtd': int(r['qtd'] or 0), 'receita': round(float(r['receita'] or 0), 2)}
                    for r in cur.fetchall()]
        tam_max = max([t['qtd'] for t in tamanhos] + [1])
    except Exception:
        rollback()

    # ── 7. Estoque parado (aging do capital empatado) — ponto no tempo ──
    aging = []; aging_total = 0.0; estoque_parado_90 = 0.0
    try:
        cur.execute("""SELECT
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))<=30 THEN custo_unitario*quantidade ELSE 0 END),0) AS b0,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em))) BETWEEN 31 AND 60 THEN custo_unitario*quantidade ELSE 0 END),0) AS b1,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em))) BETWEEN 61 AND 90 THEN custo_unitario*quantidade ELSE 0 END),0) AS b2,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))>90 THEN custo_unitario*quantidade ELSE 0 END),0) AS b3,
            COALESCE(SUM(custo_unitario*quantidade),0) AS total
            FROM estoque WHERE ativo=TRUE AND quantidade>0""")
        a = cur.fetchone()
        aging = [
            {'faixa': 'Até 30 dias', 'valor': round(float(a['b0']), 2), 'cor': '#2e7d32'},
            {'faixa': '31–60 dias', 'valor': round(float(a['b1']), 2), 'cor': '#f9a825'},
            {'faixa': '61–90 dias', 'valor': round(float(a['b2']), 2), 'cor': '#e65100'},
            {'faixa': '+90 dias', 'valor': round(float(a['b3']), 2), 'cor': '#c62828'},
        ]
        aging_total = round(float(a['total']), 2)
        estoque_parado_90 = round(float(a['b3']), 2)
    except Exception:
        rollback()
    aging_max = max([f['valor'] for f in aging] + [1]) if aging else 1

    # ── 8. Inadimplência do crediário por faixa (parcelas em aberto) ──
    cred_faixas = []; cred_total = cred_atraso = 0.0; cred_atraso_pct = 0; cred_max = 1
    try:
        cur.execute("""SELECT
            COALESCE(SUM(CASE WHEN data_vencimento>=CURRENT_DATE THEN valor ELSE 0 END),0) AS av,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-data_vencimento) BETWEEN 1 AND 30 THEN valor ELSE 0 END),0) AS d1,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-data_vencimento) BETWEEN 31 AND 60 THEN valor ELSE 0 END),0) AS d2,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-data_vencimento)>60 THEN valor ELSE 0 END),0) AS d3
            FROM crediario_parcelas WHERE pago=FALSE""")
        c = cur.fetchone()
        cred_faixas = [
            {'faixa': 'A vencer', 'valor': round(float(c['av']), 2), 'cor': '#2e7d32'},
            {'faixa': '1–30 dias', 'valor': round(float(c['d1']), 2), 'cor': '#f9a825'},
            {'faixa': '31–60 dias', 'valor': round(float(c['d2']), 2), 'cor': '#e65100'},
            {'faixa': '+60 dias', 'valor': round(float(c['d3']), 2), 'cor': '#c62828'},
        ]
        cred_total = round(sum(f['valor'] for f in cred_faixas), 2)
        cred_atraso = round(cred_faixas[1]['valor'] + cred_faixas[2]['valor'] + cred_faixas[3]['valor'], 2)
        cred_atraso_pct = round(cred_atraso / cred_total * 100, 1) if cred_total else 0
        cred_max = max([f['valor'] for f in cred_faixas] + [1])
    except Exception:
        rollback()

    # ── 9. Conversão de condicional (período por criação) ──
    cond = {'aberta': 0, 'venda': 0, 'devolvida': 0, 'valor_venda': 0.0, 'taxa': 0}
    try:
        cur.execute("""SELECT
            COUNT(*) FILTER (WHERE status='aberta') AS aberta,
            COUNT(*) FILTER (WHERE status='finalizada' AND venda_id IS NOT NULL) AS venda,
            COUNT(*) FILTER (WHERE status='devolvida') AS devolvida,
            COALESCE(SUM(valor_total) FILTER (WHERE status='finalizada' AND venda_id IS NOT NULL),0) AS valor_venda
            FROM condicionais WHERE DATE(criado_em) BETWEEN %s AND %s""", (data_inicio, data_fim))
        c = cur.fetchone()
        venda = int(c['venda'] or 0); dev = int(c['devolvida'] or 0)
        fechadas = venda + dev
        cond = {'aberta': int(c['aberta'] or 0), 'venda': venda, 'devolvida': dev,
                'valor_venda': round(float(c['valor_venda'] or 0), 2),
                'taxa': round(venda / fechadas * 100, 1) if fechadas else 0}
    except Exception:
        rollback()

    # ── 10. Desempenho por vendedora (ticket médio e peças/venda) ──
    vendedoras = []; vend_max = 1.0
    try:
        cur.execute("""SELECT v.vendedora_nome AS nome, COUNT(DISTINCT v.id) AS vendas,
                       COALESCE(SUM(v.valor_total),0) AS total, COALESCE(SUM(it.qtd),0) AS pecas
                       FROM vendas v
                       LEFT JOIN (SELECT venda_id, SUM(quantidade) AS qtd FROM venda_itens GROUP BY venda_id) it
                              ON it.venda_id=v.id
                       WHERE DATE(v.criado_em) BETWEEN %s AND %s
                       GROUP BY v.vendedora_nome ORDER BY total DESC LIMIT 8""", (data_inicio, data_fim))
        for r in cur.fetchall():
            vendas_n = int(r['vendas'] or 0); total = float(r['total'] or 0); pecas = int(r['pecas'] or 0)
            vendedoras.append({'nome': r['nome'] or '—', 'vendas': vendas_n, 'total': round(total, 2),
                               'ticket': round(total / vendas_n, 2) if vendas_n else 0,
                               'pecas_venda': round(pecas / vendas_n, 1) if vendas_n else 0})
        vend_max = max([v['total'] for v in vendedoras] + [1])
    except Exception:
        rollback()

    # ── 11. Desconto concedido × margem ──
    desc = {'total': 0.0, 'pct_medio': 0, 'n_vendas': 0, 'n_com_desc': 0, 'pct_vendas': 0}
    try:
        cur.execute("""SELECT COALESCE(SUM(desconto),0) AS total,
                       COALESCE(AVG(NULLIF(pct_desconto,0)),0) AS pct_medio, COUNT(*) AS n,
                       COUNT(CASE WHEN COALESCE(desconto,0)>0 THEN 1 END) AS n_desc
                       FROM vendas WHERE DATE(criado_em) BETWEEN %s AND %s""", (data_inicio, data_fim))
        d = cur.fetchone()
        n = int(d['n'] or 0); nd = int(d['n_desc'] or 0)
        desc = {'total': round(float(d['total'] or 0), 2), 'pct_medio': round(float(d['pct_medio'] or 0), 1),
                'n_vendas': n, 'n_com_desc': nd, 'pct_vendas': round(nd / n * 100, 1) if n else 0}
    except Exception:
        rollback()

    cur.close(); close_db(conn)

    # ── Cartões de insight automáticos ──
    insights = []
    if entradas_liquidas > 0 or despesas_total > 0:
        insights.append({'ic': '💡', 'tom': 'bom' if lucro_liquido >= 0 else 'ruim',
                         'tx': f"Lucro líquido do período: {_brl(lucro_liquido)} (margem {margem_pct}%)."})
    if len(tendencia) >= 2 and tendencia[-2]['fat'] > 0:
        var = round((tendencia[-1]['fat'] - tendencia[-2]['fat']) / tendencia[-2]['fat'] * 100, 1)
        insights.append({'ic': '📈' if var >= 0 else '📉', 'tom': 'bom' if var >= 0 else 'alerta',
                         'tx': f"Faturamento {'subiu' if var >= 0 else 'caiu'} {abs(var)}% vs o mês anterior."})
    if top_produtos:
        p = top_produtos[0]
        insights.append({'ic': '🏆', 'tom': 'neutro',
                         'tx': f"Quem mais fatura: {p['nome']} ({_brl(p['receita'])}, margem {p['margem']}%)."})
    if estoque_parado_90 > 0:
        insights.append({'ic': '📦', 'tom': 'alerta',
                         'tx': f"{_brl(estoque_parado_90)} em estoque parado há mais de 90 dias."})
    if cred_total > 0:
        insights.append({'ic': '⚠️', 'tom': 'ruim' if cred_atraso_pct >= 20 else ('alerta' if cred_atraso_pct > 0 else 'bom'),
                         'tx': f"{cred_atraso_pct}% do crediário em atraso ({_brl(cred_atraso)} a recuperar)."})
    if cond['venda'] + cond['devolvida'] > 0:
        insights.append({'ic': '🛍️', 'tom': 'bom' if cond['taxa'] >= 50 else 'neutro',
                         'tx': f"Conversão de condicional em {cond['taxa']}% ({cond['venda']} viraram venda)."})
    if vendedoras:
        v = vendedoras[0]
        insights.append({'ic': '🥇', 'tom': 'neutro',
                         'tx': f"Destaque em vendas: {v['nome']} ({_brl(v['total'])}, ticket {_brl(v['ticket'])})."})

    periodo_label = (f"{data_inicio.split('-')[2]}/{data_inicio.split('-')[1]}"
                     f" até {data_fim.split('-')[2]}/{data_fim.split('-')[1]}")

    ctx = get_ctx()
    ctx.update(
        data_inicio=data_inicio, data_fim=data_fim, periodo_label=periodo_label,
        hoje=hoje.strftime('%A, %d de %B de %Y').capitalize(),
        mes_atual=hoje.strftime('%B / %Y').capitalize(),
        resultado=resultado, entradas_origem=entradas_origem,
        pie_segments=pie_segments, pie_conic=pie_conic,
        tendencia=tendencia, fat_max_trend=fat_max_trend,
        fluxo=fluxo, fluxo_pts=fluxo_pts, fluxo_zero_y=fluxo_zero_y,
        top_produtos=top_produtos, rec_max=rec_max,
        mix=mix, mix_total=mix_total, mix_conic=mix_conic,
        tamanhos=tamanhos, tam_max=tam_max,
        aging=aging, aging_total=aging_total, aging_max=aging_max, estoque_parado_90=estoque_parado_90,
        cred_faixas=cred_faixas, cred_total=cred_total, cred_atraso=cred_atraso,
        cred_atraso_pct=cred_atraso_pct, cred_max=cred_max,
        cond=cond, vendedoras=vendedoras, vend_max=vend_max, desc=desc,
        insights=insights)
    return render_template('dashboard.html', **ctx)


def register(app):
    app.add_url_rule('/dashboard', 'dashboard_view', dashboard_view)
