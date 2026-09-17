from __future__ import annotations

# Dashboard shell markup. Onboarding is kept as a dedicated component so the
# guided setup can evolve without coupling it to the individual dashboard views.
from .web_dashboard_markup_base import DASHBOARD_BASE_MARKUP

ONBOARDING_MARKUP = '''
<div id="onboardingModal" class="modal-backdrop hidden">
  <div class="modal onboarding-modal">
    <div class="onboarding-head">
      <div><div class="onboarding-kicker">GETTING STARTED</div><h2 id="onboardingTitle">Set up Lucas</h2></div>
      <button class="onboarding-close" onclick="finishOnboarding()" aria-label="Close">×</button>
    </div>
    <div class="onboarding-progress"><span id="onboardingDot1"></span><span id="onboardingDot2"></span><span id="onboardingDot3"></span><span id="onboardingDot4"></span></div>
    <div id="onboardingStep1" class="onboarding-step">
      <div class="onboarding-number">1</div><h3>Connect your AI</h3>
      <p>Start by connecting the AI you want to use with Lucas. You will authorize it securely through the Lucas MCP Gateway.</p>
      <button class="btn primary onboarding-action" onclick="onboardingGo('ai')">Connect an AI →</button>
    </div>
    <div id="onboardingStep2" class="onboarding-step hidden">
      <div class="onboarding-number">2</div><h3>Connect your computer</h3>
      <p>Install Lucas Node on the computer you want the AI to control, then connect it to this account.</p>
      <div class="onboarding-action-row"><a class="btn secondary onboarding-action" href="/download/Lucas-Node.bat">Download Lucas Node</a><button class="btn primary onboarding-action" onclick="onboardingGo('nodes')">Connect computer →</button></div>
    </div>
    <div id="onboardingStep3" class="onboarding-step hidden">
      <div class="onboarding-number">3</div><h3>Choose permissions</h3>
      <p>Open your computer settings and choose what Lucas can access. Background work can stay unobtrusive while foreground and sensitive actions can require confirmation.</p>
      <div class="onboarding-permissions"><span>✓ Choose allowed folders</span><span>✓ Control foreground / focus confirmation</span><span>✓ Keep sensitive actions protected</span></div>
      <button class="btn primary onboarding-action" onclick="onboardingGo('nodes')">Open computer settings →</button>
    </div>
    <div id="onboardingStep4" class="onboarding-step hidden">
      <div class="onboarding-number">4</div><h3>Give your AI a real task</h3>
      <p>Setup is complete. Go back to your connected AI and ask it to use Lucas on your computer. Start with a simple task so you can see the permission flow.</p>
      <div class="onboarding-example"><small>TRY THIS</small><b>“Use Lucas to list the files on my Desktop.”</b></div>
      <button class="btn primary onboarding-action" onclick="finishOnboarding()">Finish setup</button>
    </div>
    <div class="onboarding-actions"><button id="onboardingBack" class="btn secondary" onclick="onboardingBack()">Back</button><button id="onboardingNext" class="btn secondary" onclick="onboardingNext()">Skip / Next</button></div>
  </div>
</div>
'''

DASHBOARD_MARKUP = DASHBOARD_BASE_MARKUP + ONBOARDING_MARKUP + '<div id="toast" class="toast hidden"></div>\n'
