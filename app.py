from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cd-gestao-2026')

# Configuração dos clientes (white-label)
CLIENTES = {
    'cdgestao': {
        'nome': 'CD Gestão Empresarial',
        'sigla': 'CD',
        'tagline': 'Elegância na gestão, precisão nos resultados.',
        'cor_primaria': '#0a0a0a',
        'cor_secundaria': '#f5f5f0',
        'cor_botao': '#0a0a0a',
        'fonte_titulo': 'Cormorant Garamond',
        'usuarios': {
            'carol': {'senha': 'carol123', 'nome': 'Carol Duarte', 'perfil': 'admin'},
            'renan': {'senha': 'renan123', 'nome': 'Renan', 'perfil': 'admin'},
        }
    }
}

def get_cliente():
    return CLIENTES.get('cdgestao')

@app.route('/')
def index():
    if 'usuario' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', cliente=get_cliente())

@app.route('/login', methods=['POST'])
def login():
    cliente = get_cliente()
    usuario = request.form.get('usuario', '').strip().lower()
    senha = request.form.get('senha', '')
    usuarios = cliente.get('usuarios', {})

    if usuario in usuarios and usuarios[usuario]['senha'] == senha:
        session['usuario'] = usuario
        session['nome'] = usuarios[usuario]['nome']
        session['perfil'] = usuarios[usuario]['perfil']
        return redirect(url_for('dashboard'))

    return render_template('login.html', cliente=cliente, erro='Usuário ou senha incorretos.')

@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        return redirect(url_for('index'))
    cliente = get_cliente()
    hoje = datetime.now().strftime('%A, %d de %B de %Y')
    return render_template('dashboard.html', cliente=cliente, hoje=hoje,
                           nome=session.get('nome'), perfil=session.get('perfil'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=False)
