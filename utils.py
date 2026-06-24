"""Funções utilitárias compartilhadas: conversão de valores BRL, cálculo de
taxas/líquido, taxa vigente, baixa segura de estoque, auditoria e validação de foto."""
import json
import logging
from flask import session, request
from db import get_db, close_db
from config import hoje_app

logger = logging.getLogger('cd-gestao')


def get_taxa_vigente(data=None):
    """Retorna a taxa vigente para uma data específica (ou hoje)."""
    conn = get_db(); cur = conn.cursor()
    if data is None:
        data = hoje_app()
    cur.execute("""SELECT * FROM taxas_pagamento
                   WHERE vigencia_em <= %s
                   ORDER BY vigencia_em DESC LIMIT 1""", (data,))
    row = cur.fetchone()
    cur.close(); close_db(conn)
    if row:
        return dict(row)
    base = {'credito_vista': 2.06, 'credito_parcelado': 2.70, 'debito': 1.59, 'link': 0.0, 'antecipacao': 0.0}
    for n in range(2, 11):
        base[f'credito_{n}x'] = None
    return base


def taxa_parcelado(taxa, num_parcelas=None):
    """Taxa do crédito parcelado para o nº de parcelas informado.
    Usa a taxa específica (credito_2x..credito_10x) se cadastrada; senão cai
    na taxa padrão 'credito_parcelado'."""
    if num_parcelas:
        try:
            n = int(num_parcelas)
            if n >= 2:
                v = taxa.get(f'credito_{n}x')
                if v is not None and str(v) != '':
                    return float(v)
        except (ValueError, TypeError):
            pass
    return float(taxa.get('credito_parcelado', 0) or 0)


def calcular_liquido(valor_bruto, forma_pagamento, taxa, num_parcelas=None):
    """Calcula valor líquido após taxas da operadora + antecipação.
    Para crédito parcelado, usa a taxa da parcela correspondente (se cadastrada)."""
    if not taxa:
        return valor_bruto, 0, 0
    taxa_op = 0
    fp = forma_pagamento or ''
    if fp == 'credito_vista':       taxa_op = float(taxa.get('credito_vista', 0))
    elif fp == 'credito_parcelado': taxa_op = taxa_parcelado(taxa, num_parcelas)
    elif fp == 'debito':            taxa_op = float(taxa.get('debito', 0))
    elif fp == 'link':              taxa_op = float(taxa.get('link', 0))
    taxa_ant = float(taxa.get('antecipacao', 0))
    taxa_total = taxa_op + taxa_ant
    desconto = round(valor_bruto * taxa_total / 100, 2)
    liquido = round(valor_bruto - desconto, 2)
    return liquido, desconto, taxa_total


def parse_brl(val, default=0):
    """Converte valor BRL (1.000,00) ou americano (1000.00) para float."""
    try:
        if not val:
            return default
        s = str(val).strip().replace('R$', '').replace(' ', '')
        # Formato americano: tem ponto como decimal (ex: 120.00, 1000.50)
        # Formato BRL: tem vírgula como decimal (ex: 120,00 ou 1.000,00)
        if ',' in s and '.' in s:
            # Ex: 1.000,00 → BRL
            return float(s.replace('.', '').replace(',', '.'))
        elif ',' in s:
            # Ex: 120,00 → BRL sem milhar
            return float(s.replace(',', '.'))
        else:
            # Ex: 120.00 ou 1000 → americano ou inteiro
            return float(s)
    except Exception:
        return default


def bloquear_estoque_negativo(cur, produto_id, quantidade):
    """Trava o produto na transação e baixa estoque somente se houver saldo."""
    cur.execute("SELECT id,codigo,quantidade FROM estoque WHERE id=%s FOR UPDATE", (produto_id,))
    produto = cur.fetchone()
    if not produto:
        raise ValueError(f'Produto ID {produto_id} não encontrado.')
    saldo = int(produto.get('quantidade') or 0)
    if saldo < int(quantidade):
        raise ValueError(f"Estoque insuficiente para {produto.get('codigo')}. Saldo atual: {saldo}.")
    cur.execute("UPDATE estoque SET quantidade=quantidade-%s, ultima_venda=CURRENT_DATE WHERE id=%s", (quantidade, produto_id))
    return produto


def audit_log(cur, acao, tabela=None, registro_id=None, detalhes=None):
    """Registra ações críticas sem interromper o fluxo principal se a auditoria falhar."""
    try:
        payload = detalhes
        if payload is not None and not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False, default=str)
        cur.execute("""INSERT INTO auditoria
            (usuario_id, usuario_nome, acao, tabela, registro_id, detalhes, ip, user_agent)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (session.get('uid'), session.get('nome'), acao, tabela, registro_id, payload,
             request.headers.get('X-Forwarded-For', request.remote_addr) if request else None,
             request.headers.get('User-Agent') if request else None))
    except Exception as exc:
        logger.warning('Falha ao registrar auditoria: %s', exc)


def _foto_valida(foto):
    """Valida data URI de imagem e limita o tamanho (~1.5MB de base64)."""
    if foto and foto.startswith('data:image/') and len(foto) <= 1_500_000:
        return foto
    return None
