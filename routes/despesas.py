"""Rotas de Despesas: listagem com período e gráficos (fixa×avulsa, categorias,
formas), novo lançamento passo a passo (parcelado ou conta a pagar única),
pagamento de parcela (lança saída no caixa) e exclusão (só N1)."""
from datetime import datetime, date, timedelta
import calendar
import secrets
from flask import render_template, request, redirect, url_for, session, flash
from db import get_db, close_db
from config import hoje_app
from auth import login_required, get_ctx, pode_excluir, is_admin
from utils import parse_brl


def _add_months_clamped(base_date, months):
    """Soma meses mantendo o dia original quando possível e ajustando para o último dia do mês quando necessário."""
    idx = (base_date.year * 12 + (base_date.month - 1)) + months
    y = idx // 12
    m = idx % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(base_date.day, last))


def _parse_iso_date(value, default=None):
    try:
        return date.fromisoformat(value)
    except Exception:
        return default or hoje_app()


@login_required
def despesas():
    conn = get_db(); cur = conn.cursor()
    hoje = hoje_app()
    data_inicio = request.args.get('data_inicio', hoje.strftime('%Y-%m-01'))
    data_fim    = request.args.get('data_fim',    hoje.strftime('%Y-%m-%d'))
    try: date.fromisoformat(data_inicio)
    except: data_inicio = hoje.strftime('%Y-%m-01')
    try: date.fromisoformat(data_fim)
    except: data_fim = hoje.strftime('%Y-%m-%d')
    # v115: o período da aba Despesas é sempre baseado no VENCIMENTO DAS PARCELAS.
    # Isso evita somar o valor total de uma despesa parcelada/recorrente dentro de um único mês.
    # Ex.: empréstimo de 18x R$ 750 aparece no mês como R$ 750, e não como R$ 13.500.
    cur.execute("""SELECT d.*,
                          COALESCE(SUM(p.valor),0) AS valor_periodo,
                          MIN(p.data_vencimento) AS vencimento_periodo,
                          COUNT(p.id) AS parcelas_periodo
                   FROM despesas d
                   JOIN despesa_parcelas p ON p.despesa_id=d.id
                   WHERE DATE(p.data_vencimento) BETWEEN %s AND %s
                   GROUP BY d.id
                   ORDER BY MIN(p.data_vencimento) DESC, d.id DESC""", (data_inicio, data_fim))
    lista = [dict(d) for d in cur.fetchall()]
    # Carregar parcelas de cada despesa para status; o valor exibido/contabilizado é somente o valor vencido no período.
    for d in lista:
        cur.execute("SELECT * FROM despesa_parcelas WHERE despesa_id=%s ORDER BY numero", (d['id'],))
        d['parcelas'] = [dict(p) for p in cur.fetchall()]
        d['parc_pagas'] = sum(1 for p in d['parcelas'] if p['pago'])
        d['valor_total_original'] = d.get('valor')
        d['valor'] = float(d.get('valor_periodo') or 0)
        if not d.get('data_vencimento') and d.get('vencimento_periodo'):
            d['data_vencimento'] = d.get('vencimento_periodo')
    cur.execute("""SELECT COALESCE(SUM(valor),0) as t
                   FROM despesa_parcelas
                   WHERE DATE(data_vencimento) BETWEEN %s AND %s""", (data_inicio, data_fim))
    total = float(cur.fetchone()['t'])
    # Fechamento mensal: parcelas/despesas do período por vencimento.
    # Verde = pagas; vermelho = em aberto/a pagar.
    cur.execute("""SELECT
                    COALESCE(SUM(CASE WHEN pago=TRUE THEN valor ELSE 0 END),0) AS pagas,
                    COALESCE(SUM(CASE WHEN pago=FALSE THEN valor ELSE 0 END),0) AS abertas
                   FROM despesa_parcelas
                   WHERE DATE(data_vencimento) BETWEEN %s AND %s""", (data_inicio, data_fim))
    fm = cur.fetchone()
    despesas_pagas_mes = round(float(fm['pagas'] or 0), 2)
    despesas_abertas_mes = round(float(fm['abertas'] or 0), 2)
    despesas_total_mes = round(despesas_pagas_mes + despesas_abertas_mes, 2)
    despesas_pct_pago = round((despesas_pagas_mes / despesas_total_mes * 100), 1) if despesas_total_mes else 0
    cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)), 0) as m FROM despesas WHERE codigo ~ '^D[0-9]+$'")
    n = cur.fetchone()['m']
    # Categorias para o cadastro (ordenadas)
    cur.execute("SELECT nome FROM despesa_categorias WHERE ativo=TRUE ORDER BY nome")
    categorias = [r['nome'] for r in cur.fetchall()]
    # Contas a pagar (parcelas pendentes do período filtrado)
    cur.execute("""SELECT p.id as parcela_id, p.numero, p.valor, p.data_vencimento,
                          d.id as despesa_id, d.codigo, d.descricao, d.categoria,
                          d.forma_pagamento, d.local_retirada, d.num_parcelas
                   FROM despesa_parcelas p JOIN despesas d ON d.id=p.despesa_id
                   WHERE p.pago=FALSE
                     AND DATE(p.data_vencimento) BETWEEN %s AND %s
                   ORDER BY p.data_vencimento, d.id, p.numero""", (data_inicio, data_fim))
    a_pagar = [dict(r) for r in cur.fetchall()]
    for p in a_pagar:
        p['atrasada'] = bool(p['data_vencimento'] and p['data_vencimento'] < hoje)
    total_a_pagar = round(sum(float(p['valor'] or 0) for p in a_pagar), 2)
    n_atrasadas = sum(1 for p in a_pagar if p['atrasada'])

    # v116: contas pagas do período ao lado das pendentes.
    # Base: data_pagamento dentro do período filtrado, para o fechamento financeiro real.
    cur.execute("""SELECT p.id as parcela_id, p.numero, p.valor, p.data_vencimento, p.data_pagamento,
                          p.forma_pagamento as forma_pagamento_parcela, p.obs_pagamento,
                          d.id as despesa_id, d.codigo, d.descricao, d.categoria,
                          d.forma_pagamento, d.local_retirada, d.num_parcelas
                   FROM despesa_parcelas p JOIN despesas d ON d.id=p.despesa_id
                   WHERE p.pago=TRUE
                     AND DATE(p.data_pagamento) BETWEEN %s AND %s
                   ORDER BY p.data_pagamento DESC, d.id DESC, p.numero DESC""", (data_inicio, data_fim))
    pagas_periodo = [dict(r) for r in cur.fetchall()]
    total_pagas_periodo = round(sum(float(p['valor'] or 0) for p in pagas_periodo), 2)
    # ── 3 pizzas: Fixa × Avulsa dos 3 meses ANTERIORES ao mês atual (independe do filtro) ──
    MESES_PT = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho',
                'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    def _add_months(y, mth, delta):
        idx = (y * 12 + (mth - 1)) + delta
        return idx // 12, idx % 12 + 1
    tri_meses = []
    for back in (3, 2, 1):
        yy, mm = _add_months(hoje.year, hoje.month, -back)
        ini_m = date(yy, mm, 1)
        ny, nm = _add_months(yy, mm, 1)
        fim_m = date(ny, nm, 1) - timedelta(days=1)
        cur.execute("""SELECT LOWER(COALESCE(d.tipo,'')) as tp, COALESCE(SUM(p.valor),0) as t
                       FROM despesa_parcelas p
                       JOIN despesas d ON d.id=p.despesa_id
                       WHERE DATE(p.data_vencimento) BETWEEN %s AND %s
                       GROUP BY LOWER(COALESCE(d.tipo,''))""", (ini_m, fim_m))
        fx = av = 0.0
        for r in cur.fetchall():
            if (r['tp'] or '') in ('fixa', 'fixo'): fx += float(r['t'])
            else: av += float(r['t'])
        tot_m = round(fx + av, 2)
        tri_meses.append({'label': f"{MESES_PT[mm-1]}/{yy}", 'fixa': round(fx, 2),
                          'avulsa': round(av, 2), 'total': tot_m,
                          'pct_fixa': round(fx / tot_m * 100, 1) if tot_m else 0})
    cur.close(); close_db(conn)
    # ── Agregações para gráficos (fixa vs avulsa + descrições + categorias) ──
    def _norm_tipo(t):
        return 'fixa' if (t or '').strip().lower() in ('fixa', 'fixo') else 'avulsa'
    total_fixa = total_avulsa = 0.0
    qtd_fixa = qtd_avulsa = 0
    cat_fixa, cat_avulsa = {}, {}
    for d in lista:
        v = float(d['valor'] or 0)
        tp = _norm_tipo(d.get('tipo'))
        d['tipo'] = tp  # normaliza para o template
        chave = (d.get('categoria') or d.get('descricao') or '—').strip() or '—'
        if tp == 'fixa':
            total_fixa += v; qtd_fixa += 1
            cat_fixa[chave] = cat_fixa.get(chave, 0.0) + v
        else:
            total_avulsa += v; qtd_avulsa += 1
            cat_avulsa[chave] = cat_avulsa.get(chave, 0.0) + v
    def _ranked(dic):
        itens = sorted(dic.items(), key=lambda kv: kv[1], reverse=True)
        return [{'descricao': k, 'valor': round(v, 2)} for k, v in itens]
    desc_fixa_list = _ranked(cat_fixa)
    desc_avulsa_list = _ranked(cat_avulsa)
    ctx = get_ctx()
    ctx.update(lista=lista, total=total, data_inicio=data_inicio, data_fim=data_fim, next_cod=f"D{n+1}",
               total_fixa=round(total_fixa, 2), total_avulsa=round(total_avulsa, 2),
               qtd_fixa=qtd_fixa, qtd_avulsa=qtd_avulsa,
               desc_fixa=desc_fixa_list, desc_avulsa=desc_avulsa_list, tri_meses=tri_meses,
               categorias=categorias, a_pagar=a_pagar, total_a_pagar=total_a_pagar,
               pagas_periodo=pagas_periodo, total_pagas_periodo=total_pagas_periodo,
               n_a_pagar=len(a_pagar), n_atrasadas=n_atrasadas,
               despesas_pagas_mes=despesas_pagas_mes, despesas_abertas_mes=despesas_abertas_mes,
               despesas_total_mes=despesas_total_mes, despesas_pct_pago=despesas_pct_pago)
    return render_template('despesas.html', **ctx)


