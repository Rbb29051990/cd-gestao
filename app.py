{% extends "base.html" %}
{% block content %}
<style>
.auto { background: #f0f8f2 !important; border-color: #c8e6c9 !important; }
.modal-overlay { position:fixed;inset:0;background:rgba(26,26,46,0.6);display:flex;align-items:center;justify-content:center;z-index:100;backdrop-filter:blur(4px); }
.modal { background:#fff;width:100%;max-width:640px;padding:40px;position:relative;max-height:92vh;overflow-y:auto;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.2); }
.modal-title { font-family:'Outfit',sans-serif;font-size:20px;font-weight:700;color:#1a1a2e;margin-bottom:4px; }
.modal-sub { font-size:11px;color:#aaa;letter-spacing:1px;text-transform:uppercase;margin-bottom:28px;font-weight:700; }
.modal-close { position:absolute;top:20px;right:20px;background:#f4f4f6;border:none;color:#555;width:36px;height:36px;font-size:18px;cursor:pointer;border-radius:50%;font-weight:700; }
.section-sep { font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#aaa;margin:20px 0 14px;display:flex;align-items:center;gap:10px; }
.section-sep::after { content:'';flex:1;height:1px;background:#eee; }
.form-grid { display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px; }
.form-field { display:flex;flex-direction:column;gap:6px; }
.form-field.span2 { grid-column:span 2; }
.form-label { font-size:11px;font-weight:700;color:#aaa;text-transform:uppercase;letter-spacing:1px; }
.form-input { padding:13px 14px;border:1.5px solid #e0e0e8;background:#f8f8fc;font-family:'Outfit',sans-serif;font-size:15px;color:#1a1a2e;outline:none;font-weight:500;border-radius:8px;transition:border-color 0.2s,background 0.2s;width:100%; }
.form-input:focus { border-color:#1a1a2e;background:#fff; }
.form-input::placeholder { color:#ccc; }
.form-select { padding:13px 14px;border:1.5px solid #e0e0e8;background:#f8f8fc;font-family:'Outfit',sans-serif;font-size:15px;color:#1a1a2e;outline:none;font-weight:500;border-radius:8px;width:100%;cursor:pointer; }
.form-select:focus { border-color:#1a1a2e;background:#fff; }
.form-readonly { font-size:14px;color:#2e7d32;font-weight:700;padding:13px 14px;background:#f1f8f4;border:1.5px solid #c8e6c9;border-radius:8px; }
.cep-wrap { position:relative; }
.cep-spin { position:absolute;right:14px;top:50%;transform:translateY(-50%);display:none;font-size:14px; }
.cep-hint { font-size:11px;color:#aaa;font-weight:500;margin-top:4px; }
.form-row { display:flex;align-items:center;gap:16px;padding:14px 16px;border-radius:8px;border:1.5px solid #e8e8f0;background:#f8f8fc;flex-wrap:wrap; }
.form-row-label { font-size:14px;font-weight:600;color:#333;flex:1;min-width:180px; }
.toggle-wrap { display:flex;gap:8px; }
.toggle-btn { padding:10px 22px;border:1.5px solid #ddd;font-family:'Outfit',sans-serif;font-size:13px;font-weight:700;cursor:pointer;background:#fff;color:#aaa;border-radius:6px; }
.toggle-btn.sim.active { background:#2e7d32;border-color:#2e7d32;color:#fff; }
.toggle-btn.nao.active { background:#c62828;border-color:#c62828;color:#fff; }
.modal-footer { display:flex;gap:12px;margin-top:8px;padding-top:20px;border-top:1.5px solid #eee; }
.btn-salvar { padding:14px 32px;background:#1a1a2e;color:#fff;border:none;font-family:'Outfit',sans-serif;font-size:14px;font-weight:700;cursor:pointer;border-radius:8px;box-shadow:0 4px 14px rgba(26,26,46,0.25); }
.btn-cancelar { padding:14px 24px;background:#f4f4f6;border:none;color:#888;font-family:'Outfit',sans-serif;font-size:14px;font-weight:600;cursor:pointer;border-radius:8px; }
</style>
<div class="dash-wrap">
  <div class="topbar">
    <div class="topbar-logo">
      <span class="topbar-logo-main">CD · GESTÃO</span>
      <span class="topbar-logo-sub">Empresarial</span>
    </div>
    <div class="topbar-right">
      <a href="/minha-senha" class="btn-logout">Minha senha</a>
      <span class="topbar-user">{{ nome }}</span>
      <div class="avatar">{{ nome[:2].upper() }}</div>
      <a href="/logout" class="btn-logout">Sair</a>
    </div>
  </div>
  <div class="dash-layout">
    <nav class="sidebar">
      <div class="nav-section">
        <div class="nav-label">Principal</div>
        <a href="/visao-geral" class="nav-item"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><circle cx="11" cy="11" r="8" stroke="#2e7d32" stroke-width="1.6" fill="none"/><circle cx="11" cy="11" r="3" fill="#2e7d32" opacity="0.4"/><path d="M11 3v2M11 17v2M3 11h2M17 11h2" stroke="#2e7d32" stroke-width="1.4" stroke-linecap="round"/></svg> Visão Geral</a>
        <a href="/clientes" class="nav-item active"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><circle cx="9" cy="8" r="3.5" stroke="#6a1b9a" stroke-width="1.6"/><circle cx="15" cy="9" r="2.5" stroke="#6a1b9a" stroke-width="1.4"/><path d="M3 18c0-3 2.5-5 6-5s6 2 6 5" stroke="#6a1b9a" stroke-width="1.6" stroke-linecap="round"/><path d="M15 13c2.5 0 4 1.5 4 4" stroke="#6a1b9a" stroke-width="1.4" stroke-linecap="round"/></svg> Clientes</a>
        <a href="/vendas" class="nav-item"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><path d="M3 4h1.5l2.5 9h9l2-6H7" stroke="#2e7d32" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="9" cy="17.5" r="1.5" fill="#2e7d32"/><circle cx="15" cy="17.5" r="1.5" fill="#2e7d32"/></svg> Vendas</a>
        <a href="/estoque" class="nav-item"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><rect x="3" y="8" width="16" height="11" rx="1.5" fill="none" stroke="#f9a825" stroke-width="1.6"/><path d="M7 8V6a4 4 0 018 0v2" stroke="#f9a825" stroke-width="1.6" stroke-linecap="round"/><circle cx="11" cy="13.5" r="1.5" fill="#f9a825"/></svg> Estoque</a>
      </div>
      <div class="nav-section">
        <div class="nav-label">Financeiro</div>
        <a href="#" class="nav-item"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><rect x="2" y="5" width="18" height="13" rx="2" fill="none" stroke="#2e7d32" stroke-width="1.6"/><circle cx="11" cy="11.5" r="3" fill="none" stroke="#2e7d32" stroke-width="1.5"/><circle cx="11" cy="11.5" r="1" fill="#2e7d32"/><path d="M2 8h3M17 8h3" stroke="#2e7d32" stroke-width="1.4" stroke-linecap="round"/></svg> Caixa</a>
        <a href="#" class="nav-item"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><rect x="3" y="3" width="16" height="16" rx="2" fill="none" stroke="#e65100" stroke-width="1.6"/><path d="M7 8h8M7 11h6M7 14h4" stroke="#e65100" stroke-width="1.5" stroke-linecap="round"/></svg> Despesas</a>
        <a href="#" class="nav-item"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><path d="M11 3C7 3 4 6 4 10s3 7 7 7 7-3 7-7" stroke="#c0396b" stroke-width="1.6" stroke-linecap="round"/><path d="M15 3l4 4-4 4" stroke="#c0396b" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 10h6M11 7v6" stroke="#c0396b" stroke-width="1.4" stroke-linecap="round"/></svg> Crediários</a>
      </div>
      <div class="nav-section">
        <div class="nav-label">Gestão</div>
        <a href="#" class="nav-item"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><path d="M11 11 m-8 0 a8 8 0 0 1 8-8" stroke="#1565c0" stroke-width="3" stroke-linecap="round" fill="none"/><path d="M11 11 m0-8 a8 8 0 0 1 6.9 4" stroke="#e53935" stroke-width="3" stroke-linecap="round" fill="none"/><path d="M11 11 m6.9-4 a8 8 0 0 1 0 8" stroke="#2e7d32" stroke-width="3" stroke-linecap="round" fill="none"/><path d="M11 11 m6.9 4 a8 8 0 0 1-13.8 0" stroke="#f9a825" stroke-width="3" stroke-linecap="round" fill="none"/><circle cx="11" cy="11" r="3" fill="#fff" stroke="#ddd" stroke-width="1"/></svg> Inventário</a>
        <a href="#" class="nav-item"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><polyline points="3,17 8,10 12,13 17,6 20,8" stroke="#2e7d32" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 17h16" stroke="#2e7d32" stroke-width="1.4" stroke-linecap="round"/><circle cx="20" cy="8" r="1.5" fill="#2e7d32"/></svg> Relatórios</a>
        <a href="#" class="nav-item"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><rect x="2" y="12" width="5" height="8" rx="1" fill="#1565c0"/><rect x="8.5" y="7" width="5" height="13" rx="1" fill="#e53935"/><rect x="15" y="3" width="5" height="17" rx="1" fill="#2e7d32"/><path d="M2 11 L7 6 L12 9 L20 2" stroke="#f9a825" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg> Dashboards</a>
        {% if perfil == "admin" %}<a href="/usuarios" class="nav-item"><svg class="nav-icon" viewBox="0 0 22 22" fill="none"><rect x="3" y="11" width="16" height="8" rx="1.5" fill="none" stroke="#6a1b9a" stroke-width="1.6"/><path d="M7 11V8a4 4 0 018 0v3" stroke="#6a1b9a" stroke-width="1.6" stroke-linecap="round"/><circle cx="11" cy="15" r="1.5" fill="#6a1b9a"/></svg> Usuários</a>{% endif %}
      </div>
    </nav>
    <main class="main-content">
      <a href="/clientes" class="voltar-btn">← Voltar para clientes</a>
      {% with messages = get_flashed_messages(with_categories=true) %}{% for cat, msg in messages %}<div class="flash flash-{{ cat }}">{{ msg }}</div>{% endfor %}{% endwith %}
      <div class="ficha">
        <div class="ficha-header">
          <div style="display:flex;align-items:center;gap:18px">
            <div class="ficha-avatar" style="background:{{ c.cor_avatar }}">{{ c.iniciais }}</div>
            <div>
              <div class="ficha-nome">{{ c.nome }}</div>
              <div class="ficha-cod">#CLI-{{ '%04d'|format(c.id) }}</div>
            </div>
          </div>
          <a href="/clientes/{{ c.id }}/editar" class="btn-acao">✏️ Editar cadastro</a>
        </div>
        <div class="ficha-grid">
          <div class="ficha-campo"><span class="ficha-label">Contato</span><span class="ficha-valor">{% if c.telefone %}📱 {{ c.telefone }}{% else %}—{% endif %}</span></div>
          <div class="ficha-campo"><span class="ficha-label">CPF</span><span class="ficha-valor">{% if c.cpf %}{{ c.cpf }}{% else %}—{% endif %}</span></div>
          <div class="ficha-campo"><span class="ficha-label">Data de nascimento</span><span class="ficha-valor">{% if c.data_nascimento %}🎂 {{ c.data_nascimento.strftime('%d/%m/%Y') }}{% else %}—{% endif %}</span></div>
          <div class="ficha-campo"><span class="ficha-label">CEP</span><span class="ficha-valor">{% if c.cep %}{{ c.cep }}{% else %}—{% endif %}</span></div>
          <div class="ficha-campo"><span class="ficha-label">Endereço</span><span class="ficha-valor">{% if c.logradouro %}{{ c.logradouro }}{% if c.numero %}, {{ c.numero }}{% endif %}{% if c.complemento %} — {{ c.complemento }}{% endif %}{% else %}—{% endif %}</span></div>
          <div class="ficha-campo"><span class="ficha-label">Bairro / Cidade / UF</span><span class="ficha-valor">{% if c.bairro or c.cidade %}{{ c.bairro or '' }}{% if c.cidade %} — {{ c.cidade }}{% endif %}{% if c.uf %}/{{ c.uf }}{% endif %}{% else %}—{% endif %}</span></div>
          <div class="ficha-campo"><span class="ficha-label">Crediário</span><span class="ficha-valor">{% if c.crediario %}<span class="badge badge-hab">✅ Habilitado</span>{% else %}<span class="badge badge-nao">— Não habilitado</span>{% endif %}</span></div>
          <div class="ficha-campo"><span class="ficha-label">Promoções</span><span class="ficha-valor">{% if c.promocoes %}<span class="badge badge-sim">📢 Sim</span>{% else %}<span class="badge badge-naop">🔕 Não</span>{% endif %}</span></div>
          <div class="ficha-campo"><span class="ficha-label">Cadastrado em</span><span class="ficha-valor">{{ c.criado_em.strftime('%d/%m/%Y') }}</span></div>
        </div>
      </div>
    </main>
  </div>
</div>
{% endblock %}