"""Rotas administrativas/utilitárias: setup (criação de tabelas), reset de
usuários, healthcheck, página de versão e limpeza de registros órfãos do caixa.
setup/reset ficam bloqueados em produção, salvo liberação por variável de ambiente."""
import os
import re
from flask import jsonify
from werkzeug.security import generate_password_hash
from db import get_db, close_db
from config import is_production
from auth import login_required, pode_excluir
from db_init import init_db


def healthz():
    try:
        conn = get_db(); cur = conn.cursor(); cur.execute('SELECT 1'); cur.fetchone(); cur.close(); close_db(conn)
        return jsonify({'status': 'ok', 'version': 'v142'})
    except Exception as exc:
        from db import logger
        logger.exception('Healthcheck falhou')
        return jsonify({'status': 'erro', 'detail': str(exc)}), 500


def setup():
    if os.environ.get('ALLOW_SETUP') != 'true' and is_production():
        return 'Setup bloqueado em produção. Defina ALLOW_SETUP=true apenas temporariamente.', 403
    try:
        init_db()
        return "<h2 style='font-family:sans-serif;padding:40px'>SETUP OK! <a href='/'>Login</a></h2>"
    except Exception as e:
        return "<pre style='padding:20px'>ERRO: " + str(e) + "</pre>", 500


def reset_usuarios():
    if os.environ.get('ALLOW_RESET_USUARIOS') != 'true':
        return 'Reset de usuários bloqueado. Defina ALLOW_RESET_USUARIOS=true apenas temporariamente.', 403
    conn = get_db(); cur = conn.cursor()
    try:
        for cod, nome, senha in [('F1', 'Renan Barcellos', 'renan123'), ('F2', 'Carol Duarte', 'carol123')]:
            h = generate_password_hash(senha)
            perms = 'visao_geral,clientes,vendas,estoque,caixa,crediarios,despesas,usuarios,dashboards'
            cur.execute("SELECT id FROM usuarios WHERE nome=%s OR codigo=%s", (nome, cod))
            u = cur.fetchone()
            if u: cur.execute("UPDATE usuarios SET codigo=%s,senha_hash=%s,perfil='admin_n1',permissoes=%s,ativo=TRUE WHERE id=%s", (cod, h, perms, u['id']))
            else: cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes) VALUES (%s,%s,%s,'admin_n1',%s)", (cod, nome, h, perms))
        conn.commit()
        return "<h2 style='font-family:sans-serif;padding:40px'>Usuarios resetados! Renan Barcellos/renan123 Carol Duarte/carol123 <a href='/'>Login</a></h2>"
    except Exception as e:
        conn.rollback(); return "<pre>ERRO: " + str(e) + "</pre>"
    finally: cur.close(); close_db(conn)


@login_required
def limpar_caixa_orfaos():
    if not pode_excluir():
        return 'Acesso negado', 403
    conn = get_db(); cur = conn.cursor()
    try:
        # 1) Crediários cuja venda não existe mais (apaga primeiro p/ gerar órfãos no caixa abaixo)
        cur.execute("""DELETE FROM crediarios
                       WHERE venda_id IS NOT NULL
                       AND venda_id NOT IN (SELECT id FROM vendas)""")
        cred_removidos = cur.rowcount
        # 2) Caixa de vendas que não existem mais
        cur.execute("""DELETE FROM caixa
                       WHERE venda_id IS NOT NULL
                       AND venda_id NOT IN (SELECT id FROM vendas)""")
        caixa_venda = cur.rowcount
        # 3) Caixa de recebimentos de parcela cujo crediário não existe mais
        cur.execute("""DELETE FROM caixa
                       WHERE crediario_id IS NOT NULL
                       AND crediario_id NOT IN (SELECT id FROM crediarios)""")
        caixa_cred = cur.rowcount
        # 4) Caixa de despesas que não existem mais
        cur.execute("""DELETE FROM caixa
                       WHERE despesa_id IS NOT NULL
                       AND despesa_id NOT IN (SELECT id FROM despesas)""")
        caixa_desp = cur.rowcount
        # 5) Parcelas de crediário órfãs
        cur.execute("""DELETE FROM crediario_parcelas
                       WHERE crediario_id NOT IN (SELECT id FROM crediarios)""")
        parc_removidas = cur.rowcount
        # 6) Parcelas de despesa órfãs
        cur.execute("""DELETE FROM despesa_parcelas
                       WHERE despesa_id NOT IN (SELECT id FROM despesas)""")
        dparc_removidas = cur.rowcount
        conn.commit()
        total_caixa = caixa_venda + caixa_cred + caixa_desp
        return f"""<div style='font-family:monospace;padding:40px'>
        <b>✅ Limpeza concluída!</b><br><br>
        Lançamentos de caixa removidos: <b>{total_caixa}</b><br>
        &nbsp;&nbsp;• de vendas inexistentes: {caixa_venda}<br>
        &nbsp;&nbsp;• de recebimentos de crediário inexistentes: {caixa_cred}<br>
        &nbsp;&nbsp;• de despesas inexistentes: {caixa_desp}<br>
        Crediários órfãos removidos: <b>{cred_removidos}</b><br>
        Parcelas de crediário órfãs: <b>{parc_removidas}</b><br>
        Parcelas de despesa órfãs: <b>{dparc_removidas}</b><br><br>
        <a href='/caixa'>← Voltar ao Caixa</a>
        </div>"""
    except Exception as e:
        conn.rollback()
        return f'Erro: {e}', 500
    finally:
        cur.close(); close_db(conn)


