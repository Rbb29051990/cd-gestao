# CD Gestão Empresarial — v126

## Novidades da v126 (2026-06-17) — Dashboard executivo definitivo

- **Bug corrigido:** a aba Dashboard da v123 renderizava sem estilo (sidebar/topbar quebrados, fontes erradas) porque o template **não estendia o `base.html`** — começava direto no `<style>`, sem `{% extends %}`/`{% block content %}`. Agora estende corretamente e carrega o CSS/JS do app.
- **Design moderno num só lugar:** dashboard executivo numa página única e compacta — linha de KPIs (faturamento bruto/líquido, taxas, despesas, lucro, margem com barra de saúde, ticket médio), gráficos (faturamento 12 meses, despesas fixas × avulsas, evolução do lucro, taxas por forma, top categorias), rankings (vendedoras, estoque parado, top clientes) e alertas inteligentes no rodapé.
- **Filtro de período** com atalhos Hoje/7 dias/Mês (o Mês vai do 1º ao último dia), comparando sempre com o período anterior de mesma duração.
- Limpeza de uma consulta morta no ranking de vendedoras.

## Novidades da v122 (2026-06-17) — Dashboards estratégicos

A aba **Dashboards** (antes um placeholder) agora traz 11 gráficos gerenciais + cartões de insight automáticos, com filtro de período pré-fixado no mês (1º → último dia):

1. **Resultado do período** — gráfico de **pizza** com Entradas líquidas (base da aba Caixa), Despesas fixas e Despesas avulsas; ao lado, o detalhamento da origem das entradas (por forma de pagamento) e o montante das despesas; abaixo, uma caixa destacada com o **Lucro líquido da empresa** (entradas líquidas − despesas).
2. **Tendência dos últimos 6 meses** — barras compactas de entradas líquidas, despesas fixas e avulsas por mês (com rótulos), seguidas de uma linha de lucro líquido mês a mês com rótulos.
3. **Fluxo de caixa acumulado** — saldo dia a dia no período.
4. **Top produtos · curva ABC** — por receita e margem, classificados em A/B/C (Pareto).
5. **Mix por categoria/modelo** — donut da participação na receita.
6. **Vendas por tamanho** — orienta a grade de compra.
7. **Estoque parado (aging)** — capital empatado por tempo sem venda (até 30 / 31–60 / 61–90 / +90 dias).
8. **Inadimplência do crediário** — a receber por faixa (a vencer / 1–30 / 31–60 / +60 dias) e % em atraso.
9. **Conversão de condicional** — quantas viraram venda × foram devolvidas.
10. **Desempenho por vendedora** — total, ticket médio e peças por venda.
11. **Desconto concedido × margem** — disciplina de preço.

- **Cartões de insight automáticos:** frases geradas dos próprios dados (lucro do mês, variação vs mês anterior, produto que mais fatura, estoque parado, atraso do crediário, conversão de condicional, destaque de vendas).
- **Filtro de período** igual às demais abas (De/Até + atalhos Hoje/7 dias/Mês), pré-fixado no mês corrente.
- Tudo em CSS/SVG, sem biblioteca externa, mantendo o visual do app.

## Novidades da v121 (2026-06-17) — Visão Geral: 8 quadrantes compactos e despesas fixa × avulsa

- **Menu lateral unificado:** o menu agora vem de um único arquivo compartilhado (`templates/_sidebar.html`) usado por todas as telas. Isso elimina o bug em que os ícones de algumas abas mudavam ao navegar — antes cada página tinha sua própria cópia do menu com ícones ligeiramente diferentes. O item ativo é destacado automaticamente pela URL.
- **Período do mês em todas as abas:** os filtros de data de **todas** as telas (Visão Geral, Vendas, Caixa, Ajustes, Crediários, Condicional e Despesas) agora abrem pré-preenchidos do **1º ao último dia do mês corrente**, em vez de terminar no dia de hoje.
- **Mobile/tablet da Visão Geral:** o layout de altura fixa passou a valer apenas no desktop; no celular e no tablet a tela flui naturalmente como as demais, sem destoar.

