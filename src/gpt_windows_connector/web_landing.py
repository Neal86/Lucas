from __future__ import annotations

LANDING_HTML = '''<section id="landing" class="landing">
  <style>
    /* Landing conversion refresh */
    .landing-nav{
      position:sticky!important;top:0;z-index:40!important;
      max-width:none!important;width:100%;
      padding-left:max(28px,calc((100vw - 1240px)/2 + 28px))!important;
      padding-right:max(28px,calc((100vw - 1240px)/2 + 28px))!important;
      background:rgba(5,7,13,.76);
      backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);
      box-shadow:0 1px 0 rgba(255,255,255,.06);
    }
    .hero{padding-top:112px!important}
    .hero h1{margin-top:0!important}
    .hero h1 .hero-accent{display:inline-block;background:linear-gradient(100deg,#7c8cff,#61d7ff);-webkit-background-clip:text;color:transparent}
    .landing-section-cta,.how-cta{margin-top:34px;display:flex;justify-content:flex-start}
    .how-cta{justify-content:center;margin-top:42px}
    .landing-section-cta .hero-secondary,.how-cta .hero-primary{display:inline-flex;align-items:center;gap:8px}
    @media(max-width:800px){
      .landing-nav{padding-left:18px!important;padding-right:18px!important}
      .hero{padding-top:72px!important}
      .landing-section-cta{justify-content:center}
    }
  </style>
  <nav class="landing-nav">
    <div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>
    <div class="landing-links"><a href="#capabilities">Capabilities</a><a href="#security">Security</a><a href="#how">How it works</a><a href="/pricing">Pricing</a></div>
    <button class="landing-signin" onclick="openAuth()">Sign in <span>→</span></button>
  </nav>
  <div class="hero-glow glow-a"></div><div class="hero-glow glow-b"></div>
  <main class="hero">
    <h1>Let AI Work for You<br><span class="hero-accent">With $0 API Fees.</span></h1>
    <p class="hero-copy">Connect the newest and smartest AI models to your computer, apps, files, and browser — without paying extra API or token fees.</p>
    <div class="hero-actions"><button class="hero-primary" onclick="openAuth()">Get Started Free <span>↗</span></button><a class="hero-secondary" href="#how">See How It Works ↓</a></div>
    <div class="hero-pills"><span>◆ Model agnostic</span><span>◈ Cross-platform</span><span>⚡ Direct execution</span></div>
  </main>
  <section id="capabilities" class="landing-section"><div class="section-kicker">WHAT LUCAS UNLOCKS</div><h2>Your AI can finally <span>do the work.</span></h2><p class="section-copy">Lucas is the execution layer between intelligence and your computer. One secure MCP connection exposes the tools an AI needs to act.</p><div class="feature-grid"><article><b>01</b><div class="feature-icon">⌘</div><h3>Terminal & Code</h3><p>Run commands, build projects, execute scripts and work directly inside your development environment.</p></article><article><b>02</b><div class="feature-icon">▱</div><h3>Files & Projects</h3><p>Read and write real project files with folder-level boundaries you explicitly control.</p></article><article><b>03</b><div class="feature-icon">◎</div><h3>Browser</h3><p>Navigate sites, interact with web apps and automate browser workflows from the same AI session.</p></article><article><b>04</b><div class="feature-icon">◇</div><h3>Computer Use</h3><p>Extend beyond APIs into desktop applications and the graphical workflows where your work lives.</p></article><article><b>05</b><div class="feature-icon">⑂</div><h3>Git</h3><p>Inspect changes, work with repositories and execute development workflows without another agent layer.</p></article><article><b>06</b><div class="feature-icon">⌁</div><h3>Remote Access</h3><p>Your computer connects outbound through Lucas, making it available securely wherever your AI runs.</p></article></div></section>
  <section class="token-section"><div class="token-copy"><div class="section-kicker">A DIFFERENT ARCHITECTURE</div><h2>Token-free<br><span>execution.</span></h2><p>Lucas doesn't put another AI agent between your model and your computer. Tool execution happens directly through the Lucas node — no second model loop consuming AI tokens just to operate your machine.</p><div class="token-points"><span>✓ No extra model layer</span><span>✓ No execution-agent token burn</span><span>✓ Bring any MCP-compatible AI</span></div><div class="landing-section-cta"><button class="hero-secondary" onclick="openAuth()">Run AI on Your Computer <span>→</span></button></div></div><div class="compare-card"><div class="compare-row dim"><span>Traditional agent stack</span><div>YOUR AI → <b>ANOTHER AI AGENT</b> → COMPUTER</div><em>extra model usage</em></div><div class="compare-row bright"><span>Lucas</span><div>YOUR AI → <b>LUCAS</b> → COMPUTER</div><em>direct execution</em></div></div></section>
  <section id="security" class="landing-section security"><div><div class="section-kicker">CONTROL WITHOUT COMPROMISE</div><h2>Your computer.<br><span>Your boundaries.</span></h2></div><div class="security-list"><div><b>01</b><h3>Project-scoped access</h3><p>Expose only the folders and projects you choose — not your entire machine.</p></div><div><b>02</b><h3>Local permission control</h3><p>Security mode and allowed folders are changed only on the computer itself, never from the web.</p></div><div><b>03</b><h3>OAuth-secured MCP</h3><p>Independent authorization for every MCP client with secure account isolation.</p></div><div><b>04</b><h3>Activity visibility</h3><p>Review operations and connection activity from your Lucas dashboard.</p></div></div></section>
  <section id="how" class="how-section"><div class="section-kicker">THREE STEPS</div><h2>From AI to action.</h2><div class="steps"><div><span>1</span><h3>Connect your AI</h3><p>Connect ChatGPT, Claude, Codex, Gemini, or any MCP-compatible AI.</p></div><i>→</i><div><span>2</span><h3>Connect your computer</h3><p>Install Lucas and securely connect the computer you want your AI to use.</p></div><i>→</i><div><span>3</span><h3>Start working</h3><p>Your AI can now work with the apps, files, browser, and tools you allow.</p></div></div><div class="how-cta"><button class="hero-primary" onclick="openAuth()">Connect Your AI and Computer <span>→</span></button></div></section>
  <section class="final-cta"><div class="cta-glow"></div><div class="section-kicker">THE BRIDGE IS READY</div><h2>Any AI.<br>Any computer.</h2><p>Connect intelligence to the computer where the work actually happens.</p><button class="hero-primary" onclick="openAuth()">Get Started Free <span>↗</span></button></section>
  <footer class="landing-footer"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div><span>Any AI · Any Computer · MCP Native</span><span>© 2026 Lucas</span></footer>
</section>
'''