@login_required
def corrigir_codigos_estoque():
    """Renumera produtos com código repetido. Mantém o item MAIS ANTIGO de cada
    código (a primeira leva cadastrada) e atribui códigos novos sequenciais
    (acima do maior já existente) aos repetidos cadastrados depois."""
    if not pode_excluir():
        return 'Acesso negado — apenas o Administrador N1.', 403
    conn = get_db(); cur = conn.cursor()
    try:
        # Todos os itens cujo código aparece mais de uma vez, ordenados por
        # código e do mais antigo para o mais novo.
        cur.execute("""SELECT id, codigo, modelo, descricao, criado_em FROM estoque
                       WHERE codigo IN (SELECT codigo FROM estoque GROUP BY codigo HAVING COUNT(*) > 1)
                       ORDER BY codigo, criado_em, id""")
        rows = cur.fetchall()
        renomeados = []
        vistos = set()
        # v142: mantém o PREFIXO original (PL/SL) do código duplicado — cada prefixo
        # tem sua própria sequência; calculado sob demanda (só quando aparece).
        prox_por_prefixo = {}
        for r in rows:
            cod = r['codigo']
            if cod not in vistos:
                vistos.add(cod)          # mantém o mais antigo com o código original
                continue
            m = re.match(r'^([A-Za-z]+)(\d+)$', cod or '')
            prefixo = m.group(1).upper() if m else 'P'
            if prefixo not in prox_por_prefixo:
                cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM %s) AS INTEGER)),0) as mx "
                            "FROM estoque WHERE codigo ~ %s", (len(prefixo) + 1, f'^{prefixo}[0-9]+$'))
                prox_por_prefixo[prefixo] = cur.fetchone()['mx'] + 1
            novo = f"{prefixo}{prox_por_prefixo[prefixo]}"; prox_por_prefixo[prefixo] += 1
            cur.execute("UPDATE estoque SET codigo=%s WHERE id=%s", (novo, r['id']))
            renomeados.append((cod, novo, r['modelo'] or '', r['descricao'] or ''))
        conn.commit()
        if not renomeados:
            corpo = "<b>✅ Nenhum código duplicado encontrado.</b> Tudo certo!"
        else:
            linhas = "".join(f"<tr><td style='padding:4px 12px;color:#c62828'>{c}</td>"
                             f"<td style='padding:4px 12px'>→</td>"
                             f"<td style='padding:4px 12px;color:#2e7d32;font-weight:700'>{n}</td>"
                             f"<td style='padding:4px 12px;color:#555'>{m} {d}</td></tr>"
                             for c, n, m, d in renomeados)
            corpo = (f"<b>✅ {len(renomeados)} item(ns) renumerado(s):</b><br><br>"
                     f"<table style='border-collapse:collapse'>{linhas}</table>")
        return f"""<div style='font-family:monospace;padding:40px'>
        {corpo}<br><br><a href='/estoque'>← Voltar ao Estoque</a>
        </div>"""
    except Exception as e:
        conn.rollback()
        return f'Erro: {e}', 500
    finally:
        cur.close(); close_db(conn)