- **Cabe numa página só:** os quadrantes foram compactados e padronizados (todos do mesmo tamanho, sem espaço vazio interno), eliminando o corte do card Lucro Líquido.
- **Despesas separadas:** dois novos quadrantes mostram o montante de **Despesas fixas** e **Despesas avulsas** a pagar no período, calculados pelo **vencimento das parcelas** dentro da seleção de datas.
- **Nova ordem dos 8 quadrantes:** 1) Despesas fixas · 2) Despesas avulsas · 3) Lucro líquido · 4) Crediários em aberto · 5) Em condicional/transferência · 6) Valor de estoque · 7) Custo do estoque · 8) Potencial de venda do estoque.
- **Lucro líquido:** passa a ser Total líquido de entrada − (Despesas fixas + Despesas avulsas) do período.
- **Mobile/tablet preservado:** o layout responsivo continua empilhando os quadrantes em 2 colunas roláveis no celular e no tablet.

## Novidades da v120 (2026-06-17) — Ajustes: sidebar consistente, edição e valores líquidos

- **Sidebar consistente:** o link **Ajustes** aparece na barra lateral de todas as páginas (entre Caixa e Crediários), eliminando o salto visual ao navegar para a aba Ajustes.
- **Botão Editar:** administradores N1 e N2 podem corrigir data, tipo, descrição, forma de pagamento, valor e observação de qualquer ajuste financeiro. A entrada no caixa é atualizada junto.
- **Valor Bruto · Desc. Taxa · Líquido:** a tabela agora mostra o valor lançado (bruto), o desconto da taxa da maquininha (quando aplicável) e o valor líquido que efetivamente entra no caixa.

## Novidades da v117 (2026-06-16) — Despesas: painel de gráficos simplificado
- **Dois gráficos apenas:** a aba Despesas exibe somente **Fechamento do mês · Pagas × A pagar** e **Despesa fixa × avulsa**, lado a lado em colunas iguais, sem espaço em branco.
- **Tabelas maiores:** Contas a pagar, Contas pagas e a tabela de lançamentos cresceram proporcionalmente aproveitando o espaço liberado.

## Novidades da v116 (2026-06-16) — Pagamento de despesas e fechamento operacional
- **Contas a pagar e contas pagas lado a lado:** a área financeira da aba Despesas agora mostra o que ainda falta pagar e o que já foi pago no período selecionado.
- **Descrição visível nas listas:** abaixo da categoria aparece a descrição da despesa, facilitando identificar rapidamente aluguel, compras, fornecedores e referências do mês.
- **Pagamento com data real:** ao clicar em **Pagar**, abre um modal para informar a data em que a despesa foi paga.
- **Forma de pagamento no momento correto:** Pix, dinheiro, boleto, débito ou cartão agora são informados apenas na quitação da despesa, não no cadastro inicial.
- **Cadastro de despesa mais rápido:** o lançamento cria a obrigação; a data real, forma e observação entram somente no pagamento.
- **Caixa mais confiável:** a saída no caixa usa a data e a forma informadas no momento do pagamento.

## Novidades da v115 (2026-06-16) — Despesas por vencimento e valor da parcela
- **Gráficos corrigidos por período:** os indicadores da aba **Despesas** agora consideram somente as parcelas com **data de vencimento dentro do período selecionado**.
- **Valor correto em despesas parceladas:** uma despesa parcelada passa a entrar no mês pelo **valor da parcela**, e não pelo valor total da despesa. Ex.: empréstimo de 18x R$ 750 aparece no mês como **R$ 750**, não como R$ 13.500.
- **Despesa Fixa × Avulsa corrigida:** o gráfico passa a somar as parcelas vencidas no período, separando corretamente fixa e avulsa.
- **Contas a pagar corrigidas:** a tabela **Contas a pagar — parcelas pendentes** mostra somente parcelas pendentes com vencimento dentro do período filtrado.
- **Fechamento mensal mais confiável:** total do período, pagas e a pagar passam a representar o que realmente vence no mês selecionado.

## Novidades da v114 (2026-06-16) — Filtro mensal completo
- **Atalho Mês corrigido em todas as abas com filtro por período**: agora o botão **Mês** seleciona automaticamente do **primeiro dia ao último dia do mês atual**, e não apenas até a data de hoje.
- Aplicado em **Visão Geral, Vendas, Caixa, Crediários, Condicionais e Despesas**.
- Mantidas todas as melhorias da v113 de despesas recorrentes e fechamento mensal.

