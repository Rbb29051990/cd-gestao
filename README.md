# CD Gestão Empresarial — v61

## Novidades da v61 (2026-06-04)
- Corrigido vazamento de conexão na tela de Estoque (esgotava o banco em produção).
- Taxas: passa a registrar corretamente o autor (usuário) da alteração.
- Rotas `/versao` e `/admin/limpar-caixa-orfaos` agora funcionam também ao rodar localmente.
- Fichas e telas de edição (cliente, estoque, usuário) não dão mais erro ao abrir um registro inexistente — redirecionam com aviso.


## Como fazer o deploy (atualizar o sistema)

### Se estiver no HEROKU:
```
heroku login
cd cd-gestao
git init
git add .
git commit -m "v24"
heroku git:remote -a NOME-DO-SEU-APP
git push heroku main
```

### Se estiver no RENDER:
1. Acesse o painel do Render
2. Vá em "Manual Deploy" → "Deploy latest commit"
3. Ou faça upload dos arquivos via GitHub

### Se estiver rodando LOCAL (python app.py):
1. Substitua TODOS os arquivos da pasta pelo conteúdo deste ZIP
2. Pare o servidor (Ctrl+C)
3. Rode novamente: `python app.py`

### IMPORTANTE — Primeira execução:
Acesse: https://seu-app.com/setup
Isso cria as tabelas e usuários padrão.

### Usuários padrão:
- Renan Barcellos / renan123
- Carol Duarte / carol123

