"""Rotas de autenticação: login, logout e a home pública (index)."""
import logging
import time
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


# v152: proteção contra tentativa de adivinhar senha — após 5 erros do mesmo usuário no mesmo
# IP, bloqueia novas tentativas por 10 minutos (em memória; reinicia com o servidor).
_FALHAS_LOGIN = {}
_MAX_FALHAS = 5
_JANELA_FALHAS_SEG = 600


def _ip_cliente():
    return (request.headers.get('X-Forwarded-For', request.remote_addr) or '').split(',')[0].strip()


def _login_bloqueado(chave):
    agora = time.time()
    recentes = [t for t in _FALHAS_LOGIN.get(chave, []) if agora - t < _JANELA_FALHAS_SEG]
    if recentes:
        _FALHAS_LOGIN[chave] = recentes
    else:
        _FALHAS_LOGIN.pop(chave, None)
    return len(recentes) >= _MAX_FALHAS


def login():
    nome = request.form.get('usuario', '').strip()
    senha = request.form.get('senha', '').strip()
    chave = (_ip_cliente(), nome.lower())
    if _login_bloqueado(chave):
        return render_template('login.html', cliente=CLIENTE,
                               erro='Muitas tentativas erradas. Aguarde 10 minutos e tente de novo.')
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE nome=%s AND ativo=TRUE", (nome,))
    u = cur.fetchone(); cur.close(); close_db(conn)
    if u and u['senha_hash'] and check_password_hash(u['senha_hash'], senha):
        _FALHAS_LOGIN.pop(chave, None)
        session.update(uid=u['id'], nome=u['nome'], perfil=norm_perfil(u['perfil']),
                       codigo=u.get('codigo', ''),
                       permissoes=u.get('permissoes', 'visao_geral,clientes,vendas,estoque'),
                       usuario_foto=bool(u.get('foto')), foto_v=1)
        return redirect(home_url())
    if len(_FALHAS_LOGIN) > 5000:
        _FALHAS_LOGIN.clear()
    _FALHAS_LOGIN.setdefault(chave, []).append(time.time())
    logger.warning('Falha de login para usuario=%s ip=%s', nome, request.headers.get('X-Forwarded-For', request.remote_addr))
    return render_template('login.html', cliente=CLIENTE, erro='Usuario ou senha incorretos.')


def logout():
    session.clear()
    return redirect(url_for('index'))


def register(app):
    app.add_url_rule('/', 'index', index)
    app.add_url_rule('/login', 'login', login, methods=['POST'])
    app.add_url_rule('/logout', 'logout', logout)
