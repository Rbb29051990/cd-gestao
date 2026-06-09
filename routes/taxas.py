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
            cv  = parse_brl(request.form.get('credito_vista', '0'))
            cp  = parse_brl(request.form.get('credito_parcelado', '0'))
            deb = parse_brl(request.form.get('debito', '0'))
            lnk = parse_brl(request.form.get('link', '0'))
            ant = parse_brl(request.form.get('antecipacao', '0'))
            vig = request.form.get('vigencia_em', str(hoje_app()))
            cur.execute("""INSERT INTO taxas_pagamento
                (vigencia_em,credito_vista,credito_parcelado,debito,link,antecipacao,usuario_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (vig, cv, cp, deb, lnk, ant, session.get('uid')))
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
