# CD Gestão Empresarial

Sistema white-label de gestão para lojas de moda.

## Como publicar no Render

1. Faça upload desta pasta para um repositório no GitHub
2. Acesse render.com e clique em "New Web Service"
3. Conecte seu repositório GitHub
4. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
5. Clique em "Deploy"

## Usuários padrão

| Usuário | Senha     | Perfil |
|---------|-----------|--------|
| carol   | carol123  | admin  |
| renan   | renan123  | admin  |

## Estrutura do projeto

```
cd-gestao/
├── app.py              # Aplicação principal
├── requirements.txt    # Dependências Python
├── Procfile            # Configuração Render
├── templates/
│   ├── base.html       # Template base
│   ├── login.html      # Tela de login
│   └── dashboard.html  # Dashboard principal
└── static/
    └── css/
        └── main.css    # Estilos do sistema
```
