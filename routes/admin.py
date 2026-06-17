"""Rotas administrativas/utilitárias: setup (criação de tabelas), reset de
usuários, healthcheck, página de versão e limpeza de registros órfãos do caixa.
setup/reset ficam bloqueados em produção, salvo liberação por variável de ambiente."""
import os
from flask import jsonify
from werkzeug.security import generate_password_hash
from db import get_db, close_db
from config import is_production
from auth import login_required, pode_excluir
from db_init import init_db


def healthz():
    try:
        conn = get_db(); cur = conn.cursor(); cur.execute('SELECT 1'); cur.fetchone(); cur.close(); close_db(conn)
        return jsonify({'status': 'ok', 'version': 'v121'})
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
        # Maior número já em uso → ponto de partida dos novos códigos
        cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM 2) AS INTEGER)), 0) as m FROM estoque WHERE codigo ~ '^P[0-9]+$'")
        prox = cur.fetchone()['m'] + 1
        # Todos os itens cujo código aparece mais de uma vez, ordenados por
        # código e do mais antigo para o mais novo.
        cur.execute("""SELECT id, codigo, modelo, descricao, criado_em FROM estoque
                       WHERE codigo IN (SELECT codigo FROM estoque GROUP BY codigo HAVING COUNT(*) > 1)
                       ORDER BY codigo, criado_em, id""")
        rows = cur.fetchall()
        renomeados = []
        vistos = set()
        for r in rows:
            cod = r['codigo']
            if cod not in vistos:
                vistos.add(cod)          # mantém o mais antigo com o código original
                continue
            novo = f"P{prox}"; prox += 1
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
    Versão: <b style='color:green'>v121 — 2026-06-17</b><br>
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
