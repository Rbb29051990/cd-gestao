"""Rota da Visão Geral: faturamento por forma (caixa real), estoque, crediários,
condicionais, despesas do período e a ponte despesas → caixa real (saldo
acumulado e saldo projetado após as pendências do período)."""
from flask import render_template, request
from datetime import date, timedelta
import calendar
from db import get_db, close_db
from config import agora_app, hoje_app, fim_mes_app
from auth import login_required, get_ctx
from utils import get_taxa_vigente, calcular_liquido, data_extenso_br


def _saldo_acumulado(cur, formas_com_taxa, data_limite, operador='<='):
    """v145: soma TODAS as entradas líquidas (com taxa de cartão descontada) menos
    todas as saídas do caixa até uma data — usado pra montar a ponte 'Em caixa
    (início) + recebido − pago = Em caixa (fim)'. `operador` é '<=' (inclui a data)
    ou '<' (até o dia anterior), sempre um literal fixo do código — nunca vem do
    usuário, então não há risco de injeção ao montar a query com ele."""
    cmp = '<=' if operador == '<=' else '<'
    cur.execute(f"""SELECT forma_pagamento, valor, criado_em, parcelas, tipo FROM caixa
                   WHERE DATE(criado_em) {cmp} %s""", (data_limite,))
    taxa_cache = {}
    entradas_liq = 0.0
    saidas = 0.0
    for r in cur.fetchall():
        if r['tipo'] == 'saida':
            saidas += float(r['valor'] or 0)
            continue
        if r['tipo'] != 'entrada':
            continue
        f = r['forma_pagamento'] or ''
        bruto = float(r['valor'] or 0)
        if f in formas_com_taxa:
            d = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje_app()
            chave = d.isoformat()
            if chave not in taxa_cache:
                taxa_cache[chave] = get_taxa_vigente(d)
            liq, _d, _p = calcular_liquido(bruto, f, taxa_cache[chave], r.get('parcelas'))
        else:
            liq = bruto
        entradas_liq += liq
    return round(entradas_liq - saidas, 2)