## Novidades da v113 (2026-06-16) — Despesas recorrentes e fechamento mensal
- **Despesas recorrentes**: ao lançar uma despesa fixa **sem parcelamento**, agora é possível marcar como **recorrente**.
- **Geração automática para 12 meses**: o sistema cria 12 contas a pagar mensais em aberto, usando o vencimento informado como base.
- **Valores variáveis por mês**: cada lançamento futuro pode ser editado individualmente antes do pagamento, permitindo ajustar água, luz, salário, holerite, aluguel etc.
- **Parcelamento não é recorrência**: quando a despesa tem parcelamento, o campo de recorrência é ocultado e o sistema mantém o fluxo de parcelas com vencimentos definidos.
- **Fechamento mensal**: novo gráfico verde/vermelho mostra despesas **pagas × a pagar** dentro do período filtrado, com valores ao lado. Quando todas forem pagas, o gráfico fica 100% verde.

## Novidades da v112 (2026-06-16) — Despesas
- **Período por vencimento:** o filtro De/Até agora seleciona as despesas que **vencem** no intervalo (antes era pela data de lançamento). A tabela, o total e todos os gráficos passam a refletir exatamente o período escolhido.
- **3 pizzas Fixa × Avulsa:** o antigo gráfico "Por forma de pagamento" foi substituído por **3 pizzas pequenas**, uma para cada um dos **3 meses anteriores ao mês atual**. Cada pizza mostra quanto foi gasto em despesa **Fixa** (azul) × **Avulsa** (laranja) naquele mês, com os valores ao lado. Esses 3 gráficos são sempre os 3 meses anteriores — não dependem do período selecionado — para comparar a evolução.

## v111 (2026-06-16)
- **Etiquetas corrigidas:** o **preço** voltou a sair na impressão. Ele não aparecia porque o conteúdo (4 linhas) estourava a altura da etiqueta (1,5 cm) e o preço, na última linha, era cortado. Agora a etiqueta usa **3 linhas** — código / modelo · tamanho / preço — com as **informações em azul, centralizadas** e o **preço maior e mais legível**.

## v110 (2026-06-16)
- **Editar despesa lançada:** cada despesa na tabela agora tem um botão ✏️ (ao lado do excluir), liberado para **Administradores N1 e N2**. Abre um modal para corrigir categoria, descrição, tipo, forma de pagamento e origem. **Valor e vencimento** podem ser editados enquanto a despesa for uma conta a pagar ainda em aberto; em despesas já pagas ou parceladas, esses dois campos ficam bloqueados (para não desencontrar com as parcelas e o caixa), mas os demais continuam editáveis. Se a forma de pagamento mudar, os lançamentos já feitos no caixa para essa despesa são atualizados junto.

## v109 (2026-06-16)
- **Despesa sem campo de data:** removido o campo "Data do lançamento" do cadastro de nova despesa. A data agora é automática — a despesa é registrada com a data de hoje. (O campo de **Data de vencimento**, quando não há parcelamento, continua existindo.)

## v108 (2026-06-16) — Vendas no líquido
- **Taxa do cartão e Valor líquido na tabela:** cada venda agora mostra a taxa da maquininha descontada e o **valor líquido** (bruto − desconto − taxa) — o que de fato entra na conta. Usa o mesmo cálculo do Caixa (taxa vigente na data da venda), então os números batem entre as telas.
- **Total e ticket médio líquidos:** os cards do topo (Total período e Ticket médio) passam a refletir o líquido do período.
- **Ranking por líquido + donut de 3 cores:** o ranking de vendedores agora ordena pelo valor líquido, e o gráfico de cada vendedor mostra a composição da venda em 3 fatias — 🟢 Líquido, 🟠 Desconto, 🔴 Taxa — somando o bruto, com o líquido total ao lado.

## v107 (2026-06-16)
- **Tabela de Clientes padronizada:** o botão do WhatsApp agora fica sempre **abaixo** do telefone, e o GPS sempre **abaixo** do endereço. Antes, dependendo do tamanho do conteúdo, eles apareciam ora ao lado, ora embaixo, deixando a tabela desalinhada.

## v106 (2026-06-16) — ajustes de celular
- **Valores em R$ na mesma linha:** na Visão Geral (Controle de Entradas), o símbolo e o número não quebram mais em duas linhas no celular.
- **Crediários com data pré-fixada:** o filtro De/Até já abre preenchido com o mês vigente (1º dia → hoje), igual às outras abas. O botão "Todos" continua mostrando todos os crediários.
- **Menu acompanha a aba ativa:** no celular, a barra de menu superior agora rola automaticamente até deixar visível a aba em que você está (ex.: Taxas).