@login_required
def nova_despesa():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)), 0) as m FROM despesas WHERE codigo ~ '^D[0-9]+$'")
    n = cur.fetchone()['m']
    valor = parse_brl(request.form.get('valor', '0'))
    descricao = request.form.get('descricao', '').strip()
    categoria = request.form.get('categoria', '').strip()
    # v116: forma/origem/observação são informadas somente no pagamento.
    forma = ''
    tipo = request.form.get('tipo', 'avulsa').strip().lower()
    if tipo not in ('fixa', 'avulsa'): tipo = 'avulsa'
    local_ret = None
    obs_ret = None
    parcelado = request.form.get('parcelado', 'nao').strip().lower() == 'sim'
    # Regra de negócio: despesa parcelada tem início e fim; portanto não é recorrente.
    recorrente = (not parcelado) and (request.form.get('recorrente', 'nao').strip().lower() == 'sim')
    try:
        num_parc = int(request.form.get('num_parcelas', '1') or 1)
    except ValueError:
        num_parc = 1
    if not parcelado or num_parc < 2:
        parcelado = False; num_parc = 1
    num_parc = min(max(num_parc, 1), 24)
    if parcelado:
        recorrente = False
    # Vencimento (despesa sem parcelamento = 1 conta a pagar; recorrente gera 12 contas)
    venc_unico = request.form.get('data_vencimento_unica') or hoje_app().isoformat()
    venc_base = _parse_iso_date(venc_unico, hoje_app())
    # Rótulo da despesa para histórico (categoria + descrição livre)
    rotulo = categoria or descricao or 'Despesa'
    if categoria and descricao:
        rotulo = f"{categoria} — {descricao}"
    try:
        # Persistir categoria nova, se digitada
        if categoria:
            cur.execute("INSERT INTO despesa_categorias (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING", (categoria,))
        # Tanto parcelada quanto não-parcelada entram como conta(s) a pagar (pendente).
        # Recorrente: gera 12 lançamentos independentes, todos em aberto, permitindo ajustar valor/vencimento mês a mês.
        status = 'pendente'
        if recorrente:
            grupo = 'REC-' + hoje_app().strftime('%Y%m%d') + '-' + secrets.token_hex(4).upper()
            for idx in range(12):
                venc = _add_months_clamped(venc_base, idx)
                cod = f"D{n+1+idx}"
                cur.execute("""INSERT INTO despesas
                    (codigo,descricao,categoria,valor,data_despesa,forma_pagamento,tipo,
                     parcelado,num_parcelas,local_retirada,obs_retirada,status,data_vencimento,usuario_id,usuario_nome,
                     recorrente,recorrencia_grupo,recorrencia_seq,recorrencia_total,recorrencia_base)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (cod, descricao or None, categoria or None, valor,
                     request.form.get('data_despesa') or hoje_app().isoformat(),
                     forma or None, tipo, False, 1, local_ret, obs_ret, status, venc.isoformat(),
                     session['uid'], session['nome'], True, grupo, idx + 1, 12, venc_base.isoformat()))
                desp_id_mes = cur.fetchone()['id']
                cur.execute("""INSERT INTO despesa_parcelas (despesa_id,numero,valor,data_vencimento)
                    VALUES (%s,1,%s,%s)""", (desp_id_mes, valor, venc.isoformat()))
            flash('Despesa recorrente registrada! Foram geradas 12 contas a pagar mensais em aberto.', 'ok')
        else:
            data_venc_desp = None if parcelado else venc_unico
            cur.execute("""INSERT INTO despesas
                (codigo,descricao,categoria,valor,data_despesa,forma_pagamento,tipo,
                 parcelado,num_parcelas,local_retirada,obs_retirada,status,data_vencimento,usuario_id,usuario_nome,
                 recorrente,recorrencia_total)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (f"D{n+1}", descricao or None, categoria or None, valor,
                 request.form.get('data_despesa') or hoje_app().isoformat(),
                 forma or None, tipo, parcelado, num_parc, local_ret, obs_ret, status, data_venc_desp,
                 session['uid'], session['nome'], False, 1))
            desp_id = cur.fetchone()['id']
        if (not recorrente) and parcelado:
            # Gera as parcelas; só viram saída no Caixa quando pagas
            soma = 0.0
            for i in range(1, num_parc + 1):
                pv = request.form.get(f'parcela_valor_{i}')
                pd = request.form.get(f'parcela_data_{i}')
                pvf = parse_brl(pv) if pv else round(valor / num_parc, 2)
                if not pd:
                    pd = (hoje_app() + timedelta(days=30 * i)).isoformat()
                soma += pvf
                cur.execute("""INSERT INTO despesa_parcelas (despesa_id,numero,valor,data_vencimento)
                    VALUES (%s,%s,%s,%s)""", (desp_id, i, pvf, pd))
            flash(f'Despesa parcelada em {num_parc}x registrada! As parcelas entram no caixa conforme você as paga.', 'ok')
        elif not recorrente:
            # Sem parcelamento = 1 conta a pagar com vencimento (só entra no caixa quando paga)
            cur.execute("""INSERT INTO despesa_parcelas (despesa_id,numero,valor,data_vencimento)
                VALUES (%s,1,%s,%s)""", (desp_id, valor, venc_unico))
            try: venc_fmt = datetime.fromisoformat(venc_unico).strftime('%d/%m/%Y')
            except Exception: venc_fmt = venc_unico
            flash(f'Despesa registrada como conta a pagar (vence em {venc_fmt}). Marque como paga quando quitar.', 'ok')
        conn.commit()
    except Exception as e: conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('despesas'))


