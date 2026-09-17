from __future__ import annotations

ONBOARDING_SCRIPT = r'''
(() => {
  let active = false, stage = 'welcome', pollTimer = null, target = null;
  const userKey = () => 'lucas-onboarding-v3:' + (state?.user?.email || 'guest');
  const hasAi = () => (state?.aiClients || []).length > 0;
  const ensureUi = () => {
    if (document.getElementById('lucasCoach')) return;
    const style = document.createElement('style');
    style.textContent = `
      #lucasCoach{position:fixed;z-index:10050;width:min(360px,calc(100vw - 28px));background:#fff;color:#111827;border:1px solid #dbe2ee;border-radius:14px;box-shadow:0 18px 60px rgba(15,23,42,.28);padding:18px;display:none}
      #lucasCoach h3{margin:4px 0 8px;font-size:18px}#lucasCoach p{margin:0 0 14px;line-height:1.55;color:#526078;font-size:14px}
      #lucasCoach .coach-kicker{font-size:11px;letter-spacing:.16em;font-weight:800;color:#2563eb}#lucasCoach .coach-actions{display:flex;gap:8px;justify-content:flex-end;align-items:center;flex-wrap:wrap}
      #lucasCoach .coach-progress{margin-right:auto;color:#7c879b;font-size:12px}#lucasCoach button{border:0;border-radius:9px;padding:9px 13px;font-weight:700;cursor:pointer}
      #lucasCoach .coach-primary{background:#2563eb;color:#fff}#lucasCoach .coach-secondary{background:#eef2f7;color:#28364d}
      .lucas-coach-target{position:relative!important;z-index:10040!important;box-shadow:0 0 0 4px rgba(37,99,235,.35),0 0 0 9999px rgba(15,23,42,.58)!important;border-radius:10px!important}
      .lucas-coach-target-static{z-index:10040!important;box-shadow:0 0 0 4px rgba(37,99,235,.35),0 0 0 9999px rgba(15,23,42,.58)!important;border-radius:10px!important}
    `;
    document.head.appendChild(style);
    const coach = document.createElement('div'); coach.id='lucasCoach'; coach.setAttribute('role','dialog'); coach.setAttribute('aria-live','polite'); document.body.appendChild(coach);
  };
  const clearTarget = () => { if(target){target.classList.remove('lucas-coach-target','lucas-coach-target-static'); target=null;} };
  const stopPoll = () => { clearInterval(pollTimer); pollTimer=null; };
  const positionCoach = (el, centered=false) => {
    const c=document.getElementById('lucasCoach'); if(!c)return; c.style.display='block';
    if(centered){c.style.left='50%';c.style.top='50%';c.style.transform='translate(-50%,-50%)';return;}
    c.style.transform='none'; const r=el.getBoundingClientRect(), gap=14; let left=Math.min(window.innerWidth-c.offsetWidth-14,Math.max(14,r.left)); let top=r.bottom+gap;
    if(top+c.offsetHeight>window.innerHeight-14) top=Math.max(14,r.top-c.offsetHeight-gap); c.style.left=left+'px';c.style.top=top+'px';
  };
  const renderCoach = ({el,title,body,progress,primary,primaryAction,secondary='Not now',secondaryAction=finish}) => {
    ensureUi(); clearTarget(); const c=document.getElementById('lucasCoach');
    c.innerHTML=`<div class="coach-kicker">GETTING STARTED</div><h3>${title}</h3><p>${body}</p><div class="coach-actions"><span class="coach-progress">${progress||''}</span>${secondary?`<button class="coach-secondary" id="coachSecondary">${secondary}</button>`:''}${primary?`<button class="coach-primary" id="coachPrimary">${primary}</button>`:''}</div>`;
    if(secondary) document.getElementById('coachSecondary').onclick=secondaryAction; if(primary) document.getElementById('coachPrimary').onclick=primaryAction;
    if(el){target=el; const pos=getComputedStyle(el).position; el.classList.add(pos==='static'?'lucas-coach-target':'lucas-coach-target-static'); el.scrollIntoView({behavior:'smooth',block:'center'}); setTimeout(()=>positionCoach(el),180)} else positionCoach(c,true);
  };
  const nav = id => { const btn=document.querySelector(`.nav[data-view="${id}"]`); if(window.view) window.view(id,btn); };
  const refreshState = async () => { try{ if(window.refresh) await window.refresh(); }catch(_){} sync(); };
  const startPoll = () => { stopPoll(); pollTimer=setInterval(refreshState,3500); };
  const showWelcome = () => {
    stage='welcome';
    renderCoach({title:'Welcome to Lucas',body:'Connect your AI here. Computer setup is kept out of the walkthrough and documented separately so you can open it only when needed.',progress:'1 / 2',primary:hasAi()?'Finish':'Connect AI',primaryAction:()=>{if(hasAi())finish();else showAi()},secondary:'Computer setup guide',secondaryAction:()=>{window.open('/docs/computer-node','_blank');}});
  };
  const showAi = () => {
    stage='ai'; if(hasAi()){finish();return;} nav('ai'); setTimeout(()=>{const el=document.getElementById('addAiTopBtn')||document.getElementById('addAiCardBtn'); if(!el)return setTimeout(showAi,250);
      renderCoach({el,title:'Connect your AI',body:'Click the real Add AI button and complete OAuth in your AI client. Lucas finishes this walkthrough automatically after the connection is detected.',progress:'2 / 2',secondary:'Finish later',secondaryAction:finish}); startPoll();},100);
  };
  function sync(){ if(!active)return; if(stage==='ai'&&hasAi())finish(); }
  function finish(){active=false;stopPoll();clearTarget();const c=document.getElementById('lucasCoach');if(c)c.style.display='none';try{if(state?.user)localStorage.setItem(userKey(),'1')}catch(_){}}
  function openGettingStarted(){active=true;stopPoll();showWelcome()}
  function maybeStartOnboarding(){try{if(state?.user&&!localStorage.getItem(userKey()))openGettingStarted()}catch(_){openGettingStarted()}}
  window.openGettingStarted=openGettingStarted; window.maybeStartOnboarding=maybeStartOnboarding; window.finishOnboarding=finish; window.onboardingSync=sync; window.addEventListener('resize',()=>{if(active)sync()});
})();
'''
