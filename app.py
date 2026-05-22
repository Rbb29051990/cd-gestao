from flask import Flask
import os, psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash

app = Flask(__name__)
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@app.route('/')
def index():
    return "CD Gestao - OK"

@app.route('/setup')
def setup():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY, codigo VARCHAR(10),
            nome VARCHAR(200) NOT NULL, senha_hash VARCHAR(300),
            perfil VARCHAR(20) DEFAULT 'vendedor',
            permissoes TEXT DEFAULT 'visao_geral,clientes,vendas,estoque',
            ativo BOOLEAN DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        for cod, nome, senha in [('F1','Renan Barcellos','renan123'),('F2','Carol Duarte','carol123')]:
            cur.execute("SELECT id FROM usuarios WHERE nome=%s",(nome,))
            if not cur.fetchone():
                cur.execute("INSERT INTO usuarios (codigo,nome,senha_hash,perfil,permissoes) VALUES (%s,%s,%s,'admin','visao_geral,clientes,vendas,estoque,caixa,crediarios,despesas,usuarios,dashboards')",
                    (cod,nome,generate_password_hash(senha)))
        conn.commit()
        cur.close(); conn.close()
        return "SETUP OK! Renan Barcellos/renan123 e Carol Duarte/carol123 criados!"
    except Exception as e:
        return "ERRO: " + str(e)

if __name__ == '__main__':
    app.run(debug=False)
