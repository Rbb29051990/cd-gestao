# CD Gestão Empresarial — v88

## Novidades da v88 (2026-06-08)
- **Menu lateral**: o botão **Sair** saiu do topo e agora fica no **final do menu**, logo abaixo de Usuários, com o mesmo visual moderno do menu (em vermelho).
- **Topo limpo**: removido o botão **"Minha senha"** do topo do ERP.
- **Foto de perfil no avatar**: clique na **bolinha** (avatar) no topo para **carregar ou tirar uma foto** da pessoa. Sem foto, continua mostrando as **iniciais do nome**. Também dá para definir a foto **no cadastro de um novo usuário**.
- **Acesso restrito**: ao clicar numa aba sem permissão, a caixa de aviso **não mostra mais** a opção de trocar senha.
- **Aba Usuários (N1)**: os botões **Editar / Desativar / Excluir** foram **padronizados** (mesmo tamanho e alinhamento).
- **Ortografia**: corrigido **"vendedora" → "Vendedor (a)"** em todo o ERP (telas, tabelas, ranking, etc.).
- **Condicional / Transferência**: ao **finalizar uma transferência**, agora também é possível escolher a **forma de pagamento** (mesmo fluxo da condicional — gerar venda).
- **Despesas**: corrigida a **máscara do valor** ao lançar uma nova despesa (agora usa o padrão de caixa registradora do ERP e não dá mais erro ao digitar, inclusive em despesa fixa).

## Novidades da v87 (2026-06-07) — Correção de perfil Administrador
- **Correção do acesso de Administrador**: contas com o perfil antigo **"admin"** (de antes da reformulação de perfis) agora são reconhecidas automaticamente como **Administrador (a) N1** — com acesso total, exclusão de dados e gestão de usuários.
- Duas camadas de segurança: (1) o banco é corrigido automaticamente no start (admin → admin_n1, em bloco isolado e à prova de falhas) e (2) o sistema trata "admin" como N1 em tempo de execução, então funciona mesmo sem precisar sair e entrar de novo.
- Se ainda aparecer "Administrador" no seu nome, basta **sair e entrar novamente** para atualizar a sessão.

## Novidades da v86 (2026-06-07) — Estoque e etiquetas
- **Cadastro de produto como botão**: na tela de Estoque, "**➕ Cadastrar produto**" e "**🏷️ Imprimir etiquetas**" agora são **botões** no topo da lista (não mais abas). Ao clicar, abre a tela correspondente com um "**← Voltar ao estoque**".
- **Etiquetas — busca por código**: digite o **código do produto** (P...) e o sistema mostra modelo, tamanho, preço e saldo. Informe **quantas etiquetas** quer daquele item e clique em **+ Adicionar** — montando uma **fila de etiquetas** (dá para juntar vários produtos; também há "carregar todos de uma data").
- **Folha A4 configurada para a sua folha adesiva**: retrato, **7 colunas × 18 linhas = 126 etiquetas**, cada uma **2,5 cm (largura) × 1,5 cm (altura)**. A impressão sai exatamente nessas medidas (margens centralizadas: 1,75 cm nas laterais, 1,35 cm em cima/baixo).
- **Aproveitamento 100% de meia folha**: uma **prévia da folha** mostra as 126 posições numeradas. Você escolhe **em qual posição começar** (clicando na célula ou digitando o número) — então, numa folha já usada pela metade, é só começar na primeira etiqueta livre e não desperdiçar nenhuma. Um aviso avisa se as etiquetas não couberem a partir da posição escolhida.

## Novidades da v85 (2026-06-07) — Perfis e permissões
- **Três perfis de usuário** (definidos pelo Administrador N1 no cadastro):
  - **Administrador (a) N1** — acesso total a todas as abas, pode **editar e excluir** dados e **gerenciar usuários** (cadastrar, mudar perfil, liberar abas).
  - **Administrador (a) N2** — acesso a todas as abas e pode editar, mas **não exclui** dados de nenhuma aba, **não cadastra usuários** e **não libera abas** de vendedor.
  - **Vendedor (a)** — acessa **apenas as abas que o N1 liberar** e **não pode excluir** dados.
