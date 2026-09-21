from __future__ import annotations

LANDING_HEADER_HTML = r'''<nav class="landing-nav">
    <details class="mobile-menu">
      <summary aria-label="Open navigation menu"></summary>
      <div class="mobile-menu-panel">
        <a href="#capabilities" onclick="this.closest('details').removeAttribute('open')">Capabilities</a>
        <a href="#security" onclick="this.closest('details').removeAttribute('open')">Security</a>
        <a href="#how" onclick="this.closest('details').removeAttribute('open')">How it works</a>
        <a href="/pricing">Pricing</a>
        <button class="mobile-signin" onclick="location.href='/dashboard'">Sign in →</button>
      </div>
    </details>
    <div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>
    <div class="landing-links"><a href="#capabilities">Capabilities</a><a href="#security">Security</a><a href="#how">How it works</a><a href="/pricing">Pricing</a></div>
    <button class="landing-signin" onclick="location.href='/dashboard'">Sign in <span>→</span></button>
  </nav>'''
