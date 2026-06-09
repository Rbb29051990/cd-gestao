"""Rotas de autenticação: login, logout e a home pública (index)."""
import logging
from flask import render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from config import CLIENTE
from db import get_db, close_db
from auth import norm_perfil, home_url

logger = logging.getLogger('cd-gestao')


def index():
    if 'uid' in session:
        return redirect(home_url())
    return render_template('login.html', cliente=CLIENTE, erro=None)


def login():
    nome = request.form.get('usuario', '').strip()
    senha = request.form.get('senha', '').strip()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE nome=%s AND ativo=TRUE", (nome,))
    u = cur.fetchone(); cur.close(); close_db(conn)
    if u and check_password_hash(u['senha_hash'], senha):
        session.update(uid=u['id'], nome=u['nome'], perfil=norm_perfil(u['perfil']),
                       codigo=u.get('codigo', ''),
                       permissoes=u.get('permissoes', 'visao_geral,clientes,vendas,estoque'),
                       usuario_foto=bool(u.get('foto')), foto_v=1)
        return redirect(home_url())
    logger.warning('Falha de login para usuario=%s ip=%s', nome, request.headers.get('X-Forwarded-For', request.remote_addr))
    return render_template('login.html', cliente=CLIENTE, erro='Usuario ou senha incorretos.')


def logout():
    session.clear()
    return redirect(url_for('index'))


def register(app):
    app.add_url_rule('/', 'index', index)
    app.add_url_rule('/login', 'login', login, methods=['POST'])
    app.add_url_rule('/logout', 'logout', logout)
