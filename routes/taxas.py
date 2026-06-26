"""Rota de Taxas: registra nova vigência de taxas (só admin) e mostra histórico."""
from flask import render_template, request, redirect, url_for, session, flash
from db import get_db, close_db
from config import hoje_app
from auth import login_required, get_ctx, is_admin
from utils import parse_brl, get_taxa_vigente


@login_required
def taxas():
    if not is_admin():
        flash('Apenas administradores podem gerenciar taxas.', 'erro')
        return redirect(url_for('caixa'))
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        try:
            def _opt(name):
                """Taxa opcional por parcela: em branco vira NULL."""
                raw = (request.form.get(name) or '').strip()
                return parse_brl(raw) if raw else None
            # Taxa Flex: 1x a 12x (1x = crédito à vista; 2x..12x = crédito parcelado)
            parc = {n: _opt(f'credito_{n}x') for n in range(1, 13)}
            deb = parse_brl(request.form.get('debito', '0'))
            ant = parse_brl(request.form.get('antecipacao', '0'))
            # Colunas antigas espelham a Taxa Flex (compatibilidade): à vista=1x, parcelado base=2x; link não é usado
            cv, cp, lnk = parc[1], parc[2], 0
            vig = request.form.get('vigencia_em', str(hoje_app()))
            cur.execute("""INSERT INTO taxas_pagamento
                (vigencia_em,credito_vista,credito_parcelado,debito,link,antecipacao,
                 credito_1x,credito_2x,credito_3x,credito_4x,credito_5x,credito_6x,
                 credito_7x,credito_8x,credito_9x,credito_10x,credito_11x,credito_12x,
                 usuario_id)
                VALUES (%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, %s)""",
                (vig, cv, cp, deb, lnk, ant,
                 parc[1], parc[2], parc[3], parc[4], parc[5], parc[6],
                 parc[7], parc[8], parc[9], parc[10], parc[11], parc[12],
                 session.get('uid')))
            conn.commit()
            flash('Taxas atualizadas com sucesso!', 'ok')
        except Exception as e:
            conn.rollback(); flash(str(e), 'erro')
        finally: cur.close(); close_db(conn)
        return redirect(url_for('taxas'))
    # GET
    taxa_atual = get_taxa_vigente()
    cur.execute("""SELECT t.*,u.nome as usuario_nome FROM taxas_pagamento t
                   LEFT JOIN usuarios u ON t.usuario_id=u.id
                   ORDER BY t.vigencia_em DESC LIMIT 20""")
    historico = [dict(r) for r in cur.fetchall()]
    cur.close(); close_db(conn)
    ctx = get_ctx()
    ctx.update(taxa_atual=taxa_atual, historico=historico, today=str(hoje_app()))
    return render_template('taxas.html', **ctx)


def register(app):
    app.add_url_rule('/taxas', 'taxas', taxas, methods=['GET', 'POST'])