- **Menu sempre visível**: todas as abas aparecem no menu para todos. Ao clicar numa aba sem permissão, aparece uma tela de **acesso restrito** orientando a falar com o Administrador N1.
- **Aba Usuários por perfil**:
  - **N1** vê a gestão completa (lista, cadastrar, editar, ativar/desativar, excluir) — e o perfil de N2/Vendedor **só o N1 pode alterar**.
  - **N2 e Vendedor** veem apenas o cartão **"Alterar minha senha"** (senha atual + nova + confirmação).
- **Exclusão de dados restrita ao N1** em todas as abas (vendas, despesas, clientes, estoque, condicional, usuários...). Os botões de excluir ficam ocultos para N2 e Vendedor, e o servidor também bloqueia.
- **Login inteligente**: cada usuário cai automaticamente na primeira aba que tem acesso (evita cair numa aba bloqueada).
- Usuários antigos com perfil "admin" viram **Administrador N1** automaticamente na atualização.

## Novidades da v84 (2026-06-07)
- **Visão Geral — crediário sai do faturamento por forma**: o faturamento por forma de pagamento passa a ser o **dinheiro realmente recebido (caixa)**. Como a entrada e as parcelas do crediário entram no caixa já com a forma real (pix/dinheiro/cartão), o crediário aparece distribuído nessas formas — não há mais linha "Crediário".
- **Visão Geral — cards reposicionados**: o card **Condicional/Transferência** trocou de lugar com **Crediários em aberto**.
- **Vendas — forma da entrada do crediário**: ao registrar uma venda no crediário com entrada, agora é obrigatório informar **a forma de pagamento da entrada** (Dinheiro/Pix/Débito/Crédito/Link). Isso aplica a taxa correta no caixa e fecha o caixa certinho.
- **Estoque — foto do produto**: no cadastro de produto dá para **tirar a foto na hora (câmera do celular)** ou **escolher um arquivo**. A imagem é reduzida automaticamente e fica salva, aparecendo na ficha do produto (clique para ampliar).
- **Caixa — detalhamento das taxas**: o quadrante de **Taxas descontadas** agora detalha o desconto por **Vendas**, **Crediário (entrada)** e **Crediário (parcelas)**, no mesmo estilo do quadrante de entradas, além do detalhe por forma de cartão.
- **Condicional — período no topo**: o seletor de período foi para o **topo da tela** e agora **conecta tudo** (KPIs, gráficos, lista de abertas e histórico filtram pelo período escolhido), com atalhos Hoje/7 dias/Mês/Ano.

## Novidades da v83 (2026-06-07)
- **Nova aba Condicional & Transferências** (estilo das demais abas do ERP):
  - **Dois tipos**: **Condicional** (cliente cadastrado leva peças para provar em casa) e **Transferência** (sempre para a **CD By Carol Duarte**).
  - **Reserva de estoque automática**: ao registrar, as peças saem do *saldo disponível* e ficam marcadas como **reservadas** (aparece um selo "reserv." na tela de Estoque). Não podem ser vendidas em duplicidade.
  - **Modal de nova condicional** parecido com o de Vendas (vendedora, cliente, carrinho de peças por código), **sem forma de pagamento** nesse momento.
  - **Gerar venda em 1 clique**: na ficha da condicional você informa **quanto o cliente ficou** de cada peça; ao gerar a venda, **as peças não retiradas voltam automaticamente ao estoque** e a condicional sai da lista de abertas. A venda entra normalmente em **Vendas** e no **Caixa** (com forma de pagamento, desconto e até crediário).
  - **Devolver tudo**: encerra a condicional e devolve todas as peças ao estoque.
  - **Transferência**: botão **Confirmar transferência** (baixa definitiva do estoque, sem caixa — é movimentação interna entre lojas) ou **Devolver**.
  - **Dashboard moderno**: KPIs (valor total em aberto, em condicional, em transferência, peças reservadas), **donut Condicional × Transferência**, **ranking de quem está há mais tempo** em aberto (aging) e **maiores valores em aberto**, além de tabela de abertas e histórico filtrável por período.
  - **Integração total**: Estoque (reserva/retorno), Vendas, Caixa, Crediário (ao gerar a venda) e **Visão Geral** (novo card "Em condicional / transferência").

## Novidades da v82 (2026-06-05)
- **Crediários — dashboard moderno** (estilo da aba Vendas): KPIs no topo (total em aberto, clientes devedores, clientes em atraso, valor de parcelas em atraso) e gráficos:
  - Donut **Em dia × Em atraso** com percentual e valores.
  - **Clientes por faixa de valor em aberto** (até R$200 / R$200–500 / R$500–1.000 / acima de R$1.000) — quantidade e valor por faixa.
  - **Maiores devedores** (barras), destacando quem está em atraso.
  - **Lista de clientes em atraso**: nome, nº de parcelas vencidas, dias de atraso e valor.