def versao():
    return """<div style='font-family:monospace;padding:40px;font-size:18px'>
    <b>CD Gestão</b><br>
    Versão: <b style='color:green'>v142 — 2026-07-02</b><br>
    v142: Estoque — botão "📤 Exportar dados" gera um arquivo .xlsx para download com todos os produtos do período filtrado (mesmo filtro da tela: data de lançamento), incluindo código, modelo, saldo, entradas/saídas, custo, valor de venda, promoção vigente e totais do saldo (custo × venda). Cabeçalho fixo, filtro automático e colunas formatadas. ✅<br>
    v142: Consolidação de versão — pasta renumerada de v141 para v142 para manter o padrão de numeração sequencial (sem mudança funcional em relação à v141). ✅<br>
    v141: Vendas — DESCONTO agora disponível em QUALQUER forma de pagamento (antes só pix/dinheiro) — inclusive crediário, pensado para liquidações. No crediário, a entrada/saldo/parcelas passam a ser calculados sobre o valor JÁ com desconto (antes ignorava). ✅<br>
    v141: Despesas — (a) os campos de VALOR do detalhamento (editar recorrente/parcelada, aplicar-a-todos) voltaram a ter MÁSCARA de moeda ao vivo (R$ 1.234,56), sem o erro de "1370,0000,00". (b) A tabela de despesas passou a mostrar a coluna VENCIMENTO (em vez da data de lançamento) e agora é ORDENÁVEL: clique no cabeçalho (Vencimento, Valor, etc.) para ordenar e ver o que pagar primeiro. (c) Agora dá para EDITAR A DATA de uma despesa JÁ PAGA (vencimento e data de pagamento) no detalhamento — o lançamento no caixa é ajustado junto; o valor não muda. ✅<br>
    v141: Troca/Devolução — (1) a venda NÃO vira mais "Dividido" ao trocar: mantém a forma original (ex.: Pix) na lista, com uma etiqueta 🎟️ vale / ↩ troca. (2) Passa a ficar REGISTRADO o que a cliente devolveu e o que levou (com foto) — visível na ficha da venda em "Trocas / devoluções", para auditoria; o item continua voltando ao estoque normalmente. (3) Aba VALES agrupada POR CLIENTE (some a repetição de linhas do mesmo cliente); clique no cliente para expandir os vales, origem e onde foram gastos. ✅<br>
    v140: Despesas — clicar numa despesa RECORRENTE (fixa) abre o detalhamento com TODOS os meses do grupo numa única tela; dá para editar valor, vencimento, categoria/descrição/tipo/observação de uma vez, sem abrir mês a mês. Botão "➕ Adicionar vencimento" (estende a série quando ela chega ao fim) e "🗑" para excluir vencimentos em aberto (meses pagos ficam como histórico). Ao informar/alterar uma data, os vencimentos seguintes em aberto puxam automaticamente a cada 30 dias (em cascata). "Aplicar a todos os meses em aberto": um único valor e/ou reprogramar os vencimentos a partir de uma 1ª data (a cada 30 dias). Cada mês tem valor independente (não redistribui). Campos do detalhamento padronizados. Excluir a recorrente inteira pelo detalhamento remove a série (N1). Adicionar/excluir vencimentos também vale para despesas parceladas. ✅<br>
    v140: Vales (crédito da loja) — novo fluxo de USO na venda: dá para LANÇAR O CÓDIGO do vale (ex.: VL5) direto na venda para abater, além de escolher entre os vales sugeridos do cliente. Dá para COMBINAR VÁRIOS VALES na mesma compra (ex.: mãe + filha) — abatem em ordem. Mostra, por vale, quanto ABATE e quanto SOBRA de saldo; se ainda restar valor, é obrigatório informar a forma de pagamento para lançar o restante no caixa. Funciona à vista e no dividido (o alvo já vem descontado do(s) vale(s)); se cobrir 100%, finaliza sem outra forma. Não se aplica ao crediário. A aba VALES dá baixa automática (saldo reduz / vira "usado") e registra ONDE foi gasto (coluna "Gasto em (venda)") com link para a ficha da venda — dá para ver os produtos e as FOTOS da compra (rastreio/auditoria). ✅<br>
    v140: Despesas — EDITOR DE RENEGOCIAÇÃO para parceladas/conta única: ao Editar dá para mudar o VALOR TOTAL (renegociou p/ mais ou p/ menos), o Nº DE PARCELAS (regenera os campos e distribui os valores automaticamente), a 1ª data (as demais puxam +30 dias em cascata) e o valor de cada parcela (redistribui entre as outras mantendo o total). Não deixa salvar enquanto a soma das parcelas não bater com o saldo. Parcelas já pagas ficam fixas. Layout do detalhamento padronizado. ✅<br>
    v139: Pagamento dividido (split) — uma cobrança pode ser paga em VÁRIAS formas (ex.: R$50 no débito + R$50 no crédito 5x). Cada forma vira uma linha no caixa com sua própria taxa (Taxa Flex), garantindo o líquido correto no caixa, na Visão Geral e no Dashboard. Disponível em: VENDAS (à vista e entrada do crediário), CONDICIONAL→venda, e RECEBIMENTO de parcela do crediário. Também ao EDITAR (editar venda e corrigir a forma de uma parcela já recebida no crediário) — reescreve o caixa preservando a data original. Ao digitar um valor, o campo seguinte já vem com o restante; máscara R$ padronizada em todos os campos (sem erro de ponto/vírgula). ✅<br>
    v139: Dashboard — o Ranking de vendedoras agora mostra TODAS as vendedoras ativas (mesmo sem vendas), com todos os indicadores, incl. clientes cadastrados (antes ficava "Sem vendas" e escondia tudo). Administradores N1 (donos) NÃO aparecem no ranking. ✅<br>
    v139: Troca / Devolução + Vales — na ficha da venda, botão "Trocar / Devolver": marca itens que voltam ao estoque e/ou adiciona peças novas; calcula a diferença (cliente paga na forma escolhida COM taxa, ou gera um VALE de crédito quando sobra). Nova aba VALES (crédito da loja a favor do cliente, passivo na Visão Geral) — usável como pagamento numa próxima venda à vista (abate do total; a parte do vale não é caixa). ✅<br>
    v139: Despesas — clicar na linha (categoria/descrição) abre o DETALHAMENTO completo: todas as parcelas com vencimento, valor, quais estão pagas e quando (forma e observação). No "Editar" dá para RENEGOCIAR valor e vencimento das parcelas ainda EM ABERTO (parcelas pagas não mudam); o total da despesa recalcula sozinho. Ao mudar a DATA de uma parcela, as seguintes em aberto viram +30 dias em cascata; ao mudar um VALOR, a diferença redistribui igualmente entre as outras parcelas em aberto (total constante). Também dá para REPARCELAR o saldo em aberto em Nx (renegociação que virou parcelamento): divide o saldo, espaça 30 dias, apaga as parcelas em aberto e cria as novas (as pagas ficam). Saíram os botões de editar/excluir da linha (excluir agora fica dentro do detalhamento, N1). ✅<br>
    v139: Períodos padronizados — Clientes e Vales ganharam filtro de período (idêntico às outras abas). Padrão "início do ano (01/01) até hoje" em: Clientes, Estoque, Condicional, Ajustes, Crediário, Vales, Despesas e Dashboard. Mantidos no mês vigente: Visão Geral, Vendas e Caixa. (helper novo config.inicio_ano_app). Estoque também: filtro por data de lançamento reflete nos quadrantes/tabela; e editar produto permite ADICIONAR/trocar/remover a FOTO. ✅<br>
    v139: Estoque/Promoção — além do campo %, agora há um campo de VALOR (R$) com máscara da moeda; ao digitar, o % é preenchido automaticamente (prévia pelo preço médio dos selecionados). No aplicar, o R$ é convertido em % POR PRODUTO no servidor (exato mesmo com preços diferentes). ✅<br>
    v139: Visão Geral — 20 quadrantes na ordem definida: faturamento bruto por forma (dinheiro, pix, débito, créd. à vista, créd. parcelado), total bruto, TOTAL DE TAXAS (com link p/ o dashboard), faturamento líquido, líquido×bruto, despesas fixas/avulsas, lucro líquido, TOTAL EM CAIXA (saldo líquido REAL = entradas líquidas − saídas já pagas, igual à aba Caixa), crediário, condicional, valor/custo/potencial de estoque e estoque parado +30/+60 dias. Grid responsivo mantendo o padrão dos cards. ✅<br>
    v139: Ajustes — (a) card "Líquido vs bruto" da Visão Geral agora mostra a % de TAXA como número principal e o líquido no subtítulo; (b) ficha da venda mostra a FOTO de cada item, com clique para ampliar (overlay) e voltar; (c) selects do pagamento dividido passaram a usar o estilo padrão (form-input) — corrige a aparência "fora de padrão" ao editar venda / no crediário / condicional. ✅<br>
    v139: Nova venda — cadastro de cliente SEM sair da venda: ao buscar um cliente que não existe, "cadastrar aqui" abre um modal com os campos; ao salvar, o cliente já entra selecionado na venda (rota AJAX /clientes/novo-rapido). O modal tem máscaras de CPF, telefone e CEP (com busca de endereço pelo ViaCEP) e capitaliza a inicial de nome e endereços (Title Case). ✅<br>
    v139: Nova venda — busca de produto por NOME/descrição/código (não só pelo código), com lista mostrando foto, estoque e preço (igual à aba Consulta). A foto AMPLIA ao clicar e a escolha é feita por um CHECKBOX (define o produto sem risco de clicar errado). Reduz erro de vender item errado quando a etiqueta sumiu. ✅<br>
    v138: Crediário — TODO crediário com saldo em aberto agora sempre mostra o botão Receber. Antes, quando a última (ou única) parcela era recebida por um valor menor que o saldo, o restante ficava sem parcela em aberto e travava o recebimento. Agora, se sobra saldo e não há parcela aberta, o sistema cria uma automaticamente — ao abrir a aba Crediários (conserta sozinho os casos já travados), no recebimento parcial e ao Editar o crediário ✅<br>
    v137: Taxas REFEITAS (modelo Taxa Flex) — cada parcela tem sua própria taxa (1x a 12x); crédito à vista usa a taxa de 1x; crédito parcelado usa a taxa do nº de parcelas informado na venda. A ANTECIPAÇÃO virou APENAS INFORMATIVA (não entra em cálculo). Link removido. CORREÇÃO: condicional→venda e a entrada do crediário (paga no cartão parcelado) agora gravam o nº de parcelas no caixa, puxando a taxa certa (antes caíam em 2x). Tela de Taxas, simulador, venda/condicional/crediário (até 12x) e cálculo do líquido atualizados ✅<br>
    v136: Promoções — selecionar vários produtos na aba Estoque e aplicar/remover um % de desconto (o preço original não muda; volta sozinho ao remover); o desconto entra automático na venda e nos relatórios. Nova aba CONSULTA — busca por código ou descrição mostrando foto, preço original, preço promocional e estoque (ideal p/ balcão quando a etiqueta se perdeu) ✅<br>
    v135: Login "Bem-vinda" → "Bem-vindo"; subtítulo da barra superior "Empresarial" → "Gestão Empresarial" (nas duas lojas); Condicional — na Transferência a vendedora escolhe o destino entre as lojas (CD Plus Size / CD Slim) em vez do destino fixo ✅<br>
    v134: Multi-loja — a identidade (nome na barra/login) agora vem de variáveis de ambiente (LOJA_SIGLA, LOJA_NOME, LOJA_SUB, LOJA_TAGLINE), permitindo rodar o MESMO código para várias lojas, cada uma com seu nome e seu banco ✅<br>
    v134: Etiquetas — impressão de MAIS DE 126 etiquetas gera folhas extras automaticamente (126 por folha) e imprime todas de uma vez, com quebra de página; corrigido o fundo branco/cinza da pré-visualização (folha cobre as 18 linhas) ✅<br>
    v134: Taxas — data de vigência pode ser RETROATIVA (aplica as taxas a vendas de uma data passada em diante). Backfill: lançamentos de caixa antigos de crédito parcelado recebem o nº de parcelas da venda, p/ a taxa por parcela valer retroativamente também nos relatórios do caixa ✅<br>
    v133: Etiquetas — alinhamento de impressão calibrado (gap col 0,3167cm; translateY p/ centralizar na vertical sem afetar o horizontal). Dashboard — colunas centralizadas, estoque parado compacto, linha 3 reordenada, cores condicionais nos KPIs (lucro/margem vermelho-verde, ticket azul). Crediários — lançamento avulso + estornar/editar/excluir parcela + excluir crediário inteiro. Taxas — taxa por parcela no crédito parcelado (2x a 10x), aplicada no líquido de vendas/caixa/dashboard/visão geral ✅<br>
    v131: Dashboard — rótulos dos gráficos viram TOOLTIP ao passar o mouse (R$ 0,00), sem poluir; "Qtd de clientes cadastrados" passa a contar clientes que cada funcionária CADASTROU (clientes.usuario_id), independente de venda; tabelas com rolagem própria no celular (não quebram mais a tela) ✅<br>
    v130: Dashboard — gráficos por VALOR TOTAL DO MÊS; % arredondados; donut com cores definidas; Top categorias com Mark-up; Ranking de vendedoras renomeado; Top clientes sem barra ✅<br>
    v129: Dashboard — gráficos refletem o período selecionado; versões unificadas (healthz/README) ✅<br>
    v125: Dashboard executivo definitivo conforme imagem aprovada — corrigido o bug que renderizava a aba sem estilo (faltava estender o base.html); KPIs com ícones/tendência, gráficos com rótulos e eixos, donut de taxas, rankings e alertas ✅<br>
    v122: Dashboards — 11 gráficos estratégicos (resultado, tendência 6 meses, fluxo acumulado, top produtos ABC, mix, tamanhos, estoque parado, inadimplência do crediário, conversão de condicional, vendedoras, desconto × margem) + cartões de insight automáticos e filtro de período ✅<br>
    v121: Menu lateral unificado em um único arquivo compartilhado (_sidebar.html) — fim do bug em que os ícones mudavam ao trocar de aba; item ativo destacado pela URL ✅<br>
    v121: Período de TODAS as abas (Visão Geral, Vendas, Caixa, Ajustes, Crediários, Condicional, Despesas) agora abre pré-fixado do 1º ao último dia do mês ✅<br>
    v121: Visão Geral — layout de altura fixa agora é só desktop; no celular/tablet a tela flui naturalmente como as demais ✅<br>
    v121: Visão Geral — 8 quadrantes iguais compactados (cabe numa página só); despesas separadas em Fixas e Avulsas pelo vencimento no período; Lucro Líquido = entradas líquidas − (fixas + avulsas) ✅<br>
    v120: Ajustes — sidebar consistente em todas as páginas; botão Editar para admins N1/N2; colunas Valor Bruto, Desc. Taxa e Líquido na tabela ✅<br>
    v117: Despesas — painel de gráficos simplificado: apenas Fechamento do mês e Fixa × Avulsa; tabelas crescidas proporcionalmente ✅<br>
    v116: Despesas — contas a pagar e contas pagas lado a lado, pagamento com data real e forma de pagamento informada na quitação ✅<br>
    v115: Despesas — indicadores, gráfico Fixa × Avulsa e contas a pagar agora usam o valor da parcela que vence no período selecionado (não o valor total da despesa) ✅<br>
    v114: Atalho Mês corrigido em todas as abas com filtro de período: agora seleciona do primeiro ao último dia do mês ✅<br>
    v113: Despesas — recorrência mensal: uma despesa fixa sem parcelamento pode gerar 12 contas a pagar em aberto automaticamente ✅<br>
    v113: Despesas — fechamento mensal com gráfico verde/vermelho mostrando despesas pagas × a pagar dentro do período ✅<br>
    v113: Despesas — despesas parceladas continuam com início/fim e não entram como recorrentes ✅<br>
    v112: Despesas — o período agora filtra pelas contas que VENCEM no intervalo; todos os gráficos respeitam só o período ✅<br>
    v112: Despesas — o gráfico "Por forma de pagamento" foi substituído por 3 pizzas (Fixa × Avulsa) dos 3 meses anteriores ao atual ✅<br>
    v111: Etiquetas — corrigido o preço que não saía na impressão (estourava a altura da etiqueta); layout em 3 linhas (código / modelo · tamanho / preço), informações em azul e centralizadas, preço maior e mais legível ✅<br>
    v110: Despesas — agora é possível EDITAR uma despesa já lançada (botão ✏️), liberado para Administradores N1 e N2. Valor e vencimento são editáveis enquanto a conta a pagar não foi quitada ✅<br>
    v109: Despesas — removido o campo "Data do lançamento" do cadastro; a data passa a ser automática (hoje) ✅<br>
    v108: Vendas — agora a tabela mostra a Taxa do cartão e o Valor líquido (bruto − desconto − taxa) por venda; o total do período e o ticket médio também são líquidos ✅<br>
    v108: Vendas — ranking por valor líquido e donut com 3 cores (líquido, desconto e taxa), com o líquido total ao lado ✅<br>
    v107: Clientes — contato e endereço padronizados: o botão do WhatsApp fica sempre abaixo do telefone, e o GPS sempre abaixo do endereço (sem mais ficar ora do lado, ora embaixo) ✅<br>
    v106: celular — valores em R$ não quebram mais em duas linhas na Visão Geral ✅<br>
    v106: Crediários — filtro de data já vem preenchido (mês vigente até hoje), igual às outras abas (botão "Todos" mostra tudo) ✅<br>
    v106: celular — o menu superior agora rola automaticamente até a aba ativa ficar visível ✅<br>
    v105: removido o botão de exclusão de lançamento do Caixa (era temporário, só para limpeza de órfãos) — o Caixa volta a ser somente espelho das vendas/crediários/despesas ✅<br>
    v104: ordenamento universal — TODAS as colunas de TODAS as tabelas agora são clicáveis para ordenar (datas, valores, % e texto), em todas as abas ✅<br>
    v103: correção — a aba Caixa dava "Erro interno" por causa do texto de confirmação do botão de exclusão; corrigido ✅<br>
    v102: Caixa — o Administrador N1 agora pode excluir um lançamento diretamente na lista (botão 🗑️), útil para remover registros órfãos ✅<br>
    v101: CORREÇÃO — ao excluir uma venda, os recebimentos de parcela do crediário também saem do Caixa (antes ficavam órfãos). Rode /admin/limpar-caixa-orfaos uma vez para limpar os que já ficaram presos ✅<br>
    v100: CORREÇÃO do código sequencial em Estoque (P), Clientes (C), Despesas (D) e Usuários (F): agora baseado no MAIOR número já cadastrado, não na contagem. Excluir registros não faz mais o código se repetir (antes o estoque voltava para P22) ✅<br>
    v100: nova rotina de manutenção para renumerar produtos com código duplicado já existentes (/admin/corrigir-codigos-estoque, só Admin N1) ✅<br>
    v100: CORREÇÃO ao excluir uma venda — agora também remove do Caixa os recebimentos de parcela do crediário (que ficavam órfãos) e as parcelas; antes os valores continuavam aparecendo no Caixa ✅<br>
    v100: rotina de limpeza de órfãos ampliada (/admin/limpar-caixa-orfaos) — varre Caixa por venda/crediário/despesa inexistentes e parcelas órfãs ✅<br>
    v100: estoque — lightbox da foto e thumbnail na tabela; galeria liberada no avatar e na foto do produto; foto reduzida (500px/0.70) p/ salvar mais rápido no celular ✅<br>
    v99: campo data de nascimento (novo e editar cliente) virou texto com máscara DD/MM/AAAA — digita direto sem precisar do calendário do browser ✅<br>
    v99: estoque — ao adicionar tamanho novo via modal, o sistema mantém o cadastro de produto aberto e já seleciona o tamanho adicionado ✅<br>
    v99: estoque — botão "← Voltar" adicionado no rodapé do formulário de cadastro de produto ✅<br>
    v99: estoque — quantidade padrão 1 ao abrir o formulário de cadastro ✅<br>
    v99: estoque — cadastro de produto enviado via AJAX (sem navegação de página), eliminando duplicação causada pelo botão "voltar" do celular ✅<br>
    v98: reorganização interna do código (app.py dividido em módulos: config, db, utils, auth e rotas por área) — mesmo comportamento da v97, manutenção mais fácil ✅<br>
    v98: correção — editar a forma de pagamento de uma venda agora também atualiza o Caixa e a Visão Geral ✅<br>
    v98: novo — corrigir a forma de pagamento de uma parcela de crediário já recebida (botão "✏️ Forma"), refletindo no Caixa e na Visão Geral ✅<br>
    v97: segurança, auditoria, bloqueio de rotas de desenvolvimento e estoque protegido contra venda duplicada ✅<br>
    v96: acabamento profissional de interface, mobile/tablet/notebook, tabelas, modais e usabilidade ✅<br>
    Despesas: corrigido erro ao salvar sem descrição (campo agora opcional) ✅<br>
    Despesas: sem parcelamento agora pede data de vencimento e vira conta a pagar ✅<br>
    Condicional: transferência também aceita crediário como forma de pagamento ✅<br>
    Responsivo: ERP adaptado para celular e tablet (menu vira barra superior rolável) ✅<br>
    Caixa: quadrantes de totais mais compactos na altura ✅<br>
    Menu: botão "Sair" movido para o final do menu lateral (abaixo de Usuários); removido "Minha senha" do topo ✅<br>
    Avatar: clique para carregar/tirar foto de perfil (ou iniciais do nome); foto também no cadastro de novo usuário ✅<br>
    Acesso negado: removida a opção de trocar senha da caixa de aviso ✅<br>
    Usuários (N1): botões de ação padronizados (tamanho uniforme) ✅<br>
    Ortografia: "vendedora" → "Vendedor (a)" em todo o ERP ✅<br>
    Condicional: ao finalizar uma transferência também há forma de pagamento (igual condicional) ✅<br>
    Despesas: máscara do valor corrigida (caixa registradora), sem erro ao digitar ✅<br>
    Correção: perfil legado "admin" agora é reconhecido como Administrador N1 (acesso total + gestão de usuários) ✅<br>
    Estoque: "Cadastrar produto" e "Imprimir etiquetas" viraram botões dentro da tela (com voltar) ✅<br>
    Etiquetas: busca por código do produto + quantidade de etiquetas, montando uma fila ✅<br>
    Etiquetas: folha A4 retrato configurada — 7 col × 18 lin = 126 (2,5 × 1,5 cm); escolha em qual posição começar para aproveitar 100% de meia folha ✅<br>
    Usuários: 3 perfis — Administrador N1 (acesso total + exclusão + gestão de usuários), N2 (tudo, edita, mas não exclui/nem gerencia usuários) e Vendedor (abas que o N1 liberar, sem exclusão) ✅<br>
    Acesso: menu sempre visível; clicar em aba sem permissão mostra aviso de acesso restrito ✅<br>
    Usuários: vendedor/N2 só trocam a própria senha na aba; só o N1 cadastra/edita perfis e libera abas ✅<br>
    Exclusão de dados (vendas, despesas, clientes, estoque, condicional...): apenas Administrador N1 ✅<br>
    Visão Geral: faturamento por forma vem do caixa (crediário já distribuído na forma real recebida) — sem linha de crediário ✅<br>
    Visão Geral: card Condicional trocou de posição com Crediários ✅<br>
    Vendas: entrada do crediário pede a forma de pagamento (aplica taxa no caixa, se cartão) ✅<br>
    Estoque: foto do produto no cadastro (câmera no celular ou arquivo) exibida na ficha ✅<br>
    Caixa: quadrante de taxas detalha desconto por Vendas / Crediário entrada / Crediário parcelas ✅<br>
    Condicional: filtro de período no topo, conectado a KPIs, gráficos, abertas e histórico ✅<br>
    Condicional: nova aba (condicional p/ cliente e transferência p/ CD By Carol Duarte) com reserva de estoque ✅<br>
    Condicional: gerar venda selecionando o que o cliente ficou (peças não retiradas voltam ao estoque); devolução total; baixa de transferência ✅<br>
    Condicional: integração total — estoque (reserva), vendas, caixa e crediário (ao gerar venda) e Visão Geral (valor em aberto) ✅<br>
    Condicional: dashboard com KPIs, donut condicional×transferência, aging (mais tempo) e maiores valores ✅<br>
    Crediários: dashboard moderno — donut em dia × atraso, distribuição por faixa, top devedores, lista de clientes em atraso ✅<br>
    Despesas: gráficos (donut fixa/avulsa, % por categoria em cada tipo, por forma de pagamento) ✅<br>
    Despesas: novo lançamento passo a passo (tipo → categoria com lista/busca/cadastro → descrição → valor → parcelamento até 24x com vencimentos 30/60/90 editáveis → meio de pagamento → origem Caixa/PIX) ✅<br>
    Despesas: parcelas viram contas a pagar e só entram no caixa quando pagas (Visão Geral conta saída real) ✅<br>
    Despesas: filtro De/Até + atalhos (Hoje/7dias/Mês) + busca rápida ✅<br>
    Crediários: busca + filtro De/Até + accordion duplo (cliente→vendas→parcelas) ✅<br>
    Scroll fixo: Crediários, Caixa, Estoque, Clientes, Despesas (tabela não cresce) ✅<br>
    Sticky headers: Caixa, Estoque, Clientes, Despesas ✅<br>
    Crediários: forma de pagamento ao receber parcela (dinheiro/pix/débito/crédito) ✅<br>
    Crediários: taxas aplicadas automaticamente no caixa (débito/crédito) ✅<br>
    Crediários: agrupado por cliente com accordion (expandir/recolher vendas) ✅<br>
    Caixa: ordenação clicável em Data, Tipo, Forma, Vendedora e Líquido ✅<br>
    Vendas: layout invertido (topo → tabela → ranking embaixo) ✅<br>
    Vendas: filtros de período integrados — tabela + ranking + resumo sincronizados ✅<br>
    Vendas: tabela com scroll interno (altura fixa, barra de rolagem) ✅<br>
    Vendas: ranking sem seletor de mês (usa filtro de período da página) ✅<br>
    Vendas: botão no topo + resumo + busca + ordenação clicável + donut ✅<br>
    Visão Geral: layout corrigido (sidebar + conteúdo lado a lado) ✅<br>
    Visão Geral: tudo em uma página sem scroll ✅<br>
    Caixa: taxas descontadas detalhadas por forma de pagamento ✅<br>
    <br><span style='color:#888;font-size:14px'>Correções da v61 (estoque, taxas, rotas, fichas) incluídas.</span><br>
    <br><a href='/'>← Voltar</a>
    </div>"""


def register(app):
    app.add_url_rule('/healthz', 'healthz', healthz)
    app.add_url_rule('/setup', 'setup', setup)
    app.add_url_rule('/reset-usuarios', 'reset_usuarios', reset_usuarios)
    app.add_url_rule('/admin/limpar-caixa-orfaos', 'limpar_caixa_orfaos', limpar_caixa_orfaos)
    app.add_url_rule('/admin/corrigir-codigos-estoque', 'corrigir_codigos_estoque', corrigir_codigos_estoque)
    app.add_url_rule('/versao', 'versao', versao)
