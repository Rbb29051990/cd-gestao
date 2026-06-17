"""CD Gestão Empresarial — ponto de entrada da aplicação.

A partir da v98 o código foi dividido em módulos para facilitar manutenção:
  • config.py    — variáveis de ambiente, fuso horário e identidade visual
  • db.py        — pool de conexões PostgreSQL e helpers
  • utils.py     — funções compartilhadas (BRL, taxas, auditoria, estoque)
  • auth.py      — perfis, permissões, controle de acesso e contexto de template
  • db_init.py   — criação de tabelas, migrações, índices e seeds
  • routes/      — uma rota por área de negócio (cada módulo expõe register(app))

Este arquivo apenas cria o app Flask, aplica a configuração, registra os
handlers globais e as rotas, e inicializa o banco no start.
"""
import logging
import os
from flask import Flask

from config import resolve_secret_key, is_production
from db_init import init_db
from auth import (controle_acesso_abas, security_headers,
                  pagina_nao_encontrada, erro_interno)

# Módulos de rota (cada um expõe register(app))
from routes import (auth_routes, visao_geral, usuarios, clientes, estoque,
                    vendas, condicionais, crediarios, taxas, caixa, despesas, ajustes,
                    dashboard, admin)

logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))
logger = logging.getLogger('cd-gestao')

app = Flask(__name__, static_folder='static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = is_production()
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
app.secret_key = resolve_secret_key()

# ── Handlers globais ──
app.before_request(controle_acesso_abas)
app.after_request(security_headers)
app.errorhandler(404)(pagina_nao_encontrada)
app.errorhandler(500)(erro_interno)

# ── Registro de rotas (preserva os nomes de endpoint usados nos templates) ──
for modulo in (auth_routes, visao_geral, usuarios, clientes, estoque, vendas,
               condicionais, crediarios, taxas, caixa, despesas, ajustes, dashboard, admin):
    modulo.register(app)

# ── Inicialização do banco no start ──
with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"init_db: {e}")

if __name__ == '__main__':
    app.run(debug=False)
