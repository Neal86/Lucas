from __future__ import annotations

ONBOARDING_SCRIPT = r'''
(() => {
  let active = false;
  const userKey = () => 'lucas-setup-checklist-v1:' + (state?.user?.email || 'guest');
  const hintKey = () => 'lucas-setup-checklist-hint-v1:' + (state?.user?.email || 'guest');
  const hasAi = () => (state?.aiClients || []).length > 0;
  const authorizedNodes = () => (state?.nodes || []).filter(n => n.authorized || n.access_state === 'authorized');
  const hasComputer = () => authorizedNodes().length > 0;
  const hasPermissions = () => hasComputer();
  const allDone = () => hasAi() && hasComputer() && hasPermissions();
  const appVisible = () => !!state?.user && document.getElementById('auth')?.classList.contains('hidden') && !document.getElementById('app')?.classList.contains('hidden');

  const ensureUi = () => {
    if (document.getElementById('lucasCoach')) return;
    document.getElementById('onboardingModal')?.classList.add('hidden');
    const style = document.createElement('style');
    style.textContent = `
      #lucasCoach{position:fixed;z-index:10050;width:min(410px,calc(100vw - 28px));background:#fff;color:#111827;border:1px solid #dbe2ee;border-radius:16px;box-shadow:0 18px 60px rgba(15,23,42,.28);padding:20px;display:none}
      #lucasCoach h3{margin:4px 0 14px;font-size:21px}#lucasCoach .coach-kicker{font-size:11px;letter-spacing:.16em;font-weight:800;color:#2563eb}
      #lucasCoach .coach-list{display:grid;gap:8px;margin:4px 0 18px}.coach-step{width:100%;display:flex;align-items:center;gap:12px;text-align:left;border:1px solid #e3e8f1;background:#fff;border-radius:11px;padding:12px 13px;cursor:pointer;font-weight:750;color:#18243a}
      .coach-step:hover{border-color:#9db8ff;background:#f7f9ff}.coach-status{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;flex:0 0 22px;font-size:13px;background:#eef2f7;color:#6a768b}.coach-step.done .coach-status{background:#dcfce7;color:#15803d}
      #lucasCoach .coach-actions{display:flex;justify-content:flex-end}.coach-close{border:0;border-radius:9px;padding:10px 16px;font-weight:800;cursor:pointer;background:#2563eb;color:#fff}
      #gettingStartedNav.lucas-reopen-target{position:relative;z-index:10040;box-shadow:0 0 0 3px rgba(37,99,235,.45)!important;background:#33445f!important}
      #coachReopenHint{position:fixed;z-index:10060;max-width:285px;background:#111827;color:#fff;border-radius:10px;padding:11px 13px;box-shadow:0 12px 34px rgba(15,23,42,.3);font-size:13px;line-height:1.45}
      #coachReopenHint button{margin-top:8px;border:0;border-radius:7px;background:#fff;color:#111827;padding:6px 9px;font-weight:750;cursor:pointer}
    `;
    document.head.appendChild(style);
    const coach = document.createElement('div');
    coach.id = 'lucasCoach';
    coach.setAttribute('role','dialog');
    coach.setAttribute('aria-modal','true');
    coach.setAttribute('aria-label','Getting Started');
    document.body.appendChild(coach);
  };

  const hideHint = () => {
    document.getElementById('coachReopenHint')?.remove();
    document.getElementById('gettingStartedNav')?.classList.remove('lucas-reopen-target');
  };

  const showReopenHint = () => {
    try { if (localStorage.getItem(hintKey())) return; localStorage.setItem(hintKey(),'1'); } catch (_) {}
    const nav = document.getElementById('gettingStartedNav');
    if (!nav || !appVisible()) return;
    hideHint();
    nav.classList.add('lucas-reopen-target');
    const hint = document.createElement('div');
    hint.id = 'coachReopenHint';
    hint.innerHTML = 'You can reopen setup guidance here anytime.<br><button type="button">Got it</button>';
    document.body.appendChild(hint);
    const place = () => {
      const r = nav.getBoundingClientRect();
      hint.style.left = Math.min(window.innerWidth - hint.offsetWidth - 12, r.right + 12) + 'px';
      hint.style.top = Math.max(12, Math.min(window.innerHeight - hint.offsetHeight - 12, r.top)) + 'px';
    };
    hint.querySelector('button').onclick = hideHint;
    place();
    setTimeout(hideHint, 9000);
  };

  const step = (label, done, target) => `<button type="button" class="coach-step ${done?'done':''}" data-target="${target}"><span class="coach-status">${done?'✓':'○'}</span><span>${label}</span></button>`;

  const renderChecklist = () => {
    if (!active || !appVisible()) return hideGettingStarted();
    ensureUi();
    const coach = document.getElementById('lucasCoach');
    coach.innerHTML = `<div class="coach-kicker">GETTING STARTED</div><h3>Setup Checklist</h3><div class="coach-list">${step('Connect your AI',hasAi(),'ai')}${step('Connect your computer',hasComputer(),'nodes')}${step('Set permissions',hasPermissions(),'nodes')}</div><div class="coach-actions"><button type="button" class="coach-close" id="coachClose">Close</button></div>`;
    coach.style.display = 'block';
    coach.style.left = '50%';
    coach.style.top = '50%';
    coach.style.transform = 'translate(-50%,-50%)';
    coach.querySelectorAll('.coach-step').forEach(btn => btn.onclick = () => {
      const id = btn.dataset.target;
      closeGettingStarted(false);
      const nav = document.querySelector(`.nav[data-view="${id}"]`);
      if (window.view) window.view(id, nav);
    });
    document.getElementById('coachClose').onclick = () => closeGettingStarted(true);
  };

  function closeGettingStarted(showHint=true) {
    active = false;
    const coach = document.getElementById('lucasCoach');
    if (coach) coach.style.display = 'none';
    try { if (state?.user) localStorage.setItem(userKey(),'1'); } catch (_) {}
    if (showHint) setTimeout(showReopenHint, 120);
  }

  function hideGettingStarted() {
    active = false;
    hideHint();
    const coach = document.getElementById('lucasCoach');
    if (coach) coach.style.display = 'none';
  }

  function openGettingStarted() {
    if (!appVisible()) return;
    hideHint();
    active = true;
    renderChecklist();
  }

  function maybeStartOnboarding() {
    if (!appVisible()) return;
    if (allDone()) return;
    try { if (localStorage.getItem(userKey())) return; } catch (_) {}
    openGettingStarted();
  }

  function sync() { if (active) renderChecklist(); }

  window.openGettingStarted = openGettingStarted;
  window.maybeStartOnboarding = maybeStartOnboarding;
  window.finishOnboarding = () => closeGettingStarted(true);
  window.hideGettingStarted = hideGettingStarted;
  window.onboardingSync = sync;
  window.addEventListener('resize', () => {
    const hint = document.getElementById('coachReopenHint');
    if (hint) { hideHint(); }
  });
})();
'''
