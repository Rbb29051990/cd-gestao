# CD Gestão Empresarial — v97

## Foco da versão
Segurança, auditoria, bloqueio de rotas de desenvolvimento em produção, registro de alterações críticas e prevenção de conflitos de estoque.

## Itens implementados
- Bloqueio de `/setup` em produção, salvo `ALLOW_SETUP=true`.
- Bloqueio de `/reset-usuarios`, salvo `ALLOW_RESET_USUARIOS=true`.
- Tabela `auditoria` para ações críticas.
- Registro de criação de venda e exclusões sensíveis.
- Registro de alteração de usuário/permissões.
- Log de falhas de login.
- Baixa de estoque com `SELECT ... FOR UPDATE`.
- Validação de saldo antes da venda.
- Restrição para impedir estoque negativo.
- Índices de apoio para crescimento.

## Variáveis importantes no Render
- `SECRET_KEY` obrigatório.
- `DATABASE_URL` obrigatório.
- `APP_TIMEZONE=America/Sao_Paulo` recomendado.
- `ALLOW_SETUP=true` apenas temporariamente quando precisar executar setup.
- `ALLOW_RESET_USUARIOS=true` apenas temporariamente e com muito cuidado.