- **Despesas — Fixa × Avulsa**: novo campo **Tipo** no cadastro (Fixa/Avulsa) e coluna na tabela, com gráficos:
  - Donut **Fixa × Avulsa** (percentual, valores e quantidades).
  - **% de cada categoria dentro de cada tipo** (barras para Fixa e para Avulsa).
  - **Despesas por forma de pagamento** (barras com percentual).
- Despesas existentes sem tipo definido entram como **Avulsa** por padrão (migração automática).
- **Despesas — novo lançamento passo a passo** (à prova de erro):
  1. **Tipo** (Fixa/Avulsa).
  2. **Categoria** com lista pronta (Salário, Aluguel, IPTU, Água, Luz, Imposto, Contador, MEI, Internet, Empréstimo, Holerite, Modelo, Marketing, Publicidade, Vale para funcionário, Costureira, Motoboy, Compra de Sacolas, Produto de Limpeza, Degustação, Manutenção em geral, Aquisição de equipamentos, Assinaturas, Cartão de Crédito) — dá para **rolar e escolher** ou **digitar para filtrar**; categoria nova fica **salva** para os próximos lançamentos.
  3. **Descrição** livre (opcional).
  4. **Valor total**.
  5. **Parcelamento?** Não/Sim — se Sim, escolhe **até 24x**; o sistema **calcula o valor de cada parcela** e abre os **vencimentos sugeridos a cada 30 dias (30/60/90…)**, todos **editáveis**, com conferência da soma.
  6. **Meio de pagamento**: Pix, Dinheiro, Boleto, Débito, Cartão à vista, Cartão parcelado.
  7. **De onde saiu o pagamento**: Caixa ou PIX/Banco + observação opcional.
- **Despesa parcelada vira "Contas a pagar"**: cada parcela é uma pendência com vencimento e só é **lançada como saída no caixa quando você clica em Pagar** (igual aos Crediários). A tabela mostra a situação (À vista / X de N pagas) e a origem (Caixa/PIX), e há um painel **Contas a pagar** com as parcelas pendentes/atrasadas.
- **Visão Geral coerente**: despesas contam como **saída real** — à vista na data e parcelas só quando pagas (bate com o Caixa).

## Novidades da v77 (2026-06-05)
- **Crediários — forma de pagamento ao receber**: modal agora inclui seleção da forma de pagamento (Dinheiro, Pix, Débito, Crédito à vista, Crédito parcelado com seleção de parcelas até 10x).
- **Crediários — taxas integradas ao caixa**: ao receber com débito ou crédito, a forma real é gravada no caixa, e as taxas (débito 1,59%, crédito à vista 2,06%, crédito parcelado 2,70%) são aplicadas automaticamente nos cálculos de bruto/líquido.
- **Crediários — preview de taxa**: antes de confirmar, o modal mostra a taxa %, o desconto e o valor líquido que será registrado.

## Novidades da v76 (2026-06-05)
- Crediários agrupado por cliente + accordion expandir/recolher vendas + totais compilados.

## Novidades da v75 (2026-06-05)
- **Caixa — ordenação clicável**: clique nos cabeçalhos **Data**, **Tipo**, **Forma**, **Vendedora** e **Líquido** para ordenar A→Z / Z→A ou maior→menor. Seta ↑↓ indica a direção.

## Novidades da v74 (2026-06-05)
- **Layout invertido**: topo (botão + filtros + resumo) → tabela de vendas → ranking embaixo.
- **Página 100% integrada**: ao mudar o período (De/Até), tabela + ranking + chips de resumo atualizam juntos.
- **Tabela com scroll interno**: altura fixa com barra de rolagem — a página não cresce conforme aumentam os registros.
- **Ranking sem seletor de mês**: usa o mesmo filtro de período da página.

## Novidades da v73 (2026-06-05)
- Botão "+ Nova venda" no topo, resumo do período, sticky header, busca rápida, ordenação clicável.

## Novidades da v71 (2026-06-05)
- Ranking de vendedoras moderno: cards compactos com donut de participação, ticket médio, vendas e clientes.

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