@login_required
def pagar_parcela_despesa(did, pid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM despesas WHERE id=%s", (did,))
        d = cur.fetchone()
        if not d:
            flash('Despesa não encontrada.', 'erro'); return redirect(url_for('despesas'))
        d = dict(d)
        cur.execute("SELECT * FROM despesa_parcelas WHERE id=%s", (pid,))
        p = cur.fetchone()
        if not p:
            flash('Parcela não encontrada.', 'erro'); return redirect(url_for('despesas'))
        p = dict(p)
        if p['pago']:
            flash('Esta parcela já está paga.', 'erro'); return redirect(url_for('despesas'))
        data_pagamento = request.form.get('data_pagamento') or hoje_app().isoformat()
        forma_pagamento = (request.form.get('forma_pagamento') or '').strip()
        obs_pagamento = (request.form.get('obs_pagamento') or '').strip() or None
        if not forma_pagamento:
            flash('Informe a forma de pagamento para quitar a despesa.', 'erro')
            return redirect(url_for('despesas'))
        # valida data ISO; se vier inválida, usa a data atual do Brasil
        try:
            date.fromisoformat(data_pagamento)
        except Exception:
            data_pagamento = hoje_app().isoformat()
        cur.execute("""UPDATE despesa_parcelas
                       SET pago=TRUE,data_pagamento=%s,forma_pagamento=%s,obs_pagamento=%s
                       WHERE id=%s""", (data_pagamento, forma_pagamento, obs_pagamento, pid))
        rotulo = d.get('categoria') or d.get('descricao') or 'Despesa'
        descr_caixa = f"Despesa: {rotulo} (parc. {p['numero']}/{d.get('num_parcelas')})"
        if obs_pagamento:
            descr_caixa += f" — {obs_pagamento}"
        cur.execute("""INSERT INTO caixa
                       (descricao,valor,tipo,forma_pagamento,despesa_id,parcela_id,usuario_id,vendedora_nome,criado_em)
                       VALUES (%s,%s,'saida',%s,%s,%s,%s,%s,%s)""",
            (descr_caixa, float(p['valor']), forma_pagamento, did, pid, session['uid'], session['nome'], data_pagamento))
        # Se todas pagas, fecha a despesa
        cur.execute("SELECT COUNT(*) as t FROM despesa_parcelas WHERE despesa_id=%s AND pago=FALSE", (did,))
        if cur.fetchone()['t'] == 0:
            cur.execute("UPDATE despesas SET status='pago' WHERE id=%s", (did,))
        conn.commit(); flash(f"Parcela {p['numero']} paga e lançada no caixa!", 'ok')
    except Exception as e: conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('despesas'))