@login_required
def visao_geral():
    conn = get_db(); cur = conn.cursor()
    hoje = agora_app()
    # Período (mesmo padrão da aba Caixa)
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim    = request.args.get('data_fim',    fim_mes_app())
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = fim_mes_app()
    # Faturamento por forma = dinheiro REAL recebido (caixa entradas).
    # Crediário não aparece como forma própria: a entrada e as parcelas já
    # entram no caixa com a forma real (pix/dinheiro/cartão), então são contabilizadas aqui.
    formas = ['dinheiro', 'pix', 'debito', 'credito_vista', 'credito_parcelado', 'link']
    formas_com_taxa = ['credito_vista', 'credito_parcelado', 'debito', 'link']
    fat     = {f: 0.0 for f in formas}   # bruto por forma
    fat_liq = {f: 0.0 for f in formas}   # líquido por forma (após taxas de cartão)
    # v143: fat_total_geral/fat_total_liq_geral somam TODA entrada do caixa no período,
    # inclusive as que não têm uma forma de pagamento "de venda" conhecida (ex.: Ajuste
    # de Caixa, forma='transferencia') — antes essas linhas eram puladas (`if f not in
    # fat: continue`) e ficavam de fora até do "Total em caixa", te dando um saldo menor
    # que o real da aba Caixa. fat/fat_liq/fat_total continuam só com as formas de venda
    # conhecidas — servem pros quadrantes de faturamento por forma e % de taxa, que são
    # sobre a VENDA, não sobre ajustes manuais.
    fat_total_geral = 0.0
    fat_total_liq_geral = 0.0
    try:
        cur.execute("""SELECT forma_pagamento, valor, criado_em, parcelas FROM caixa
                       WHERE tipo='entrada' AND DATE(criado_em) BETWEEN %s AND %s""", (data_inicio, data_fim))
        for r in cur.fetchall():
            f = r['forma_pagamento'] or ''
            bruto = float(r['valor'] or 0)
            if f in formas_com_taxa:
                taxa_data = get_taxa_vigente(r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje_app())
                liq, _d, _p = calcular_liquido(bruto, f, taxa_data, r.get('parcelas'))
            else:
                liq = bruto
            fat_total_geral += bruto
            fat_total_liq_geral += liq
            if f in fat:
                fat[f] += bruto
                fat_liq[f] += liq
    except Exception:
        pass
    fat     = {k: round(v, 2) for k, v in fat.items()}
    fat_liq = {k: round(v, 2) for k, v in fat_liq.items()}
    fat_total     = round(sum(fat.values()), 2)
    fat_total_liq = round(sum(fat_liq.values()), 2)
    fat_total_geral     = round(fat_total_geral, 2)
    fat_total_liq_geral = round(fat_total_liq_geral, 2)
    # Agrupamentos do faturamento BRUTO para os quadrantes
    fat_dinheiro_pix = round(fat['dinheiro'] + fat['pix'], 2)            # 1º quadrante
    fat_cartao       = round(fat_total - fat_dinheiro_pix, 2)           # 2º (crédito/débito/link)
    # % do líquido sobre o bruto (quanto sobra após as taxas de cartão)
    pct_liquido = round(fat_total_liq / fat_total * 100, 1) if fat_total > 0 else 0.0
    total_taxas = round(fat_total - fat_total_liq, 2)   # total de taxas descontadas
    pct_taxa    = round(total_taxas / fat_total * 100, 1) if fat_total > 0 else 0.0  # % de taxa sobre o bruto
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
    # Estoque parado (mesmo critério do dashboard: dias desde a última venda, ou
    # desde a entrada se nunca vendeu). Usa o VALOR de venda, igual ao "Valor em estoque".
    try:
        cur.execute("""SELECT
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))>30 THEN valor_venda*quantidade ELSE 0 END),0) e30,
            COALESCE(SUM(CASE WHEN (CURRENT_DATE-COALESCE(ultima_venda,DATE(criado_em)))>60 THEN valor_venda*quantidade ELSE 0 END),0) e60
            FROM estoque WHERE ativo=TRUE AND quantidade>0""")
        re = cur.fetchone()
        estoque_30 = round(float(re['e30']), 2)
        estoque_60 = round(float(re['e60']), 2)
    except: estoque_30 = estoque_60 = 0.0
    # Crediários em aberto (global)
    try:
        cur.execute("SELECT COALESCE(SUM(saldo_devedor),0) as v FROM crediarios WHERE status='aberto'")
        val_crediarios = round(float(cur.fetchone()['v']), 2)
    except: val_crediarios = 0.0
    # Vales em aberto (passivo: crédito que a loja deve aos clientes)
    try:
        cur.execute("SELECT COALESCE(SUM(saldo),0) v FROM vales WHERE status='aberto'")
        val_vales = round(float(cur.fetchone()['v']), 2)
    except Exception:
        val_vales = 0.0
    # Condicional / transferência em aberto (global)
    try:
        cur.execute("SELECT COALESCE(SUM(valor_total),0) as v, COUNT(*) as n FROM condicionais WHERE status='aberta'")
        rc = cur.fetchone()
        val_condicional = round(float(rc['v']), 2); n_condicional = int(rc['n'])
    except: val_condicional = 0.0; n_condicional = 0
    # Despesas do período pelo VENCIMENTO das parcelas (valores que SERÃO pagos
    # dentro do período selecionado), separadas em mensais e avulsas — mesmo
    # critério da aba Despesas (d.tipo = 'mensal' → mensal; 'fixa'/'fixo' → sinônimo
    # legado; o resto → avulsa).
    despesas_fixas = despesas_avulsas = 0.0
    try:
        cur.execute("""SELECT LOWER(COALESCE(d.tipo,'')) as tp, COALESCE(SUM(p.valor),0) as t
                       FROM despesa_parcelas p
                       JOIN despesas d ON d.id=p.despesa_id
                       WHERE DATE(p.data_vencimento) BETWEEN %s AND %s
                       GROUP BY LOWER(COALESCE(d.tipo,''))""", (data_inicio, data_fim))
        for r in cur.fetchall():
            if (r['tp'] or '') in ('mensal', 'fixa', 'fixo'): despesas_fixas += float(r['t'])
            else: despesas_avulsas += float(r['t'])
    except Exception:
        pass
    despesas_fixas   = round(despesas_fixas, 2)
    despesas_avulsas = round(despesas_avulsas, 2)
    val_despesas     = round(despesas_fixas + despesas_avulsas, 2)

    # Em caixa AGORA (acumulado até o fim do período) — só como referência na
    # seção "Diversos".
    try:
        saldo_caixa = _saldo_acumulado(cur, formas_com_taxa, data_fim, operador='<=')
    except Exception:
        saldo_caixa = 0.0
    try:
        cur.execute("""SELECT COALESCE(SUM(p.valor),0) v FROM despesa_parcelas p
                       WHERE p.pago=FALSE AND DATE(p.data_vencimento) BETWEEN %s AND %s""",
                    (data_inicio, data_fim))
        despesas_pendentes_periodo = round(float(cur.fetchone()['v']), 2)
    except Exception:
        despesas_pendentes_periodo = 0.0
    despesas_pagas_periodo = round(val_despesas - despesas_pendentes_periodo, 2)

    # v145: "Controle de caixa" (ponte Despesas → Caixa real) andava junto com o
    # filtro De/Até do resto da tela — então escolher "Hoje" ou "7 dias" fazia o
    # "Em caixa (início)" mostrar o saldo de ONTEM, não o saldo real acumulado
    # até o fim do MÊS ANTERIOR. Agora essa ponte é sempre MENSAL, ignorando o
    # filtro De/Até: deriva o mês do data_inicio (o mesmo que os atalhos "Mês"
    # já usam) e sempre olha do dia 1 ao último dia DESSE mês — só troca de mês
    # se o próprio data_inicio cair em outro mês.
    dia_inicio_dt = date.fromisoformat(data_inicio)
    mes_ini_dt = dia_inicio_dt.replace(day=1)
    ultimo_dia_mes = calendar.monthrange(mes_ini_dt.year, mes_ini_dt.month)[1]
    mes_fim_dt = mes_ini_dt.replace(day=ultimo_dia_mes)
    try:
        saldo_caixa_mes_anterior = _saldo_acumulado(cur, formas_com_taxa, mes_ini_dt, operador='<')
    except Exception:
        saldo_caixa_mes_anterior = 0.0
    try:
        cur.execute("""SELECT forma_pagamento, valor, criado_em, parcelas FROM caixa
                       WHERE tipo='entrada' AND DATE(criado_em) BETWEEN %s AND %s""",
                    (mes_ini_dt.isoformat(), mes_fim_dt.isoformat()))
        fat_liq_mes = 0.0
        taxa_cache_mes = {}
        for r in cur.fetchall():
            f = r['forma_pagamento'] or ''
            if f not in fat:   # só formas de venda conhecidas, igual "Faturamento líquido" (card 8)
                continue
            bruto = float(r['valor'] or 0)
            if f in formas_com_taxa:
                d = r['criado_em'].date() if hasattr(r['criado_em'], 'date') else hoje_app()
                chave = d.isoformat()
                if chave not in taxa_cache_mes:
                    taxa_cache_mes[chave] = get_taxa_vigente(d)
                liq, _d, _p = calcular_liquido(bruto, f, taxa_cache_mes[chave], r.get('parcelas'))
            else:
                liq = bruto
            fat_liq_mes += liq
        fat_liq_mes = round(fat_liq_mes, 2)
    except Exception:
        fat_liq_mes = 0.0
    try:
        cur.execute("""SELECT COALESCE(SUM(p.valor),0) v FROM despesa_parcelas p
                       WHERE DATE(p.data_vencimento) BETWEEN %s AND %s""",
                    (mes_ini_dt.isoformat(), mes_fim_dt.isoformat()))
        despesas_mes = round(float(cur.fetchone()['v']), 2)
    except Exception:
        despesas_mes = 0.0
    saldo_projetado_mes = round(saldo_caixa_mes_anterior + fat_liq_mes - despesas_mes, 2)
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
               fat_dinheiro_pix=fat_dinheiro_pix, fat_cartao=fat_cartao, pct_liquido=pct_liquido,
               pct_taxa=pct_taxa, total_taxas=total_taxas,
               saldo_caixa=saldo_caixa,
               despesas_pendentes_periodo=despesas_pendentes_periodo,
               despesas_pagas_periodo=despesas_pagas_periodo,
               saldo_caixa_mes_anterior=saldo_caixa_mes_anterior, fat_liq_mes=fat_liq_mes,
               despesas_mes=despesas_mes, saldo_projetado_mes=saldo_projetado_mes,
               mes_anterior_fim_br=(mes_ini_dt - timedelta(days=1)).strftime('%d/%m/%Y'),
               data_fim_br=date.fromisoformat(data_fim).strftime('%d/%m/%Y'),
               estoque_30=estoque_30, estoque_60=estoque_60,
               custo_estoque=custo_estoque, val_estoque=val_estoque,
               lucro_potencial=lucro_potencial, val_crediarios=val_crediarios,
               val_condicional=val_condicional, n_condicional=n_condicional, val_vales=val_vales,
               val_despesas=val_despesas, despesas_fixas=despesas_fixas,
               despesas_avulsas=despesas_avulsas,
               movs=movs, estoque_baixo=estoque_baixo,
               data_inicio=data_inicio, data_fim=data_fim,
               hoje=data_extenso_br(hoje))
    return render_template('visao_geral.html', **ctx)


def register(app):
    app.add_url_rule('/visao-geral', 'visao_geral', visao_geral)
