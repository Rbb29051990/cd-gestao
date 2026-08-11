"""Criação de tabelas, migrações idempotentes, índices e seeds.
Chamado uma vez no start do app (app_context) e pela rota /setup."""
import os
import logging
from werkzeug.security import generate_password_hash
from db import get_db, close_db

logger = logging.getLogger('cd-gestao')


def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10),
        nome VARCHAR(200) NOT NULL, senha_hash VARCHAR(300),
        perfil VARCHAR(20) DEFAULT 'vendedor',
        permissoes TEXT DEFAULT 'visao_geral,clientes,vendas,estoque',
        ativo BOOLEAN DEFAULT TRUE,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS clientes (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10),
        nome VARCHAR(200) NOT NULL, cpf VARCHAR(20),
        data_nascimento DATE, telefone VARCHAR(30), telefone2 VARCHAR(30),
        cep VARCHAR(10), logradouro VARCHAR(200), numero VARCHAR(20),
        complemento VARCHAR(100), bairro VARCHAR(100), cidade VARCHAR(100), uf VARCHAR(2),
        promocoes BOOLEAN DEFAULT TRUE, crediario BOOLEAN DEFAULT FALSE,
        ativo BOOLEAN DEFAULT TRUE, cor_avatar VARCHAR(10) DEFAULT '#2e7d32',
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS modelos_estoque (
        id SERIAL PRIMARY KEY, nome VARCHAR(100) UNIQUE NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS tamanhos_estoque (
        id SERIAL PRIMARY KEY, nome VARCHAR(20) UNIQUE NOT NULL)""")
    for m in ['Vestido', 'Calca', 'Blusa', 'Bolsa', 'Saia', 'Macacao', 'Conjunto', 'Short', 'Blazer']:
        cur.execute("INSERT INTO modelos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (m,))
    for t in ['PP', 'P', 'M', 'G', 'GG', 'EG', 'EGG', '38', '40', '42', '44', '46', '48', '50', '52', '54', '56', '58', '60', 'UNICO']:
        cur.execute("INSERT INTO tamanhos_estoque (nome) VALUES (%s) ON CONFLICT DO NOTHING", (t,))
    cur.execute("""CREATE TABLE IF NOT EXISTS estoque (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE NOT NULL,
        modelo VARCHAR(100), descricao TEXT, tamanho VARCHAR(20),
        quantidade INTEGER DEFAULT 1, estoque_inicial INTEGER DEFAULT 1,
        custo_unitario NUMERIC(10,2) DEFAULT 0, markup NUMERIC(10,2) DEFAULT 0,
        valor_venda NUMERIC(10,2) DEFAULT 0, margem_lucro NUMERIC(10,2) DEFAULT 0,
        ativo BOOLEAN DEFAULT TRUE, ultima_venda DATE,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS estoque_entradas (
        id SERIAL PRIMARY KEY,
        estoque_id INTEGER NOT NULL,
        quantidade INTEGER NOT NULL,
        custo_unitario NUMERIC(10,2) DEFAULT 0,
        valor_venda NUMERIC(10,2) DEFAULT 0,
        markup NUMERIC(10,2) DEFAULT 0,
        margem_lucro NUMERIC(10,2) DEFAULT 0,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS vendas (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE,
        usuario_id INTEGER, vendedora_nome VARCHAR(200),
        cliente_id INTEGER, cliente_nome VARCHAR(200),
        valor_total NUMERIC(10,2) DEFAULT 0,
        desconto NUMERIC(10,2) DEFAULT 0,
        pct_desconto NUMERIC(6,2) DEFAULT 0,
        forma_pagamento VARCHAR(50), parcelas INTEGER DEFAULT 1,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS venda_itens (
        id SERIAL PRIMARY KEY,
        venda_id INTEGER REFERENCES vendas(id) ON DELETE CASCADE,
        produto_id INTEGER, codigo_produto VARCHAR(10),
        modelo VARCHAR(100), descricao TEXT, tamanho VARCHAR(20),
        valor_unitario NUMERIC(10,2) DEFAULT 0,
        quantidade INTEGER DEFAULT 1, valor_total NUMERIC(10,2) DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS crediarios (
        id SERIAL PRIMARY KEY,
        venda_id INTEGER REFERENCES vendas(id) ON DELETE CASCADE,
        cliente_id INTEGER, cliente_nome VARCHAR(200),
        valor_total NUMERIC(10,2) DEFAULT 0, entrada NUMERIC(10,2) DEFAULT 0,
        saldo_devedor NUMERIC(10,2) DEFAULT 0, status VARCHAR(20) DEFAULT 'aberto',
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS crediario_parcelas (
        id SERIAL PRIMARY KEY,
        crediario_id INTEGER REFERENCES crediarios(id) ON DELETE CASCADE,
        numero_parcela INTEGER, data_vencimento DATE,
        valor NUMERIC(10,2) DEFAULT 0,
        pago BOOLEAN DEFAULT FALSE, data_pagamento DATE)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS taxas_pagamento (
        id SERIAL PRIMARY KEY,
        vigencia_em DATE NOT NULL DEFAULT CURRENT_DATE,
        credito_vista NUMERIC(5,2) DEFAULT 2.06,
        credito_parcelado NUMERIC(5,2) DEFAULT 2.70,
        debito NUMERIC(5,2) DEFAULT 1.59,
        link NUMERIC(5,2) DEFAULT 0.00,
        antecipacao NUMERIC(5,2) DEFAULT 0.00,
        usuario_id INTEGER,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    # Inserir taxa padrão se não existir
    cur.execute("SELECT COUNT(*) as t FROM taxas_pagamento")
    if cur.fetchone()['t'] == 0:
        cur.execute("""INSERT INTO taxas_pagamento (vigencia_em,credito_vista,credito_parcelado,debito,link,antecipacao)
                       VALUES (CURRENT_DATE,2.06,2.70,1.59,0.00,0.00)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS caixa (
        id SERIAL PRIMARY KEY, descricao TEXT,
        valor NUMERIC(10,2) DEFAULT 0, tipo VARCHAR(20) DEFAULT 'entrada',
        forma_pagamento VARCHAR(50), venda_id INTEGER, crediario_id INTEGER,
        despesa_id INTEGER, usuario_id INTEGER, vendedora_nome VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS vales (
        id SERIAL PRIMARY KEY,
        codigo VARCHAR(20) UNIQUE,
        cliente_id INTEGER,
        cliente_nome VARCHAR(200),
        valor NUMERIC(10,2) DEFAULT 0,
        saldo NUMERIC(10,2) DEFAULT 0,
        status VARCHAR(20) DEFAULT 'aberto',
        venda_origem INTEGER,
        venda_uso INTEGER,
        observacao TEXT,
        usuario_id INTEGER, usuario_nome VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        usado_em TIMESTAMP)""")
    # v140: histórico de USO dos vales (um vale pode ser usado em várias vendas / parcial).
    cur.execute("""CREATE TABLE IF NOT EXISTS vale_usos (
        id SERIAL PRIMARY KEY,
        vale_id INTEGER,
        venda_id INTEGER,
        valor NUMERIC(10,2) DEFAULT 0,
        usuario_id INTEGER, usuario_nome VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    # v141: registro de TROCAS/DEVOLUÇÕES (para auditoria — o que voltou, o que entrou,
    # diferença e vale gerado), mesmo que o item volte ao estoque e saia da venda.
    cur.execute("""CREATE TABLE IF NOT EXISTS trocas (
        id SERIAL PRIMARY KEY,
        venda_id INTEGER,
        venda_codigo VARCHAR(12),
        valor_devolvido NUMERIC(10,2) DEFAULT 0,
        valor_novos NUMERIC(10,2) DEFAULT 0,
        diferenca NUMERIC(10,2) DEFAULT 0,
        forma_pagamento VARCHAR(50),
        vale_id INTEGER, vale_codigo VARCHAR(20),
        usuario_id INTEGER, usuario_nome VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS troca_itens (
        id SERIAL PRIMARY KEY,
        troca_id INTEGER,
        direcao VARCHAR(12),            -- 'devolvido' | 'novo'
        produto_id INTEGER,
        codigo_produto VARCHAR(30),
        modelo VARCHAR(120), descricao TEXT, tamanho VARCHAR(20),
        valor_unitario NUMERIC(10,2) DEFAULT 0,
        quantidade INTEGER DEFAULT 1,
        valor_total NUMERIC(10,2) DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS ajustes_financeiros (
        id SERIAL PRIMARY KEY,
        data_ajuste DATE DEFAULT CURRENT_DATE,
        tipo_ajuste VARCHAR(40) NOT NULL,
        descricao TEXT NOT NULL,
        forma_pagamento VARCHAR(50),
        valor NUMERIC(10,2) DEFAULT 0,
        observacao TEXT,
        caixa_id INTEGER,
        usuario_id INTEGER,
        usuario_nome VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS despesas (
        id SERIAL PRIMARY KEY, codigo VARCHAR(10) UNIQUE,
        descricao TEXT NOT NULL, categoria VARCHAR(100),
        valor NUMERIC(10,2) DEFAULT 0, data_despesa DATE DEFAULT CURRENT_DATE,
        forma_pagamento VARCHAR(50), usuario_id INTEGER, usuario_nome VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS despesa_categorias (
        id SERIAL PRIMARY KEY, nome VARCHAR(120) UNIQUE NOT NULL,
        ativo BOOLEAN DEFAULT TRUE, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS despesa_parcelas (
        id SERIAL PRIMARY KEY, despesa_id INTEGER, numero INTEGER,
        valor NUMERIC(10,2) DEFAULT 0, data_vencimento DATE,
        pago BOOLEAN DEFAULT FALSE, data_pagamento DATE,
        forma_pagamento VARCHAR(50), obs_pagamento TEXT,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS condicionais (
        id SERIAL PRIMARY KEY, codigo VARCHAR(12) UNIQUE,
        tipo VARCHAR(14) DEFAULT 'condicional',
        cliente_id INTEGER, cliente_nome VARCHAR(200),
        usuario_id INTEGER, vendedora_nome VARCHAR(200),
        valor_total NUMERIC(10,2) DEFAULT 0,
        status VARCHAR(20) DEFAULT 'aberta',
        venda_id INTEGER, observacao TEXT,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finalizado_em TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS condicional_itens (
        id SERIAL PRIMARY KEY,
        condicional_id INTEGER REFERENCES condicionais(id) ON DELETE CASCADE,
        produto_id INTEGER, codigo_produto VARCHAR(10),
        modelo VARCHAR(100), descricao TEXT, tamanho VARCHAR(20),
        valor_unitario NUMERIC(10,2) DEFAULT 0,
        quantidade INTEGER DEFAULT 1,
        status VARCHAR(20) DEFAULT 'pendente')""")
    cur.execute("""CREATE TABLE IF NOT EXISTS auditoria (
        id SERIAL PRIMARY KEY,
        usuario_id INTEGER,
        usuario_nome VARCHAR(200),
        acao VARCHAR(80) NOT NULL,
        tabela VARCHAR(80),
        registro_id INTEGER,
        detalhes TEXT,
        ip VARCHAR(80),
        user_agent TEXT,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    # ── MIGRAÇÕES — adiciona colunas novas em tabelas existentes ──
    migracoes = [
        "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS usuario_id INTEGER",
        "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS usuario_nome VARCHAR(200)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_usuario_criado ON clientes (usuario_id, criado_em)",
        # v142: rastreabilidade simples da importação (sem conceito de loja — o ERP
        # unificado trata todo cliente igual, já vem tratado/deduplicado na planilha).
        # origem_id é só a referência da linha na planilha importada, pra reimportar o
        # mesmo arquivo não duplicar (índice único abaixo).
        "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS origem_codigo VARCHAR(10)",
        "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS origem_id INTEGER",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_origem_id ON clientes (origem_id) WHERE origem_id IS NOT NULL",
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS reservado INTEGER DEFAULT 0",
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS foto TEXT",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS foto TEXT",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS desconto NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS pct_desconto NUMERIC(6,2) DEFAULT 0",
        # v141: forma ORIGINAL da venda quando sofre troca/devolução (exibição mantém a forma real,
        # mas o líquido passa a vir do caixa via 'multiplo') + flag de que houve troca.
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS forma_original VARCHAR(50)",
        "ALTER TABLE vendas ADD COLUMN IF NOT EXISTS trocada BOOLEAN DEFAULT FALSE",
        "ALTER TABLE vendas ALTER COLUMN pct_desconto TYPE NUMERIC(6,2)",
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS dias_estoque INTEGER DEFAULT 0",
        # v142: tipo do produto (Acessórios/Plus Size/Slim) — define o prefixo do código
        # (ACn/PSn/SLn), sequências numéricas independentes por tipo (dá pra saber o
        # total de cada um só pelo código).
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS tipo_produto VARCHAR(12)",
        "ALTER TABLE estoque_entradas ADD COLUMN IF NOT EXISTS markup NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE estoque_entradas ADD COLUMN IF NOT EXISTS margem_lucro NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS tipo VARCHAR(10) DEFAULT 'avulsa'",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS parcelado BOOLEAN DEFAULT FALSE",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS num_parcelas INTEGER DEFAULT 1",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS local_retirada VARCHAR(20)",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS obs_retirada TEXT",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS status VARCHAR(12) DEFAULT 'pago'",
        "ALTER TABLE despesas ALTER COLUMN descricao DROP NOT NULL",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS data_vencimento DATE",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS recorrente BOOLEAN DEFAULT FALSE",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS recorrencia_grupo VARCHAR(80)",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS recorrencia_seq INTEGER",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS recorrencia_total INTEGER DEFAULT 1",
        "ALTER TABLE despesas ADD COLUMN IF NOT EXISTS recorrencia_base DATE",
        "ALTER TABLE auditoria ADD COLUMN IF NOT EXISTS ip VARCHAR(80)",
        "ALTER TABLE auditoria ADD COLUMN IF NOT EXISTS user_agent TEXT",
        "ALTER TABLE caixa ADD COLUMN IF NOT EXISTS parcela_id INTEGER",
        "ALTER TABLE ajustes_financeiros ADD COLUMN IF NOT EXISTS caixa_id INTEGER",
        "ALTER TABLE ajustes_financeiros ADD COLUMN IF NOT EXISTS usuario_nome VARCHAR(200)",
        "ALTER TABLE despesa_parcelas ADD COLUMN IF NOT EXISTS forma_pagamento VARCHAR(50)",
        "ALTER TABLE despesa_parcelas ADD COLUMN IF NOT EXISTS obs_pagamento TEXT",
        "ALTER TABLE crediarios ADD COLUMN IF NOT EXISTS observacao TEXT",
        "ALTER TABLE caixa ADD COLUMN IF NOT EXISTS parcelas INTEGER",
        "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS desconto_promo NUMERIC(5,2) DEFAULT 0",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_1x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_2x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_3x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_4x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_5x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_6x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_7x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_8x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_9x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_10x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_11x NUMERIC(5,2)",
        "ALTER TABLE taxas_pagamento ADD COLUMN IF NOT EXISTS credito_12x NUMERIC(5,2)",
        # Backfill (idempotente): preenche o nº de parcelas nos lançamentos de caixa
        # antigos de vendas no crédito parcelado, p/ a taxa por parcela valer retroativamente.
        """UPDATE caixa c SET parcelas = v.parcelas
             FROM vendas v
            WHERE c.venda_id = v.id
              AND c.forma_pagamento = 'credito_parcelado'
              AND c.parcelas IS NULL
              AND COALESCE(v.parcelas,0) >= 2""",
        "CREATE INDEX IF NOT EXISTS idx_auditoria_criado_em ON auditoria (criado_em DESC)",
        "CREATE INDEX IF NOT EXISTS idx_auditoria_tabela_registro ON auditoria (tabela, registro_id)",
        "CREATE INDEX IF NOT EXISTS idx_estoque_codigo ON estoque (codigo)",
        "CREATE INDEX IF NOT EXISTS idx_vendas_criado_em ON vendas (criado_em)",
        "CREATE INDEX IF NOT EXISTS idx_caixa_criado_em ON caixa (criado_em)",
        "CREATE INDEX IF NOT EXISTS idx_ajustes_data ON ajustes_financeiros (data_ajuste DESC)",
        "CREATE INDEX IF NOT EXISTS idx_ajustes_tipo ON ajustes_financeiros (tipo_ajuste)",
        "CREATE INDEX IF NOT EXISTS idx_crediario_parcelas_vencimento ON crediario_parcelas (data_vencimento, pago)",
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_estoque_quantidade_nao_negativa') THEN ALTER TABLE estoque ADD CONSTRAINT chk_estoque_quantidade_nao_negativa CHECK (quantidade >= 0) NOT VALID; END IF; END $$;",
    ]
    for sql in migracoes:
        try:
            cur.execute(sql)
        except Exception:
            conn.rollback()
    conn.commit()
    # ── PERFIS: converte 'admin' legado em 'admin_n1' (bloco isolado e commitado à parte) ──
    try:
        cur.execute("UPDATE usuarios SET perfil='admin_n1' WHERE perfil IN ('admin','administrador','Administrador')")
        conn.commit()
    except Exception:
        conn.rollback()
    # ── SEED de categorias de despesa (só insere o que faltar) ──
    CATEGORIAS_PADRAO = ['Salário', 'Aluguel', 'IPTU', 'Água', 'Luz', 'Imposto', 'Contador', 'MEI',
        'Internet', 'Empréstimo', 'Holerite', 'Modelo', 'Marketing', 'Publicidade',
        'Vale para funcionário', 'Costureira', 'Motoboy', 'Compra de Sacolas',
        'Produto de Limpeza', 'Degustação', 'Manutenção em geral', 'Aquisição de equipamentos',
        'Assinaturas', 'Cartão de Crédito']
    try:
        for nome in CATEGORIAS_PADRAO:
            cur.execute("INSERT INTO despesa_categorias (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING", (nome,))
        conn.commit()
    except Exception:
        conn.rollback()
    # Segurança v91: usuários padrão só são criados quando explicitamente permitido.

    # Índices v91: aceleram dashboards, filtros por período e buscas frequentes.
    indices_v91 = [
        "CREATE INDEX IF NOT EXISTS idx_caixa_tipo_criado ON caixa (tipo, criado_em)",
        "CREATE INDEX IF NOT EXISTS idx_vendas_criado ON vendas (criado_em)",
        "CREATE INDEX IF NOT EXISTS idx_vendas_cliente ON vendas (cliente_id)",
        "CREATE INDEX IF NOT EXISTS idx_estoque_codigo ON estoque (codigo)",
        "CREATE INDEX IF NOT EXISTS idx_estoque_ativo_qtd ON estoque (ativo, quantidade)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_nome ON clientes (LOWER(nome))",
        "CREATE INDEX IF NOT EXISTS idx_crediarios_status ON crediarios (status)",
        "CREATE INDEX IF NOT EXISTS idx_condicionais_status_criado ON condicionais (status, criado_em)",
        "CREATE INDEX IF NOT EXISTS idx_despesas_criado ON despesas (criado_em)",
        "CREATE INDEX IF NOT EXISTS idx_despesas_vencimento_status ON despesas (data_vencimento, status)",
        "CREATE INDEX IF NOT EXISTS idx_despesas_recorrencia ON despesas (recorrencia_grupo, recorrencia_seq)",
        "CREATE INDEX IF NOT EXISTS idx_despesa_parcelas_pago_data ON despesa_parcelas (pago, data_pagamento, data_vencimento)",
        "CREATE INDEX IF NOT EXISTS idx_vale_usos_vale ON vale_usos (vale_id)",
        "CREATE INDEX IF NOT EXISTS idx_vale_usos_venda ON vale_usos (venda_id)",
        "CREATE INDEX IF NOT EXISTS idx_trocas_venda ON trocas (venda_id)",
        "CREATE INDEX IF NOT EXISTS idx_troca_itens_troca ON troca_itens (troca_id)",
    ]
    try:
        for sql in indices_v91:
            cur.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
    if os.environ.get('SEED_DEFAULT_USERS') == 'true':
        try:
            for cod, nome, senha in [('F1', 'Renan Barcellos', 'renan123'), ('F2', 'Carol Duarte', 'carol123')]:
                cur.execute("SELECT id FROM usuarios WHERE nome=%s", (nome,))
                if not cur.fetchone():
                    perms = 'visao_geral,clientes,vendas,estoque,condicionais,caixa,crediarios,despesas,taxas,dashboards'
                    cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes) VALUES (%s,%s,%s,'admin_n1',%s)",
                        (cod, nome, generate_password_hash(senha), perms))
            conn.commit()
        except Exception as e:
            logger.exception(f"usuarios padrao: {e}"); conn.rollback()
    cur.close(); close_db(conn)
