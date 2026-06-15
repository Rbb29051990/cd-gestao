"""Rotas de Usuários: gestão (N1), troca de senha, foto de perfil/avatar."""
import base64
from flask import render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db, close_db
from auth import (login_required, get_ctx, pode_gerenciar_usuarios, perfil_label,
                  _perms_do_form, ABAS)
from utils import audit_log, _foto_valida


@login_required
def usuarios():
    ctx = get_ctx()
    if pode_gerenciar_usuarios():
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios ORDER BY id")
        lista = [dict(u) for u in cur.fetchall()]
        cur.close(); close_db(conn)
        for u in lista:
            u['perfil_nome'] = perfil_label(u.get('perfil'))
        ctx['usuarios'] = lista
    # não-N1 caem no modo "somente minha senha" (tratado no template)
    return render_template('usuarios.html', **ctx)


@login_required
def usuarios_trocar_senha():
    atual = request.form.get('senha_atual', '')
    nova = request.form.get('nova_senha', '')
    conf = request.form.get('confirma_senha', '')
    if not nova or len(nova) < 4:
        flash('A nova senha deve ter ao menos 4 caracteres.', 'erro'); return redirect(url_for('usuarios'))
    if nova != conf:
        flash('A confirmação não confere com a nova senha.', 'erro'); return redirect(url_for('usuarios'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT senha_hash FROM usuarios WHERE id=%s", (session['uid'],))
    u = cur.fetchone()
    if u and check_password_hash(u['senha_hash'], atual):
        cur.execute("UPDATE usuarios SET senha_hash=%s WHERE id=%s", (generate_password_hash(nova), session['uid']))
        conn.commit(); flash('Senha alterada com sucesso!', 'ok')
    else:
        flash('Senha atual incorreta.', 'erro')
    cur.close(); close_db(conn)
    return redirect(url_for('usuarios'))


@login_required
def usuario_avatar():
    uid = request.args.get('uid') or session.get('uid')
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT foto FROM usuarios WHERE id=%s", (uid,))
    row = cur.fetchone(); cur.close(); close_db(conn)
    foto = row['foto'] if row else None
    if foto and foto.startswith('data:'):
        try:
            header, b64 = foto.split(',', 1)
            mime = header.split(';')[0].replace('data:', '') or 'image/jpeg'
            resp = Response(base64.b64decode(b64), mimetype=mime)
            resp.headers['Cache-Control'] = 'no-cache'
            return resp
        except Exception:
            pass
    return ('', 404)


@login_required
def usuario_foto():
    foto = _foto_valida(request.form.get('foto', '').strip())
    if not foto:
        flash('Imagem inválida ou muito grande.', 'erro'); return redirect(request.referrer or url_for('usuarios'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("UPDATE usuarios SET foto=%s WHERE id=%s", (foto, session['uid']))
        conn.commit()
        session['usuario_foto'] = True
        session['foto_v'] = session.get('foto_v', 0) + 1
        flash('Foto de perfil atualizada!', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(request.referrer or url_for('usuarios'))


@login_required
def usuario_foto_remover():
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("UPDATE usuarios SET foto=NULL WHERE id=%s", (session['uid'],))
        conn.commit()
        session['usuario_foto'] = False
        session['foto_v'] = session.get('foto_v', 0) + 1
        flash('Foto de perfil removida.', 'ok')
    except Exception as e:
        conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(request.referrer or url_for('usuarios'))


@login_required
def usuario_novo():
    if not pode_gerenciar_usuarios():
        flash('Apenas o Administrador N1 pode cadastrar usuários.', 'erro')
        return redirect(url_for('usuarios'))
    ctx = get_ctx(); ctx['abas'] = ABAS
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        senha = request.form.get('senha', '').strip()
        perfil = request.form.get('perfil', 'vendedor')
        if perfil not in ('admin_n1', 'admin_n2', 'vendedor'): perfil = 'vendedor'
        if not nome or len(senha) < 4:
            flash('Informe o nome e uma senha de ao menos 4 caracteres.', 'erro')
            return render_template('usuario_form.html', **ctx)
        perms = _perms_do_form(perfil)
        foto = _foto_valida(request.form.get('foto', '').strip())
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)), 0) as m FROM usuarios WHERE codigo ~ '^F[0-9]+$'")
        n = cur.fetchone()['m']
        try:
            cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes,foto) VALUES (%s,%s,%s,%s,%s,%s)",
                        (f"F{n+1}", nome, generate_password_hash(senha), perfil, perms, foto))
            conn.commit(); flash('Usuário cadastrado!', 'ok')
        except Exception as e: conn.rollback(); flash(str(e), 'erro')
        finally: cur.close(); close_db(conn)
        return redirect(url_for('usuarios'))
    return render_template('usuario_form.html', **ctx)


