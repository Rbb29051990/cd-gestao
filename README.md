# CD Gestão Empresarial — v73

## Novidades da v73 (2026-06-05)
- **Botão "+ Nova venda" no topo da página**: movido para acima do ranking, alinhado à esquerda (acesso mais rápido).
- **Faixa de resumo do período**: 3 chips ao lado do botão mostrando **Total do período**, **Nº de vendas** e **Ticket médio** — calculados automaticamente a partir dos filtros de data.
- **Cabeçalho sticky (fixo)**: ao rolar a lista de vendas, o cabeçalho da tabela fica preso no topo para referência fácil.
- **Busca rápida**: campo de pesquisa que filtra a tabela em tempo real por cliente, código, vendedora ou qualquer texto.
- **Ordenação clicável**: clique nos cabeçalhos **Data**, **Vendedora**, **Valor final** e **Pagamento** para ordenar A→Z / Z→A ou maior→menor. Seta indicando a direção da ordenação.

## Novidades da v71 (2026-06-05)
- **Vendas — ranking de vendedoras moderno**: cards compactos com donut de participação, ticket médio, vendas e clientes por vendedora.

## Novidades da v67 (2026-06-04)
- **Visão Geral — design moderno**: a tabela "Controle de Entradas" ganhou visual de app de gestão: cabeçalho com os totais (bruto e líquido) em destaque, ícone por forma de pagamento, efeito de hover nas linhas, números alinhados e linha de total realçada. Mesmas informações da v66.

## Novidades da v66 (2026-06-04)
- **Visão Geral — tabela "Controle de Entradas"**: o card de faturamento virou uma tabela clara, com cabeçalho e colunas Forma de Pagamento / Valor Bruto / Valor Líquido, e linha de TOTAL destacada. Mesmos dados da v65, só com apresentação em formato de planilha.

## Novidades da v65 (2026-06-04)
- **Visão Geral — crediário detalhado**: a linha "Crediário" do faturamento foi substituída por duas, iguais às do Caixa:
  - **Crediário (entradas)** — sinal pago no momento da venda no crediário.
  - **Crediário (parcelas)** — parcelas recebidas no período.
  - Importante: o crediário agora reflete o que **entrou** no período (recebido), não o valor total da venda. O total do período passa a somar essas entradas/parcelas.

## Novidades da v64 (2026-06-04)
- **Visão Geral — bruto e líquido**: o card de faturamento agora mostra, lado a lado, o valor **bruto** e o **líquido** (após taxas de cartão) de cada forma de pagamento, com totais.
- **Visão Geral — filtro de período**: adicionado o mesmo seletor de datas do Caixa (De/Até + atalhos Hoje, 7 dias, Mês). O faturamento passa a respeitar o período escolhido.

## Novidades da v63 (2026-06-04)
- **Caixa — taxas descontadas detalhadas**: o card "Taxas descontadas" agora mostra o desconto de cada forma de pagamento (crédito à vista, crédito parcelado, débito, link). Só aparecem as formas com desconto no período.

## Novidades da v62 (2026-06-04)
- **Caixa — crediário detalhado**: o card "Total entradas" agora separa o crediário em duas linhas:
  - **Crediário (entradas)** — valor de entrada/sinal pago no momento da venda no crediário.
  - **Crediário (parcelas)** — pagamentos de parcelas recebidos na aba Crediários.

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

