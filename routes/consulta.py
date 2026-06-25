"""Consulta de mercadoria: busca rápida (código ou descrição), somente leitura.
Mostra foto, preço original, preço promocional e saldo em estoque — útil no balcão
quando a etiqueta se perdeu. É uma aba controlável por permissão (consta em ABAS/
SEG_ABA): admins têm acesso total; vendedores só com a aba 'consulta' marcada."""
import base64
from flask import render_template, request, jsonify, Response
from db import get_db, close_db
from auth import login_required, get_ctx


@login_required
def consulta():
    return render_template('consulta.html', **get_ctx())


@login_required
def consulta_buscar():
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify({'itens': []})
    termo = f"%{q}%"
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT id,codigo,modelo,descricao,tamanho,valor_venda,desconto_promo,quantidade,
                          (foto IS NOT NULL) AS tem_foto
                   FROM estoque
                   WHERE ativo=TRUE AND (
                         LOWER(codigo) LIKE %s OR LOWER(modelo) LIKE %s OR LOWER(descricao) LIKE %s)
                   ORDER BY codigo LIMIT 40""", (termo, termo, termo))
    itens = []
    for r in cur.fetchall():
        it = dict(r)
        dp = float(it.get('desconto_promo') or 0)
        it['valor_venda'] = float(it['valor_venda'] or 0)
        it['desconto_promo'] = dp
        it['valor_promo'] = round(it['valor_venda'] * (1 - dp / 100), 2) if dp > 0 else None
        it['tem_foto'] = bool(it['tem_foto'])
        itens.append(it)
    cur.close(); close_db(conn)
    return jsonify({'itens': itens})


@login_required
def consulta_foto(eid):
    """Serve a foto do produto (data URI guardado no banco) como imagem real,
    para a busca não precisar trafegar o base64 inteiro em cada tecla."""
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT foto FROM estoque WHERE id=%s", (eid,))
    row = cur.fetchone(); cur.close(); close_db(conn)
    foto = row['foto'] if row else None
    if not foto or not foto.startswith('data:'):
        return ('', 404)
    try:
        header, b64 = foto.split(',', 1)
        mime = header.split(':', 1)[1].split(';', 1)[0]
        return Response(base64.b64decode(b64), mimetype=mime)
    except Exception:
        return ('', 404)


def register(app):
    app.add_url_rule('/consulta', 'consulta', consulta)
    app.add_url_rule('/consulta/buscar', 'consulta_buscar', consulta_buscar)
    app.add_url_rule('/consulta/foto/<int:eid>', 'consulta_foto', consulta_foto)
