"""Configuração central do CD Gestão: variáveis de ambiente, fuso horário e
constantes visuais do cliente. Não importa nada do app (camada mais baixa)."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# ── Variáveis de ambiente obrigatórias / opcionais ──
SECRET_KEY = os.environ.get('SECRET_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')
APP_TZ = ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Sao_Paulo"))


def is_production():
    return os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER') == 'true'


def resolve_secret_key():
    """SECRET_KEY é obrigatória em produção; em dev local cai num valor fixo."""
    if SECRET_KEY:
        return SECRET_KEY
    if is_production():
        raise RuntimeError('Configure a variável de ambiente SECRET_KEY antes do deploy.')
    return 'cd-gestao-dev-local-only'


def agora_app():
    """Data/hora oficial do ERP (padrão: Brasil/São Paulo)."""
    return datetime.now(APP_TZ)


def hoje_app():
    """Data oficial do ERP, evitando diferença de UTC no Render."""
    return agora_app().date()


# ── Identidade visual ──
CLIENTE = {
    'nome': 'CD Gestao Empresarial',
    'loja': 'By Carol Duarte',
    'sigla': 'CD GESTAO',
    'tagline': 'Gestao inteligente para sua loja.',
    'cor_primaria': '#1a1a2e',
    'cor_secundaria': '#f4f4f6',
    'cor_botao': '#2e7d32'
}
CORES = ['#2e7d32', '#1565c0', '#6a1b9a', '#c62828', '#e65100', '#00695c', '#283593']
