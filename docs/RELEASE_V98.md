# Release v98 — Reorganização interna do código (refactor)

**Data:** 2026-06-09
**Tipo:** Refatoração estrutural. **Sem mudança de comportamento** em relação à v97.

## Objetivo
Dividir o `app.py` monolítico (2279 linhas) em módulos por responsabilidade, para
que correções futuras mexam apenas no arquivo da área afetada — reduzindo o tempo e
o esforço de manutenção.

## Estrutura nova

```
cd-gestao-v98/
  app.py          # cria o app, configura, registra handlers e rotas, init_db no start
  config.py       # SECRET_KEY/DATABASE_URL/APP_TZ, is_production, agora_app/hoje_app, CLIENTE/CORES
  db.py           # pool (SimpleConnectionPool), get_db/close_db/db_cursor, logger
  utils.py        # parse_brl, calcular_liquido, get_taxa_vigente, bloquear_estoque_negativo,
                  #   audit_log, _foto_valida
  auth.py         # perfis/permissões, login_required, get_ctx, _perms_do_form,
                  #   handlers before/after request e errorhandlers
  db_init.py      # init_db(): tabelas, migrações, índices, seeds
  routes/
    auth_routes.py    # index, login, logout
    visao_geral.py    # visao_geral
    usuarios.py       # usuarios + senha/avatar/foto/novo/editar/toggle/excluir, minha_senha
    clientes.py       # clientes, novo, verificar, ficha, editar, excluir
    estoque.py        # estoque, novo, nova-entrada, modelo/tamanho, etiquetas, ficha, editar, excluir
    vendas.py         # vendas, nova, ficha, excluir, editar, ranking, buscar-ref, buscar-cliente
    condicionais.py   # condicionais + nova/ficha/gerar-venda/devolver/confirmar-transferencia/excluir
    crediarios.py     # crediarios, pagar parcela
    taxas.py          # taxas
    caixa.py          # caixa
    despesas.py       # despesas, nova, pagar parcela, excluir
    dashboard.py      # dashboard_view
    admin.py          # healthz, setup, reset-usuarios, limpar-caixa-orfaos, versao
```

## Decisões técnicas
- **Sem Blueprints.** Cada módulo de rota tem funções de view normais + uma função
  `register(app)` que chama `app.add_url_rule(rule, endpoint, view_func, methods)`.
  Isso **preserva os nomes de endpoint** (`url_for('vendas')` continua `'vendas'`),
  então **nenhum template precisou mudar**. Blueprints renomeariam os endpoints
  (`vendas.vendas`) e quebrariam os links.
- **Imports estritamente de baixo para cima** (config → db/auth → utils → db_init →
  routes → app), sem import circular.
- **URLs idênticas** às da v97 — o controle de acesso por aba (`SEG_ABA`, que mapeia
  o 1º segmento da URL) continua funcionando sem ajuste.

## Validação feita (sem Python local)
- `url_for(...)` referenciados no código Python: todos apontam para endpoints registrados.
- Templates: só usam `url_for('static', ...)`; o resto é URL fixa (preservada).
- Contagem de rotas: **59 na v97 = 59 na v98** (nenhuma rota perdida).
- Sem `from app import` nos módulos de rota (nenhum ciclo).
- Todos os 13 módulos de rota expõem `register(app)`.

## Pós-deploy (conferir no Render)
- `/healthz` deve responder `{"status":"ok","version":"v98"}`.
- Fazer login e abrir cada aba uma vez.
