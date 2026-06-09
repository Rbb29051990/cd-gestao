"""Acesso ao PostgreSQL: pool de conexões e helpers de conexão/cursor.
Garante o fuso horário do ERP em cada conexão (não o UTC do Render)."""
import os
import logging
from contextlib import contextmanager
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
    return conn


def close_db(conn):
    if conn:
        get_pool().putconn(conn)


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