@login_required
def editar_despesa(did):
    """Edita uma despesa. Liberado para N1 e N2.
    Categoria/descrição/tipo/forma/origem podem ser alterados sempre.
    Valor e vencimento só quando a despesa ainda não foi paga e não é parcelada
    (conta a pagar única em aberto) — evita desencontro com parcelas/caixa."""
    if not is_admin():
        flash('Apenas administradores (N1 ou N2) podem editar despesas.', 'erro')
        return redirect(url_for('despesas'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM despesas WHERE id=%s", (did,))
        d = cur.fetchone()
        if not d:
            flash('Despesa não encontrada.', 'erro'); return redirect(url_for('despesas'))
        d = dict(d)
        categoria = request.form.get('categoria', '').strip()
        descricao = request.form.get('descricao', '').strip()
        forma = request.form.get('forma_pagamento', '').strip()
        tipo = request.form.get('tipo', 'avulsa').strip().lower()
        if tipo not in ('fixa', 'avulsa'): tipo = 'avulsa'
        local_ret = request.form.get('local_retirada', '').strip().lower()
        if local_ret not in ('caixa', 'pix'): local_ret = None
        obs_ret = request.form.get('obs_retirada', '').strip() or None
        # Valor/vencimento só são editáveis em conta a pagar única ainda em aberto
        editavel_valor = (not d.get('parcelado')) and (d.get('status') != 'pago')
        if categoria:
            cur.execute("INSERT INTO despesa_categorias (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING", (categoria,))
        if editavel_valor:
            valor = parse_brl(request.form.get('valor', '0'))
            venc = request.form.get('data_vencimento') or d.get('data_vencimento')
            cur.execute("""UPDATE despesas SET categoria=%s,descricao=%s,forma_pagamento=%s,tipo=%s,
                           local_retirada=%s,obs_retirada=%s,valor=%s,data_vencimento=%s WHERE id=%s""",
                        (categoria or None, descricao or None, forma or None, tipo, local_ret, obs_ret, valor, venc, did))
            # Atualiza a parcela única ainda em aberto (mantém a conta a pagar coerente)
            cur.execute("UPDATE despesa_parcelas SET valor=%s, data_vencimento=%s WHERE despesa_id=%s AND pago=FALSE",
                        (valor, venc, did))
        else:
            cur.execute("""UPDATE despesas SET categoria=%s,descricao=%s,forma_pagamento=%s,tipo=%s,
                           local_retirada=%s,obs_retirada=%s WHERE id=%s""",
                        (categoria or None, descricao or None, forma or None, tipo, local_ret, obs_ret, did))
        # Se a forma mudou, mantém o caixa coerente para lançamentos já pagos desta despesa
        cur.execute("UPDATE caixa SET forma_pagamento=%s WHERE despesa_id=%s", (forma or None, did))
        conn.commit(); flash('Despesa atualizada!', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally:
        cur.close(); close_db(conn)
    return redirect(url_for('despesas'))


@login_required
def excluir_despesa(did):
    if not pode_excluir():
        flash('Apenas o Administrador N1 pode excluir dados.', 'erro'); return redirect(url_for('despesas'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM caixa WHERE despesa_id=%s", (did,))
        cur.execute("DELETE FROM despesa_parcelas WHERE despesa_id=%s", (did,))
        cur.execute("DELETE FROM despesas WHERE id=%s", (did,))
        conn.commit(); flash('Despesa excluida.', 'ok')
    except Exception as e: conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('despesas'))


def register(app):
    app.add_url_rule('/despesas', 'despesas', despesas)
    app.add_url_rule('/despesas/nova', 'nova_despesa', nova_despesa, methods=['POST'])
    app.add_url_rule('/despesas/<int:did>/parcela/<int:pid>/pagar', 'pagar_parcela_despesa', pagar_parcela_despesa, methods=['POST'])
    app.add_url_rule('/despesas/<int:did>/editar', 'editar_despesa', editar_despesa, methods=['POST'])
    app.add_url_rule('/despesas/<int:did>/excluir', 'excluir_despesa', excluir_despesa, methods=['POST'])