## v105 (2026-06-15)
- **Botão de exclusão do Caixa removido:** era um recurso temporário (v102/v103) para limpar lançamentos órfãos. Com a limpeza feita, o botão foi retirado — o Caixa volta a ser apenas um espelho automático das vendas, crediários e despesas, sem exclusão manual. A rota interna correspondente também foi removida.

## v104 (2026-06-15)
- **Ordenamento em todas as tabelas:** agora **todas as colunas de todas as abas** podem ser clicadas para ordenar (crescente/decrescente), com o ícone ↕ no cabeçalho — igual ao que já existia em Vendas. O sistema detecta automaticamente datas (dd/mm/aaaa), valores em R$, porcentagens, códigos e texto. Implementado de forma central no `base.html`, então vale para qualquer tabela, inclusive as futuras.

## v103 (2026-06-15)
- **Correção da aba Caixa:** a página dava "Erro interno" porque o texto de confirmação do botão de exclusão (v102) tinha aspas que quebravam a renderização. Corrigido — o Caixa abre normalmente e o botão 🗑️ funciona.
- *Observação:* o botão de exclusão no Caixa é temporário (para limpeza de órfãos). Será removido em uma versão futura, já que o Caixa é um espelho e não a origem do dado.

## v102 (2026-06-15)
- **Excluir lançamento do Caixa (Admin N1):** cada linha da lista de movimentações do Caixa tem um botão 🗑️ visível apenas para o Administrador N1. Serve para remover registros órfãos que tenham sobrado. A ação pede confirmação e avisa que, se o lançamento pertencer a uma venda ainda existente, o Caixa ficará diferente da venda.

## v101 (2026-06-15)
- **Excluir venda agora limpa o Caixa por completo:** os recebimentos de parcela de crediário (gravados por `crediario_id`, sem `venda_id`) ficavam órfãos no Caixa ao excluir a venda. Agora são removidos junto com a venda, com as parcelas.
- **Limpeza de órfãos ampliada:** a rota `/admin/limpar-caixa-orfaos` agora varre o Caixa por venda, crediário e despesa inexistentes, e remove parcelas órfãs — **conserta os valores que já ficaram presos no Caixa** (rode uma vez após o deploy, logado como Admin N1).

## v100 (2026-06-15)
- **Correção do código sequencial (Estoque P, Clientes C, Despesas D, Usuários F):** o número agora é gerado a partir do **maior código já cadastrado**, e não da quantidade de registros. Antes, ao excluir itens, a contagem caía e o sistema repetia um código antigo (ex.: o estoque voltava para P22). Agora a sequência sempre continua de onde parou — é seguro excluir os dados de teste em qualquer aba.
- **Renumeração de duplicados existentes:** rota `/admin/corrigir-codigos-estoque` (só Admin N1) que conserta produtos que já ficaram com código repetido.
- Inclui também as melhorias de estoque/foto da v99.1 (lightbox da foto, thumbnail na tabela, galeria liberada no avatar e na foto do produto, foto reduzida para salvar mais rápido no celular).

## v99 (2026-06-13)
- **Data de nascimento com máscara:** campo virou texto `DD/MM/AAAA` — o usuário digita direto e as barras aparecem automaticamente. Funciona no cadastro e na edição de cliente.
- **Estoque — novo tamanho sem sair do cadastro:** ao adicionar um tamanho que não existe, o sistema salva via AJAX, já seleciona o novo tamanho no formulário e mantém o modal de cadastro de produto aberto com todos os dados preenchidos.

## v98 (2026-06-09) — Reorganização interna do código (sem mudança de comportamento)
- **`app.py` dividido em módulos** para manutenção mais fácil e rápida. O comportamento é **idêntico ao da v97** — nenhuma tela, rota ou regra mudou.
- **Nova estrutura:**
  - `config.py` — variáveis de ambiente, fuso horário e identidade visual.
  - `db.py` — pool de conexões PostgreSQL e helpers de conexão/cursor.
  - `utils.py` — funções compartilhadas (valores BRL, taxas/líquido, auditoria, baixa de estoque).
  - `auth.py` — perfis, permissões, controle de acesso por aba e contexto de template.
  - `db_init.py` — criação de tabelas, migrações, índices e seeds.
  - `routes/` — uma área de negócio por arquivo (vendas, caixa, estoque, crediários, despesas, condicionais, clientes, usuários, dashboards, taxas, visão geral, admin).
  - `app.py` — só monta o app, registra os handlers e as rotas, e inicializa o banco.
