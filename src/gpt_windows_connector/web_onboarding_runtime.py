from __future__ import annotations

ONBOARDING_SCRIPT = r'''
<script>
(() => {
  let active = false, stage = 'welcome', pollTimer = null, target = null;
  const userKey = () => 'lucas-onboarding-v2:' + (window.state?.user?.email || 'guest');
  const downloadKey = () => 'lucas-node-download-clicked:' + (window.state?.user?.email || 'guest');
  const authorizedNodes = () => (window.state?.nodes || []).filter(n => n.authorized || n.access_state === 'authorized');
  const hasAi = () => (window.state?.aiClients || []).length > 0;
  const ensureUi = () => {
    if (document.getElementById('lucasCoach')) return;
    const style = document.createElement('style');
    style.textContent = `
      #lucasCoach{position:fixed;z-index:10050;width:min(360px,calc(100vw - 28px));background:#fff;color:#111827;border:1px solid #dbe2ee;border-radius:14px;box-shadow:0 18px 60px rgba(15,23,42,.28);padding:18px;display:none}
      #lucasCoach h3{margin:4px 0 8px;font-size:18px}#lucasCoach p{margin:0 0 14px;line-height:1.55;color:#526078;font-size:14px}
      #lucasCoach .coach-kicker{font-size:11px;letter-spacing:.16em;font-weight:800;color:#2563eb}#lucasCoach .coach-actions{display:flex;gap:8px;justify-content:flex-end;align-items:center}
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
  const renderCoach = ({el,title,body,progress,primary,primaryAction,secondary='Skip',secondaryAction=finish}) => {
    ensureUi(); clearTarget(); const c=document.getElementById('lucasCoach');
    c.innerHTML=`<div class="coach-kicker">GETTING STARTED</div><h3>${title}</h3><p>${body}</p><div class="coach-actions"><span class="coach-progress">${progress||''}</span>${secondary?`<button class="coach-secondary" id="coachSecondary">${secondary}</button>`:''}${primary?`<button class="coach-primary" id="coachPrimary">${primary}</button>`:''}</div>`;
    if(secondary) document.getElementById('coachSecondary').onclick=secondaryAction; if(primary) document.getElementById('coachPrimary').onclick=primaryAction;
    if(el){target=el; const pos=getComputedStyle(el).position; el.classList.add(pos==='static'?'lucas-coach-target':'lucas-coach-target-static'); el.scrollIntoView({behavior:'smooth',block:'center'}); setTimeout(()=>positionCoach(el),180)} else positionCoach(c,true);
  };
  const nav = id => { const btn=document.querySelector(`.nav[data-view="${id}"]`); if(window.view) window.view(id,btn); };
  const refreshState = async () => { try{ if(window.refresh) await window.refresh(); }catch(_){} sync(); };
  const startPoll = () => { stopPoll(); pollTimer=setInterval(refreshState,3500); };
  const showWelcome = () => { stage='welcome'; renderCoach({title:'Welcome to Lucas',body:'Set up Lucas by doing the real actions once. Lucas will guide you on the actual controls instead of showing a slide tutorial.',progress:'1 / 4',primary:'Get started',primaryAction:()=>{ if(hasAi()) showComputer(); else showAi(); },secondary:'Not now'}); };
  const showAi = () => {
    stage='ai'; if(hasAi()){showComputer();return;} nav('ai'); setTimeout(()=>{const el=document.getElementById('addAiTopBtn')||document.getElementById('addAiCardBtn'); if(!el)return setTimeout(showAi,250);
      renderCoach({el,title:'Connect your AI',body:'Click the real Add AI button and complete an OAuth connection in your AI client. This step advances automatically when Lucas detects the connection.',progress:'2 / 4',secondary:'Skip for now',secondaryAction:showComputer}); startPoll();},100);
  };
  const markDownloaded = () => { try{localStorage.setItem(downloadKey(),'1')}catch(_){} setTimeout(showComputer,250); };
  const showComputer = () => {
    stopPoll(); stage='computer'; if(authorizedNodes().length){showPermissions();return;} nav('nodes'); setTimeout(()=>{
      const downloaded=(()=>{try{return !!localStorage.getItem(downloadKey())}catch(_){return false}})(); const download=document.getElementById('downloadNodeBtn'), connect=document.getElementById('connectComputerBtn');
      if(!downloaded && download){renderCoach({el:download,title:'Install Lucas Node',body:'Download and install Lucas Node on the computer you want AI to control. After the download starts, Lucas will guide you to the real Connect computer button.',progress:'3 / 4',secondary:'Already installed',secondaryAction:()=>{markDownloaded()},primary:'Download Node',primaryAction:()=>{download.click();markDownloaded()}});return;}
      if(connect){renderCoach({el:connect,title:'Connect your computer',body:'Click Connect computer, enter the Node ID and 8-digit Connection Code shown in Lucas Settings, then approve the request locally. Lucas advances only after an Authorized Computer is detected.',progress:'3 / 4',secondary:'Skip for now',secondaryAction:showPermissions}); startPoll();}
    },120);
  };
  const showPermissions = () => {
    stopPoll(); stage='permissions'; nav('nodes'); setTimeout(()=>{const nodes=authorizedNodes(); if(!nodes.length){finish();return;} const first=nodes[0], key=encodeURIComponent(first.node_id), row=[...document.querySelectorAll('tr[data-node-key]')].find(x=>x.dataset.nodeKey===key), viewBtn=row?.querySelector('button');
      if(!viewBtn){setTimeout(showPermissions,250);return;}
      renderCoach({el:viewBtn,title:'Review computer permissions',body:'Open the real computer details. Lucas permissions are controlled locally on that computer; review the current Access mode and use the Lucas tray Settings if you want to change foreground or sensitive-action confirmation.',progress:'4 / 4',primary:'Open computer',primaryAction:()=>{viewBtn.click();setTimeout(showPermissionDetail,250)},secondary:'Finish',secondaryAction:finish});
    },120);
  };
  const showPermissionDetail = () => { const el=document.getElementById('managePermissionText'); if(!el)return showPermissions(); renderCoach({el,title:'Access mode',body:'This is the actual permission state reported by your computer. Security settings stay local-only. Open Lucas Settings from the Windows tray to change Background / Foreground focus / Sensitive confirmation, then return here.',progress:'4 / 4',primary:'Done',primaryAction:finish,secondary:'Back',secondaryAction:showPermissions}); };
  function sync(){ if(!active)return; if(stage==='ai'&&hasAi())showComputer(); else if(stage==='computer'&&authorizedNodes().length)showPermissions(); }
  function finish(){active=false;stopPoll();clearTarget();const c=document.getElementById('lucasCoach');if(c)c.style.display='none';try{if(window.state?.user)localStorage.setItem(userKey(),'1')}catch(_){}}
  function openGettingStarted(){active=true;stopPoll();showWelcome()}
  function maybeStartOnboarding(){try{if(window.state?.user&&!localStorage.getItem(userKey()))openGettingStarted()}catch(_){openGettingStarted()}}
  window.openGettingStarted=openGettingStarted; window.maybeStartOnboarding=maybeStartOnboarding; window.finishOnboarding=finish; window.onboardingSync=sync; window.addEventListener('resize',()=>{if(active)sync()});
})();
</script>
'''
