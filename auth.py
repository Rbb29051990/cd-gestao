"""Perfis, permissões e controle de acesso por aba.
Inclui o decorator login_required, o contexto de template (get_ctx) e os
handlers de before/after request e de erro — registrados no app.py."""
import logging
from functools import wraps
from flask import session, request, redirect, url_for, render_template
from config import CLIENTE

logger = logging.getLogger('cd-gestao')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'uid' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# ══════════════ PERFIS E PERMISSÕES ══════════════
# Abas controláveis (id, rótulo). 'usuarios' é sempre acessível (troca de senha).
ABAS = [
    ('visao_geral', 'Visão Geral'),
    ('clientes',    'Clientes'),
    ('estoque',     'Estoque'),
    ('vendas',      'Vendas'),
    ('condicionais', 'Condicional'),
    ('caixa',       'Caixa'),
    ('crediarios',  'Crediários'),
    ('despesas',    'Despesas'),
    ('taxas',       'Taxas'),
    ('dashboards',  'Dashboards'),
]
ABAS_DICT = dict(ABAS)
# Primeiro segmento da URL -> aba
SEG_ABA = {
    'visao-geral': 'visao_geral', 'clientes': 'clientes', 'estoque': 'estoque',
    'vendas': 'vendas', 'condicionais': 'condicionais', 'caixa': 'caixa',
    'crediarios': 'crediarios', 'despesas': 'despesas', 'taxas': 'taxas',
    'dashboard': 'dashboards', 'usuarios': 'usuarios',
}
# aba -> endpoint (para montar a home dinâmica)
ABA_ROUTE = {
    'visao_geral': 'visao_geral', 'clientes': 'clientes', 'estoque': 'estoque',
    'vendas': 'vendas', 'condicionais': 'condicionais', 'caixa': 'caixa',
    'crediarios': 'crediarios', 'despesas': 'despesas', 'taxas': 'taxas',
    'dashboards': 'dashboard_view',
}
# Endpoints liberados para qualquer logado (helpers e utilitários compartilhados)
ALLOW_ENDPOINTS = {'index', 'login', 'logout', 'setup', 'reset_usuarios', 'minha_senha',
    'versao', 'buscar_ref', 'buscar_cliente', 'usuarios_trocar_senha', 'limpar_caixa_orfaos'}
PERFIL_LABELS = {'admin_n1': 'Administrador (a) N1', 'admin_n2': 'Administrador (a) N2', 'vendedor': 'Vendedor (a)'}


def norm_perfil(p):
    """Compatibilidade: o perfil legado 'admin' (antes da v85) equivale a Administrador N1."""
    if p == 'admin' or p == 'administrador':
        return 'admin_n1'
    return p or 'vendedor'


def perfil_label(p):
    p = norm_perfil(p)
    return PERFIL_LABELS.get(p, p or '—')


def is_admin(p=None):
    return norm_perfil(p if p is not None else session.get('perfil')) in ('admin_n1', 'admin_n2')


def pode_excluir(p=None):
    return norm_perfil(p if p is not None else session.get('perfil')) == 'admin_n1'


def pode_gerenciar_usuarios(p=None):
    return norm_perfil(p if p is not None else session.get('perfil')) == 'admin_n1'


def tem_acesso_aba(aba, perfil=None, permissoes=None):
    perfil = norm_perfil(perfil if perfil is not None else session.get('perfil', 'vendedor'))
    if perfil in ('admin_n1', 'admin_n2'):
        return True
    if aba == 'usuarios':
        return True   # todos podem entrar p/ trocar a própria senha
    perms = permissoes if permissoes is not None else (session.get('permissoes') or '')
    return aba in [x.strip() for x in perms.split(',') if x.strip()]


def home_url():
    """Primeira aba que o usuário pode acessar (evita cair numa aba bloqueada no login)."""
    perfil = norm_perfil(session.get('perfil'))
    if perfil in ('admin_n1', 'admin_n2'):
        return url_for('visao_geral')
    perms = [x.strip() for x in (session.get('permissoes') or '').split(',') if x.strip()]
    for aba in [a for a, _ in ABAS]:
        if aba in perms and aba in ABA_ROUTE:
            return url_for(ABA_ROUTE[aba])
    return url_for('usuarios')   # nada liberado: só troca de senha


def get_ctx():
    p = norm_perfil(session.get('perfil'))
    return dict(nome=session.get('nome'), perfil=p, cliente=CLIENTE,
                permissoes=session.get('permissoes', ''),
                pode_excluir=(p == 'admin_n1'),
                pode_gerenciar_usuarios=(p == 'admin_n1'),
                is_admin_user=(p in ('admin_n1', 'admin_n2')),
                perfil_nome=perfil_label(p),
                usuario_foto=session.get('usuario_foto', False),
                avatar_v=session.get('foto_v', 0))


def _perms_do_form(perfil):
    """Vendedor: usa as abas marcadas. Admins: acesso total (todas as abas)."""
    if perfil == 'vendedor':
        sel = [a for a in request.form.getlist('permissoes') if a in ABAS_DICT]
        return ','.join(sel)
    return ','.join([a for a, _ in ABAS])


# ── Handlers registrados no app.py (before/after request e erros) ──
def controle_acesso_abas():
    if 'uid' not in session:
        return  # rotas públicas / login_required cuida do redirect
    ep = request.endpoint
    if ep is None or ep in ALLOW_ENDPOINTS or ep.startswith('static'):
        return
    seg = request.path.strip('/').split('/')[0] if request.path.strip('/') else ''
    aba = SEG_ABA.get(seg)
    if aba and not tem_acesso_aba(aba):
        ctx = get_ctx(); ctx['aba_negada'] = ABAS_DICT.get(aba, aba)
        return render_template('acesso_negado.html', **ctx), 403


def security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(self), geolocation=()')
    return response


def pagina_nao_encontrada(e):
    if 'uid' in session:
        ctx = get_ctx(); ctx['aba_negada'] = 'Página não encontrada'
        return render_template('acesso_negado.html', **ctx), 404
    return redirect(url_for('index'))


def erro_interno(e):
    logger.exception('Erro interno na aplicação')
    return '<h2 style="font-family:sans-serif;padding:40px">Erro interno. Tente novamente em instantes.</h2>', 500