- **Endpoints e URLs preservados**: todos os links e formulários continuam funcionando sem alteração nos templates.
- **Por que isso ajuda**: a partir de agora, uma correção em uma área (ex: Vendas) mexe só no arquivo daquela área, sem precisar abrir o arquivo gigante inteiro.

### Correções incluídas na v98
- **Editar forma de pagamento de uma venda agora reflete no Caixa e na Visão Geral.** Antes, a edição mudava só o registro da venda; o lançamento no caixa mantinha a forma antiga, então os relatórios não acompanhavam. Agora a entrada à-vista da venda no caixa é atualizada junto (as taxas de cartão são recalculadas automaticamente).
- **Corrigir a forma de pagamento de uma parcela de crediário já recebida.** Novo botão **"✏️ Forma"** ao lado das parcelas pagas: abre uma janelinha para escolher a forma correta, que atualiza o lançamento no Caixa (e a Visão Geral). O valor recebido não muda. Para isso, o caixa passou a registrar de qual parcela veio cada recebimento (coluna `parcela_id`); pagamentos antigos são corrigidos pela entrada mais recente daquele crediário.

# CD Gestão Empresarial — v97

## Novidades da v97 (2026-06-08) — Segurança, Auditoria e Estoque Seguro
- **Rotas de desenvolvimento protegidas**: `/setup` e `/reset-usuarios` ficam bloqueadas em produção, salvo liberação temporária via variável de ambiente.
- **Auditoria de ações críticas**: criado registro interno para vendas, exclusões e alterações sensíveis, com usuário, data/hora, IP e detalhes da ação.
- **Prevenção de venda duplicada de estoque**: baixa de produto em venda agora valida saldo no banco usando trava transacional (`FOR UPDATE`) antes de diminuir a quantidade.
- **Proteção contra estoque negativo**: adicionada restrição no banco para impedir saldo negativo.
- **Índices de performance**: criados índices para auditoria, estoque, vendas, caixa e parcelas de crediário.
- **Logs de segurança**: falhas de login passam a ser registradas no log da aplicação.
- **Healthcheck atualizado**: `/healthz` passa a identificar a versão v97.

## Novidades da v96 (2026-06-09) — Acabamento profissional e responsividade
- **Interface mais profissional**: cards, tabelas, modais, botões e campos receberam ajustes de acabamento, sombra, espaçamento e área de toque.
- **Mobile/tablet/notebook reforçados**: melhorias para uso em celular, tablet e notebook, com foco em navegação, leitura e interação com uma mão.
- **Tabelas largas mais seguras**: rolagem horizontal reforçada, cabeçalhos fixos e larguras mínimas para evitar cortes em vendas, caixa, crediário, despesas, estoque e condicionais.
- **Modais melhores no celular**: janelas passam a respeitar melhor a altura da tela, com botões empilhados quando necessário.
- **Login mantido limpo**: campo de senha continua com apenas o ícone de olho para mostrar/ocultar.
- **Versão técnica atualizada**: cache do CSS, `/healthz` e `/versao` atualizados para v96.

# CD Gestão Empresarial — v91.3

## Novidades da v91.3 (2026-06-09) — Ajustes mobile e login
- **Crediários no celular**: corrigido o layout dos cards de vendas dentro da ficha do cliente, evitando corte/desalinhamento dos campos **Total** e **Saldo**.
- **Login**: adicionada opção de **mostrar/ocultar senha** antes de entrar no ERP.
- Mantidas as correções de fuso horário da v91.2 e rolagem lateral da v91.1.

# CD Gestão Empresarial — v91.2

## Novidades da v91.2 (2026-06-08) — Correção de fuso horário
- **Correção do botão Hoje e períodos padrão**: o ERP agora usa o fuso `America/Sao_Paulo`, evitando que o Render/UTC mostre o dia seguinte à noite no Brasil.
- **Correção nos filtros rápidos em JavaScript**: removido uso de `toISOString()` para datas dos botões Hoje/7 dias/Mês/Ano, evitando virada indevida para o dia seguinte.
- **Banco alinhado ao fuso do ERP**: conexões PostgreSQL passam a aplicar o timezone configurado em `APP_TIMEZONE` (padrão: `America/Sao_Paulo`).

# CD Gestão Empresarial — v91.1

