from __future__ import annotations

ONBOARDING_SCRIPT = r'''
(() => {
  let active = false;
  let checklistGeneration = 0, checklistOwner = null;
  let hintGeneration = 0, hintOwner = null;
  const userKey = () => 'lucas-setup-checklist-v1:' + (state?.user?.email || 'guest');
  const hintKey = () => 'lucas-setup-checklist-hint-v1:' + (state?.user?.email || 'guest');
  const hasAi = () => (state?.aiClients || []).length > 0;
  const authorizedNodes = () => (state?.nodes || []).filter(n => n.authorized || n.access_state === 'authorized');
  const hasComputer = () => authorizedNodes().length > 0;
  const hasPermissions = () => hasComputer();
  const allDone = () => hasAi() && hasComputer() && hasPermissions();
  const appVisible = () => !!state?.user && document.getElementById('auth')?.classList.contains('hidden') && !document.getElementById('app')?.classList.contains('hidden');
  const ownsSession = owner => !!owner?.user && owner.user === state.user && owner.login === loginGeneration && appVisible();
  const ownsChecklist = owner => active && owner === checklistOwner && owner?.generation === checklistGeneration && ownsSession(owner);
  const ownsHint = owner => !!owner && owner === hintOwner && owner.generation === hintGeneration && ownsSession(owner);

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
    coach.setAttribute('aria-label',wt('Getting Started'));
    document.body.appendChild(coach);
  };

  const hideHint = (owner = hintOwner) => {
    if (!owner || owner !== hintOwner) return;
    hintGeneration++;
    hintOwner = null;
    if (owner.showTimer !== null) clearTimeout(owner.showTimer);
    if (owner.dismissTimer !== null) clearTimeout(owner.dismissTimer);
    owner.hint?.remove();
    owner.nav?.classList.remove('lucas-reopen-target');
  };

  const showReopenHint = owner => {
    if (!ownsHint(owner) || active) return;
    const nav = document.getElementById('gettingStartedNav');
    if (!nav) return hideHint(owner);
    try { if (localStorage.getItem(owner.key)) return hideHint(owner); localStorage.setItem(owner.key,'1'); } catch (_) {}
    owner.nav = nav;
    nav.classList.add('lucas-reopen-target');
    const hint = document.createElement('div');
    owner.hint = hint;
    hint.id = 'coachReopenHint';
    hint.innerHTML = 'You can reopen setup guidance here anytime.<br><button type="button">Got it</button>';
    document.body.appendChild(hint);
    const place = () => {
      const r = nav.getBoundingClientRect();
      hint.style.left = Math.min(window.innerWidth - hint.offsetWidth - 12, r.right + 12) + 'px';
      hint.style.top = Math.max(12, Math.min(window.innerHeight - hint.offsetHeight - 12, r.top)) + 'px';
    };
    const dismiss = () => { if (ownsHint(owner)) hideHint(owner); };
    hint.querySelector('button').onclick = dismiss;
    place();
    owner.dismissTimer = setTimeout(dismiss, 9000);
  };

  const step = (label, done, target) => `<button type="button" class="coach-step ${done?'done':''}" data-target="${target}"><span class="coach-status">${done?'✓':'○'}</span><span>${label}</span></button>`;

  const renderChecklist = () => {
    if (!ownsChecklist(checklistOwner)) return hideGettingStarted();
    ensureUi();
    const coach = document.getElementById('lucasCoach');
    // A replaced render must not leave its detached buttons owning the checklist.
    const owner = {...checklistOwner, generation: ++checklistGeneration};
    checklistOwner = owner;
    coach.innerHTML = `<div class="coach-kicker">GETTING STARTED</div><h3>Setup Checklist</h3><div class="coach-list">${step('Connect your AI',hasAi(),'ai')}${step('Connect your computer',hasComputer(),'nodes')}${step('Set permissions',hasPermissions(),'nodes')}</div><div class="coach-actions"><button type="button" class="coach-close" id="coachClose">Close</button></div>`;
    coach.style.display = 'block';
    coach.style.left = '50%';
    coach.style.top = '50%';
    coach.style.transform = 'translate(-50%,-50%)';
    coach.querySelectorAll('.coach-step').forEach(btn => btn.onclick = () => {
      if (!ownsChecklist(owner)) return;
      const id = btn.dataset.target;
      closeGettingStarted(false, owner);
      const nav = document.querySelector(`.nav[data-view="${id}"]`);
      if (window.view) window.view(id, nav);
    });
    document.getElementById('coachClose').onclick = () => closeGettingStarted(true, owner);
  };

  function closeGettingStarted(showHint=true, owner=checklistOwner) {
    if (!ownsChecklist(owner)) return;
    active = false;
    checklistGeneration++;
    checklistOwner = null;
    const coach = document.getElementById('lucasCoach');
    if (coach) coach.style.display = 'none';
    try { localStorage.setItem(owner.key,'1'); } catch (_) {}
    hideHint();
    if (showHint) {
      const hint = {user: owner.user, login: owner.login, generation: ++hintGeneration,
        key: owner.hintKey, showTimer: null, dismissTimer: null, hint: null, nav: null};
      hintOwner = hint;
      hint.showTimer = setTimeout(() => {
        if (!ownsHint(hint)) return;
        hint.showTimer = null;
        showReopenHint(hint);
      }, 120);
    }
  }

  function hideGettingStarted() {
    active = false;
    checklistGeneration++;
    checklistOwner = null;
    hideHint();
    const coach = document.getElementById('lucasCoach');
    if (coach) coach.style.display = 'none';
  }

  function openGettingStarted() {
    if (!appVisible()) return;
    hideHint();
    active = true;
    checklistOwner = {user: state.user, login: loginGeneration, generation: ++checklistGeneration,
      key: userKey(), hintKey: hintKey()};
    renderChecklist();
  }

  function maybeStartOnboarding() {
    if ((checklistOwner && !ownsSession(checklistOwner)) || (hintOwner && !ownsSession(hintOwner))) hideGettingStarted();
    if (!appVisible()) return;
    if (allDone()) return;
    try { if (localStorage.getItem(userKey())) return; } catch (_) {}
    openGettingStarted();
  }

  function sync() {
    if (active) renderChecklist();
    else if (hintOwner && !ownsSession(hintOwner)) hideHint();
  }

  window.openGettingStarted = openGettingStarted;
  window.maybeStartOnboarding = maybeStartOnboarding;
  window.finishOnboarding = () => closeGettingStarted(true);
  window.hideGettingStarted = hideGettingStarted;
  window.onboardingSync = sync;
  window.addEventListener('resize', () => {
    if (hintOwner?.hint) hideHint();
  });
})();
'''