@login_required
def usuario_editar(uid):
    if not pode_gerenciar_usuarios():
        flash('Apenas o Administrador N1 pode editar usuários.', 'erro')
        return redirect(url_for('usuarios'))
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        perfil = request.form.get('perfil', 'vendedor')
        if perfil not in ('admin_n1', 'admin_n2', 'vendedor'): perfil = 'vendedor'
        # Trava anti-bloqueio: N1 não pode rebaixar o próprio perfil
        if uid == session.get('uid') and perfil != 'admin_n1':
            flash('Você não pode alterar o seu próprio perfil de Administrador N1.', 'erro')
            cur.close(); close_db(conn); return redirect(url_for('usuarios'))
        perms = _perms_do_form(perfil)
        nova_senha = request.form.get('nova_senha', '').strip()
        if nova_senha:
            cur.execute("UPDATE usuarios SET nome=%s,perfil=%s,permissoes=%s,senha_hash=%s WHERE id=%s",
                        (nome, perfil, perms, generate_password_hash(nova_senha), uid))
        else:
            cur.execute("UPDATE usuarios SET nome=%s,perfil=%s,permissoes=%s WHERE id=%s", (nome, perfil, perms, uid))
        audit_log(cur, 'ALTERAR_USUARIO', 'usuarios', uid, {'nome': nome, 'perfil': perfil, 'permissoes': perms, 'alterou_senha': bool(nova_senha)})
        conn.commit(); cur.close(); close_db(conn)
        flash('Usuario atualizado!', 'ok')
        return redirect(url_for('usuarios'))
    cur.execute("SELECT * FROM usuarios WHERE id=%s", (uid,))
    row = cur.fetchone()
    if not row:
        cur.close(); close_db(conn)
        flash('Usuario nao encontrado.', 'erro'); return redirect(url_for('usuarios'))
    user = dict(row)
    user['perms_lista'] = [x.strip() for x in (user.get('permissoes') or '').split(',') if x.strip()]
    cur.close(); close_db(conn)
    ctx = get_ctx(); ctx['user'] = user; ctx['abas'] = ABAS
    return render_template('usuario_editar.html', **ctx)


@login_required
def usuario_toggle(uid):
    if not pode_gerenciar_usuarios():
        flash('Apenas o Administrador N1 pode ativar/desativar usuários.', 'erro')
        return redirect(url_for('usuarios'))
    if uid == session.get('uid'):
        flash('Você não pode desativar a si mesmo.', 'erro')
        return redirect(url_for('usuarios'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE usuarios SET ativo=NOT ativo WHERE id=%s", (uid,))
    conn.commit(); cur.close(); close_db(conn)
    return redirect(url_for('usuarios'))


@login_required
def usuario_excluir(uid):
    if not pode_gerenciar_usuarios():
        flash('Apenas o Administrador N1 pode excluir usuários.', 'erro')
        return redirect(url_for('usuarios'))
    if uid == session.get('uid'):
        flash('Você não pode excluir a si mesmo.', 'erro')
        return redirect(url_for('usuarios'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM usuarios WHERE id=%s", (uid,))
        conn.commit(); flash('Usuário excluído.', 'ok')
    except Exception as e: conn.rollback(); flash(str(e), 'erro')
    finally: cur.close(); close_db(conn)
    return redirect(url_for('usuarios'))


@login_required
def minha_senha():
    ctx = get_ctx()
    if request.method == 'POST':
        atual = request.form.get('senha_atual', '')
        nova = request.form.get('nova_senha', '')
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT senha_hash FROM usuarios WHERE id=%s", (session['uid'],))
        u = cur.fetchone()
        if u and check_password_hash(u['senha_hash'], atual):
            cur.execute("UPDATE usuarios SET senha_hash=%s WHERE id=%s", (generate_password_hash(nova), session['uid']))
            conn.commit(); flash('Senha alterada!', 'ok')
        else: flash('Senha atual incorreta.', 'erro')
        cur.close(); close_db(conn)
    return render_template('minha_senha.html', **ctx)


def register(app):
    app.add_url_rule('/usuarios', 'usuarios', usuarios)
    app.add_url_rule('/usuarios/senha', 'usuarios_trocar_senha', usuarios_trocar_senha, methods=['POST'])
    app.add_url_rule('/usuarios/avatar', 'usuario_avatar', usuario_avatar)
    app.add_url_rule('/usuarios/foto', 'usuario_foto', usuario_foto, methods=['POST'])
    app.add_url_rule('/usuarios/foto/remover', 'usuario_foto_remover', usuario_foto_remover, methods=['POST'])
    app.add_url_rule('/usuarios/novo', 'usuario_novo', usuario_novo, methods=['GET', 'POST'])
    app.add_url_rule('/usuarios/<int:uid>/editar', 'usuario_editar', usuario_editar, methods=['GET', 'POST'])
    app.add_url_rule('/usuarios/<int:uid>/toggle', 'usuario_toggle', usuario_toggle, methods=['POST'])
    app.add_url_rule('/usuarios/<int:uid>/excluir', 'usuario_excluir', usuario_excluir, methods=['POST'])
    app.add_url_rule('/minha-senha', 'minha_senha', minha_senha, methods=['GET', 'POST'])
