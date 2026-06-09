# Arquitetura V91 — CD Gestão Empresarial

Esta versão mantém compatibilidade com o deploy atual, mas prepara o ERP para crescer com menos risco.

## Estado atual

O `app.py` ainda concentra as rotas e regras do sistema para evitar uma quebra grande em produção. A V91 adiciona estabilidade, segurança e documentação para que a próxima evolução possa ser feita por módulos sem reescrever tudo de uma vez.

## Direção recomendada para V92+

```text
app.py                  # criação do Flask e registro de blueprints
config.py               # variáveis de ambiente e configuração
extensions.py           # pool de banco, logging e extensões
routes/
  auth.py
  usuarios.py
  clientes.py
  estoque.py
  vendas.py
  caixa.py
  despesas.py
  crediarios.py
  condicionais.py
  dashboards.py
services/
  financeiro_service.py
  estoque_service.py
  vendas_service.py
  clientes_service.py
repositories/
  base_repository.py
  estoque_repository.py
  vendas_repository.py
utils/
  permissions.py
  formatters.py
  validators.py
```

## Variáveis obrigatórias no deploy

```text
DATABASE_URL=<url do PostgreSQL>
SECRET_KEY=<chave secreta forte>
```

## Variáveis opcionais

```text
DB_POOL_MAX=5
LOG_LEVEL=INFO
ALLOW_SETUP=true              # usar apenas temporariamente
ALLOW_RESET_USUARIOS=true     # usar apenas temporariamente
SEED_DEFAULT_USERS=true       # usar apenas em ambiente inicial/controlado
```

## Cuidados antes de subir em produção

1. Configure `SECRET_KEY` no Render/GitHub Secrets.
2. Configure `DATABASE_URL`.
3. Evite deixar `ALLOW_SETUP`, `ALLOW_RESET_USUARIOS` ou `SEED_DEFAULT_USERS` ligados permanentemente.
4. Após deploy, teste `/healthz`.
5. Limpe cache do navegador se algum estilo antigo aparecer.