## Correção v91.1 (2026-06-09) — Rolagem lateral em tabelas
- **Vendas**: tabela principal da aba Vendas agora possui rolagem horizontal quando a tela é estreita.
- **Condicional**: tabelas **Em aberto** e **Histórico (finalizadas/devolvidas)** agora possuem rolagem horizontal em celular, tablet e notebook.
- Ajustado `overflow-x` e largura mínima das tabelas para evitar corte de colunas e botões de ação.

# CD Gestão Empresarial — v91

## Novidades da v91 (2026-06-09) — Estabilidade, segurança e crescimento
- **Arquitetura preparada para crescimento**: adicionada base técnica para evolução modular, com documentação de arquitetura e separação conceitual por rotas, serviços, banco e utilitários.
- **Segurança de deploy reforçada**: `SECRET_KEY` e `DATABASE_URL` passam a ser obrigatórios em produção; endpoints sensíveis de setup/reset ficam bloqueados por padrão.
- **Banco mais estável**: conexão com PostgreSQL passa a usar pool configurável (`DB_POOL_MAX`) e índices foram adicionados para acelerar dashboards, filtros por período, estoque, vendas, caixa, despesas, crediários e condicionais.
- **Healthcheck para deploy**: nova rota `/healthz` para validar se o app e o banco estão respondendo.
- **Responsividade reforçada**: CSS extra para reduzir quebras em celular, tablet e notebook, com tabelas rolando horizontalmente, menu superior no mobile e modais mais seguros em telas pequenas.
- **Uploads mais protegidos**: limite global de requisição adicionado para evitar imagens ou formulários grandes demais.
- **Headers de segurança**: adicionados `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` e `Permissions-Policy`.
- **Cache do CSS atualizado**: `base.html` aponta para a versão visual `v91`, evitando que o navegador mantenha CSS antigo após o deploy.


## Novidades da v95 (2026-06-08) — Login
- **Login — mostrar/ocultar senha simplificado**: removido o ícone do macaquinho. Agora o botão usa apenas o ícone de olho.
- Ao clicar no olho, a senha fica visível; ao clicar novamente, a senha volta a ficar oculta.
- Ajuste aplicado mantendo compatibilidade com celular, tablet e notebook.

## Novidades da v90 (2026-06-09) — Responsivo (celular, tablet e notebook)
- **Layout corrigido para todos os dispositivos**: o mesmo design funciona em **notebook, tablet e celular**, ajustando-se automaticamente ao tamanho da tela.
- **Visão Geral (e demais abas) deixaram de cortar o conteúdo**: havia uma trava de altura (`100vh`) que impedia a página de rolar no celular. Agora a página **rola normalmente** e os cards empilham em coluna única quando a tela é estreita.
- Celular/tablet: menu vira **barra superior rolável**, grids/formulários em **1 coluna**, tabelas largas **rolam na horizontal**, modais ocupam a tela. Notebook: layout completo, como antes.

## Novidades da v89 (2026-06-08)
- **Despesas — erro corrigido**: ao marcar despesa (fixa ou avulsa) **sem preencher a descrição**, dava erro de banco. A descrição agora é realmente opcional.
- **Despesas — vencimento sem parcelamento**: ao escolher **"Não" no parcelamento**, aparece o campo **Data de vencimento**. A despesa entra como **conta a pagar** e **só sai do caixa quando você marca como paga** — útil para contas fixas com vencimento.
- **Condicional / Transferência**: ao finalizar uma **transferência**, o **crediário** também aparece como forma de pagamento.
- **Responsivo (celular e tablet)**: no celular/tablet o **menu lateral vira uma barra superior rolável**, formulários/grids ficam em coluna única, tabelas rolam na horizontal e modais ocupam a tela — sem ficar desconfigurado.
- **Caixa — quadrantes mais justos**: os cards de totais ficaram **mais compactos na altura**.

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



## V126 — Dashboard conforme layout aprovado

- Dashboard reorganizado conforme imagem de referência aprovada.
- Linha 1 com 7 KPIs compactos.
- Linha 2 com Faturamento Bruto/Líquido, Despesas/Lucro, Taxas e Top 5 Categorias.
- Linha 3 com Ranking de Vendedoras, Estoque Parado e Top 5 Clientes.
- Ranking de Vendedoras usa venda líquida e quantidade vendida.
- Top 5 Clientes inclui valor líquido, peças, ticket médio e última compra.
- Ajustes de altura, espaçamento e proporção para reduzir rolagem.
