/* Pagamento dividido (split) — componente compartilhado por Vendas, Crediário e
   Condicional. Mesma lógica em todas as telas: máscara R$ padronizada (guarda os
   centavos em dataset.cents — sem erro de ponto/vírgula) + auto-preenchimento do
   restante no campo de baixo, recalculando ao editar/adicionar formas. */

function fmtBRL(v){ return 'R$ ' + (parseFloat(v)||0).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}); }

/* Máscara monetária "R$ 1.234,56". setMoney/getMoney p/ uso por código. */
function moneyMask(el, onChange){
  function fmt(cents){
    if(!cents) return '';
    let p=(parseInt(cents,10)/100).toFixed(2).split('.');
    p[0]=p[0].replace(/\B(?=(\d{3})+(?!\d))/g,'.');
    return 'R$ '+p[0]+','+p[1];
  }
  function render(silent){ el.value=fmt(el.dataset.cents||''); if(!silent && onChange) onChange(); }
  el.addEventListener('keydown', function(e){
    if(/^[0-9]$/.test(e.key)){ e.preventDefault(); if((el.dataset.cents||'').length>=12) return; el.dataset.cents=(el.dataset.cents||'')+e.key; render(false); }
    else if(e.key==='Backspace'){ e.preventDefault(); el.dataset.cents=(el.dataset.cents||'').slice(0,-1); render(false); }
    else if(e.key==='Delete'){ e.preventDefault(); el.dataset.cents=''; render(false); }
  });
  el.setMoney=function(num){ el.dataset.cents=(num==null||isNaN(num)||num<=0)?'':String(Math.round(num*100)); render(true); };
  el.getMoney=function(){ return el.dataset.cents?parseInt(el.dataset.cents,10)/100:0; };
  el.dataset.cents=el.dataset.cents||''; render(true);
}

function criarSplitEditor(cfg){
  const rowsEl = document.getElementById(cfg.rowsId);
  function formaOptions(){ return '<option value="">Forma...</option>'
    + '<option value="dinheiro">💵 Dinheiro</option>'
    + '<option value="pix">⚡ Pix</option>'
    + '<option value="debito">💳 Débito</option>'
    + '<option value="credito_vista">💳 Crédito à vista</option>'
    + '<option value="credito_parcelado">💳 Crédito parcelado</option>'
    + '<option value="link">🔗 Link</option>'; }
  function parcOptions(){ let s='<option value="">Parc...</option>'; for(let i=2;i<=12;i++) s+='<option value="'+i+'">'+i+'x</option>'; return s; }
  function rows(){ return Array.from(rowsEl.querySelectorAll('.split-row')); }
  function getVal(row){ const i=row.querySelector('.split-valor'); return i && i.getMoney ? i.getMoney() : 0; }
  function alvo(){ return Math.round((cfg.target()||0)*100)/100; }
  function recompute(){
    let soma=0; rows().forEach(function(row){ soma+=getVal(row); });
    soma=Math.round(soma*100)/100;
    const dif=Math.round((alvo()-soma)*100)/100;
    document.getElementById(cfg.alvoId).textContent = fmtBRL(alvo());
    document.getElementById(cfg.somaId).textContent = fmtBRL(soma);
    const difEl=document.getElementById(cfg.difId);
    difEl.textContent=fmtBRL(dif);
    const ok=Math.abs(dif)<0.005 && soma>0;
    difEl.style.color=ok?'#2e7d32':'#c62828';
    const al=document.getElementById(cfg.alertaId);
    if(al) al.style.display=ok?'none':'block';
    return {soma:soma, dif:dif, ok:ok};
  }
  /* Ao editar uma linha, o campo IMEDIATAMENTE ABAIXO recebe o valor restante. */
  function autoPreencherProximo(row){
    const rr=rows(); const idx=rr.indexOf(row); const next=rr[idx+1];
    if(!next) return;
    let somaAte=0; for(let i=0;i<=idx;i++) somaAte+=getVal(rr[i]);
    const rest=Math.round((alvo()-somaAte)*100)/100;
    next.querySelector('.split-valor').setMoney(rest>0?rest:0);
  }
  function onEdit(row){ autoPreencherProximo(row); recompute(); }
  function addRow(preencherRestante){
    const row=document.createElement('div');
    row.className='split-row';
    row.style.cssText='display:flex;gap:8px;align-items:flex-end;margin-bottom:8px';
    row.innerHTML =
      '<div class="form-field" style="flex:1;margin:0"><label class="form-label">Valor</label><input class="form-input split-valor" type="text" inputmode="numeric" placeholder="R$ 0,00"></div>'
      + '<div class="form-field" style="flex:1.4;margin:0"><label class="form-label">Forma</label><select class="form-select split-forma">'+formaOptions()+'</select></div>'
      + '<div class="form-field split-parc-wrap" style="width:110px;margin:0;visibility:hidden"><label class="form-label">Parcelas</label><select class="form-select split-parc">'+parcOptions()+'</select></div>'
      + '<button type="button" class="btn-del-split" title="Remover" style="padding:9px 11px;background:#fff;color:#c62828;border:1.5px solid #fcd5d5;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer">🗑️</button>';
    rowsEl.appendChild(row);
    moneyMask(row.querySelector('.split-valor'), function(){ onEdit(row); });
    row.querySelector('.split-forma').addEventListener('change', function(){
      row.querySelector('.split-parc-wrap').style.visibility=this.value==='credito_parcelado'?'visible':'hidden';
      recompute();
    });
    row.querySelector('.split-parc').addEventListener('change', recompute);
    row.querySelector('.btn-del-split').addEventListener('click', function(){ row.remove(); recompute(); });
    if(preencherRestante){
      let soma=0; rows().forEach(function(r){ if(r!==row) soma+=getVal(r); });
      const rest=Math.round((alvo()-soma)*100)/100;
      row.querySelector('.split-valor').setMoney(rest>0?rest:0);
    }
    recompute();
  }
  document.getElementById(cfg.addBtnId).addEventListener('click', function(){ addRow(true); });
  return {
    addRow: function(){ addRow(false); },
    recompute: recompute,
    reset: function(){ rowsEl.innerHTML=''; },
    /* Pré-carrega linhas a partir de [{forma,valor,parcelas}] (ex.: ao editar). */
    load: function(arr){
      rowsEl.innerHTML='';
      (arr||[]).forEach(function(p){
        addRow(false);
        const row=rowsEl.lastElementChild;
        row.querySelector('.split-valor').setMoney(parseFloat(p.valor)||0);
        const fsel=row.querySelector('.split-forma'); fsel.value=p.forma||'';
        if(p.forma==='credito_parcelado'){ row.querySelector('.split-parc-wrap').style.visibility='visible'; row.querySelector('.split-parc').value=p.parcelas||''; }
      });
      recompute();
    },
    serialize: function(){
      const arr=[];
      rows().forEach(function(row){
        const valor=getVal(row); const forma=row.querySelector('.split-forma').value;
        if(valor>0 && forma){
          const o={forma:forma, valor:valor.toFixed(2)};
          if(forma==='credito_parcelado') o.parcelas=parseInt(row.querySelector('.split-parc').value)||null;
          arr.push(o);
        }
      });
      return arr;
    }
  };
}
