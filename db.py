"""Acesso ao PostgreSQL: pool de conexões e helpers de conexão/cursor.
Garante o fuso horário do ERP em cada conexão (não o UTC do Render)."""
import os
import logging
from contextlib import contextmanager
from flask import g, has_request_context
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from config import DATABASE_URL

logger = logging.getLogger('cd-gestao')

if not DATABASE_URL:
    raise RuntimeError('Configure a variável de ambiente DATABASE_URL.')

DB_POOL = None


def get_pool():
    global DB_POOL
    if DB_POOL is None:
        DB_POOL = SimpleConnectionPool(
            1, int(os.environ.get('DB_POOL_MAX', '5')),
            DATABASE_URL, cursor_factory=RealDictCursor)
    return DB_POOL


def get_db():
    # Mantém compatibilidade com o código legado, mas usa pool de conexões.
    # Garante CURRENT_DATE/CURRENT_TIMESTAMP no fuso do ERP (Brasil), não no UTC do Render.
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE %s", (os.environ.get("APP_TIMEZONE", "America/Sao_Paulo"),))
    except Exception:
        logger.exception('Não foi possível ajustar o fuso horário da conexão')
    # v152: anota a conexão no pedido atual. Várias rotas (editar_estoque, excluir_estoque,
    # editar_cliente...) não fecham a conexão se der erro no meio — como o pool tem só 5,
    # 5 erros seguidos esgotavam o pool e o sistema inteiro parava ("connection pool
    # exhausted") até reiniciar. liberar_conexoes_pendentes() devolve o que sobrou.
    try:
        if has_request_context():
            g.setdefault('_db_conns', []).append(conn)
    except Exception:
        pass
    return conn


def close_db(conn):
    if not conn:
        return
    try:
        if has_request_context():
            pendentes = g.get('_db_conns')
            if pendentes is not None:
                if conn not in pendentes:
                    return   # já devolvida ao pool (fechamento duplicado) — não devolve 2x
                pendentes.remove(conn)
    except Exception:
        pass
    get_pool().putconn(conn)


def liberar_conexoes_pendentes(exc=None):
    """Registrada em app.teardown_appcontext: devolve ao pool as conexões que a rota
    pegou e não devolveu (erro no meio do caminho). putconn() já faz rollback se preciso."""
    try:
        pendentes = g.pop('_db_conns', None) or []
    except Exception:
        return
    for conn in pendentes:
        try:
            get_pool().putconn(conn)
        except Exception:
            logger.exception('Falha ao devolver conexão pendente ao pool')


@contextmanager
def db_cursor(commit=False):
    conn = get_db(); cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        logger.exception('Erro em operação de banco')
        raise
    finally:
        cur.close(); close_db(conn)
