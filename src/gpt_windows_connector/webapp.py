from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import unquote

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route

from . import gateway
from .admin import admin_routes


BRAND_ASSET_DIR = Path(__file__).with_name("assets")

DASHBOARD_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Lucas</title>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
<style>
:root{--bg:#f6f7fb;--card:#fff;--text:#101828;--muted:#667085;--line:#e4e7ec;--accent:#155eef;--ok:#079455;--danger:#d92d20;--shadow:0 1px 3px rgba(16,24,40,.08),0 1px 2px rgba(16,24,40,.05)}*{box-sizing:border-box}body{margin:0;font:14px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--text);background:var(--bg)}button,input,select{font:inherit}.hidden{display:none!important}.auth{min-height:100vh;display:grid;place-items:center;padding:24px}.auth-card{width:min(440px,100%);background:var(--card);border:1px solid var(--line);border-radius:18px;padding:30px;box-shadow:var(--shadow)}h1,h2,h3,p{margin-top:0}.brand{font-size:23px;font-weight:750;margin-bottom:6px}.sub{color:var(--muted);margin-bottom:24px}.field{margin:14px 0}.field label{display:block;font-weight:600;margin-bottom:6px}.input,select{width:100%;border:1px solid #d0d5dd;border-radius:9px;padding:10px 12px;background:#fff;color:var(--text);outline:none}.input:focus,select:focus{border-color:#84adff;box-shadow:0 0 0 3px #d1e0ff}.btn{border:0;border-radius:9px;padding:10px 14px;font-weight:650;cursor:pointer}.primary{background:var(--accent);color:#fff}.secondary{background:#fff;color:#344054;border:1px solid #d0d5dd}.danger{background:#fff;color:var(--danger);border:1px solid #fda29b}.google{width:100%;background:#fff;border:1px solid #d0d5dd;color:#344054;margin-top:10px}.switch{color:var(--accent);background:none;border:0;padding:0;cursor:pointer}.error{background:#fef3f2;color:#b42318;border:1px solid #fecdca;padding:10px;border-radius:8px;margin:10px 0}.shell{min-height:100vh;display:grid;grid-template-columns:240px 1fr}.side{background:#101828;color:#fff;padding:22px 14px;display:flex;flex-direction:column;gap:6px}.logo{font-size:18px;font-weight:750;padding:0 10px 22px}.nav{background:transparent;color:#d0d5dd;border:0;text-align:left;padding:10px 12px;border-radius:8px;cursor:pointer}.nav.active,.nav:hover{background:#344054;color:#fff}.userbox{margin-top:auto;border-top:1px solid #344054;padding:15px 10px 0;color:#d0d5dd}.main{padding:28px;overflow:auto}.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:var(--shadow)}.metric{font-size:28px;font-weight:750}.muted{color:var(--muted)}.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:14px}.toolbar .input,.toolbar select{width:auto}.table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}.table th,.table td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}.table th{font-size:12px;color:#475467;background:#f9fafb;text-transform:uppercase;letter-spacing:.03em}.badge{display:inline-flex;padding:3px 8px;border-radius:999px;font-size:12px;font-weight:650}.online{background:#ecfdf3;color:#027a48}.offline{background:#f2f4f7;color:#475467}.modal-backdrop{position:fixed;inset:0;background:rgba(16,24,40,.45);display:grid;place-items:center;padding:18px}.modal{width:min(620px,100%);max-height:88vh;overflow:auto;background:#fff;border-radius:14px;padding:22px;box-shadow:0 20px 40px rgba(16,24,40,.22)}.row{display:flex;gap:10px}.row>*{flex:1}.folderbox{border:1px solid var(--line);border-radius:10px;min-height:250px;max-height:360px;overflow:auto;margin-top:8px}.folder{display:flex;gap:10px;align-items:center;padding:10px 12px;border-bottom:1px solid #f2f4f7;cursor:pointer}.folder:hover{background:#f9fafb}.folder.selected{background:#eff4ff}.path{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;color:#475467;word-break:break-all}.actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}.empty{padding:28px;text-align:center;color:var(--muted)}pre.details{white-space:pre-wrap;max-width:560px;margin:0;font-size:12px}.log-filter{display:flex;gap:8px;margin-bottom:12px}.toast{position:fixed;right:22px;bottom:22px;background:#101828;color:#fff;padding:12px 16px;border-radius:9px;box-shadow:var(--shadow)}.platform-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:20px}.platform-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:var(--shadow);display:flex;flex-direction:column;min-height:168px}.platform-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.platform-name{font-size:17px;font-weight:700}.platform-card p{color:var(--muted);margin:0 0 18px;line-height:1.55}.platform-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:auto}.coming{background:#f2f4f7;color:#667085}.disabled-btn{cursor:not-allowed;opacity:.62;background:#f9fafb;color:#98a2b3;border:1px solid #e4e7ec}@media(max-width:850px){.shell{grid-template-columns:1fr}.side{position:sticky;top:0;z-index:5;flex-direction:row;overflow:auto;padding:10px}.logo,.userbox{display:none}.main{padding:16px}.grid,.platform-grid{grid-template-columns:1fr}.row{flex-direction:column}.table{display:block;overflow:auto}}

/* Lucas public landing */
.landing{--ink:#f5f7ff;--soft:#9aa4bd;--blue:#6d7cff;--cyan:#55d6ff;position:relative;overflow:hidden;background:#05070d;color:var(--ink);min-height:100vh;font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}.landing *{box-sizing:border-box}.landing-nav{height:82px;max-width:1240px;margin:auto;padding:0 28px;display:flex;align-items:center;justify-content:space-between;position:relative;z-index:5;border-bottom:1px solid rgba(255,255,255,.07)}.landing-logo{display:flex;align-items:center;gap:10px;font-size:19px;font-weight:760;letter-spacing:-.02em}.logo-mark{width:30px;height:30px;display:grid;place-items:center;border-radius:9px;background:linear-gradient(145deg,#8c96ff,#5665ef);box-shadow:0 0 30px rgba(105,118,255,.28);font-weight:850}.landing-links{display:flex;gap:34px}.landing-links a,.landing-footer{color:#8e98ae}.landing-links a{font-size:13px;text-decoration:none;transition:.2s}.landing-links a:hover{color:#fff}.landing-signin{color:#dfe4f3;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.11);border-radius:10px;padding:10px 15px;cursor:pointer}.hero{max-width:1180px;margin:auto;text-align:center;padding:120px 28px 82px;position:relative;z-index:2}.eyebrow,.section-kicker{font-size:11px;font-weight:750;letter-spacing:.18em;color:#8490aa}.eyebrow{display:inline-flex;align-items:center;gap:9px;border:1px solid rgba(255,255,255,.1);border-radius:999px;padding:8px 13px;background:rgba(255,255,255,.025)}.pulse{width:6px;height:6px;border-radius:50%;background:#68e5ac;box-shadow:0 0 12px #68e5ac}.hero h1{font-size:clamp(62px,8.5vw,126px);line-height:.88;letter-spacing:-.075em;margin:31px 0 35px;font-weight:650}.hero h1 span,.landing-section h2 span,.token-copy h2 span,.security h2 span{background:linear-gradient(100deg,#7c8cff,#61d7ff);-webkit-background-clip:text;color:transparent}.hero-copy{max-width:730px;margin:0 auto 34px;color:#9da7bd;font-size:19px;line-height:1.65}.hero-actions{display:flex;justify-content:center;align-items:center;gap:12px}.hero-primary{border:0;color:white;background:linear-gradient(110deg,#6473f4,#5969e9);padding:14px 21px;border-radius:11px;font-weight:700;box-shadow:0 10px 40px rgba(86,103,235,.25);cursor:pointer}.hero-primary span{margin-left:12px}.hero-secondary{padding:13px 19px;color:#aeb7ca;text-decoration:none;border:1px solid rgba(255,255,255,.1);border-radius:11px;background:rgba(255,255,255,.025)}.hero-pills{margin:35px 0 58px;display:flex;justify-content:center;gap:28px;color:#77829a;font-size:12px}.network-card{max-width:950px;margin:auto;border:1px solid rgba(255,255,255,.09);border-radius:18px;background:linear-gradient(180deg,rgba(20,25,42,.75),rgba(9,12,21,.82));box-shadow:0 30px 100px rgba(0,0,0,.4),inset 0 1px rgba(255,255,255,.04);backdrop-filter:blur(18px);overflow:hidden}.network-head{height:45px;border-bottom:1px solid rgba(255,255,255,.07);display:flex;align-items:center;justify-content:space-between;padding:0 17px;color:#68738a;font-size:9px;letter-spacing:.16em}.live{color:#69dba9}.live i{display:inline-block;width:5px;height:5px;background:#69dba9;border-radius:50%;margin-right:6px}.network{min-height:270px;display:flex;align-items:center;justify-content:center;padding:30px}.ai-stack,.computer-node,.lucas-core{display:flex;flex-direction:column;align-items:center;gap:7px}.ai-stack{width:155px;display:grid;grid-template-columns:repeat(3,42px);justify-content:center}.ai-stack small{grid-column:1/-1}.mini-node{height:42px;border:1px solid rgba(255,255,255,.1);border-radius:10px;display:grid;place-items:center;background:#101522;color:#9aa6bf;font-size:10px}.network small{color:#606b82;font-size:8px;letter-spacing:.14em;margin-top:8px}.flow-line{width:140px;height:1px;background:linear-gradient(90deg,transparent,#6473f4,transparent);position:relative}.flow-line i{position:absolute;width:5px;height:5px;border-radius:50%;background:#7f8cff;top:-2px;animation:flow 2.3s linear infinite;box-shadow:0 0 10px #7380ff}@keyframes flow{from{left:0}to{left:100%}}.core-ring{width:86px;height:86px;border-radius:26px;border:1px solid rgba(122,137,255,.4);display:grid;place-items:center;background:radial-gradient(circle,rgba(103,119,255,.25),rgba(70,80,180,.08));box-shadow:0 0 60px rgba(93,108,255,.22)}.core-ring b{font-size:32px}.lucas-core strong{font-size:11px;letter-spacing:.18em}.screen{width:155px;height:95px;border:1px solid rgba(255,255,255,.12);border-radius:9px;background:#090d16;padding:10px;text-align:left;font-family:ui-monospace,monospace;box-shadow:0 18px 35px rgba(0,0,0,.35)}.screen span{display:inline-block;width:5px;height:5px;background:#566074;border-radius:50%;margin-right:3px}.screen b,.screen em{display:block;font-size:9px;margin-top:12px;color:#8390a8;font-style:normal}.screen em{color:#66dba8;margin-top:5px}.hero-glow{position:absolute;border-radius:50%;filter:blur(100px);pointer-events:none}.glow-a{width:650px;height:450px;left:15%;top:180px;background:rgba(77,83,230,.13)}.glow-b{width:500px;height:400px;right:4%;top:300px;background:rgba(44,180,235,.08)}.landing-section{max-width:1180px;margin:auto;padding:130px 28px}.landing-section h2,.token-copy h2,.how-section h2,.final-cta h2{font-size:clamp(42px,5vw,72px);letter-spacing:-.055em;line-height:1.03;margin:16px 0 22px;font-weight:600}.section-copy{color:#8994aa;max-width:650px;font-size:17px;line-height:1.65}.feature-grid{display:grid;grid-template-columns:repeat(3,1fr);margin-top:60px;border-top:1px solid rgba(255,255,255,.08);border-left:1px solid rgba(255,255,255,.08)}.feature-grid article{min-height:260px;padding:27px;border-right:1px solid rgba(255,255,255,.08);border-bottom:1px solid rgba(255,255,255,.08);position:relative;background:rgba(255,255,255,.012);transition:.25s}.feature-grid article:hover{background:rgba(100,115,244,.05)}.feature-grid article>b,.security-list b{position:absolute;right:22px;top:20px;color:#444e64;font-size:10px}.feature-icon{font-size:28px;color:#8390ff;margin:20px 0 36px}.feature-grid h3,.security-list h3,.steps h3{font-size:18px;margin-bottom:10px}.feature-grid p,.security-list p,.steps p{color:#7f899f;line-height:1.6}.token-section{max-width:1180px;margin:40px auto 100px;padding:80px 28px;display:grid;grid-template-columns:1fr 1.05fr;gap:80px;align-items:center}.token-copy p{color:#8b95aa;font-size:16px;line-height:1.7;max-width:520px}.token-points{display:flex;flex-direction:column;gap:12px;margin-top:28px;color:#aab3c5;font-size:13px}.token-points span::first-letter{color:#65d8a7}.compare-card{border:1px solid rgba(255,255,255,.09);border-radius:18px;padding:12px;background:#090c14}.compare-row{padding:27px;border-radius:12px}.compare-row+ .compare-row{margin-top:8px}.compare-row>span{font-size:10px;letter-spacing:.12em;color:#6e788e}.compare-row div{margin:22px 0 10px;font-family:ui-monospace,monospace;font-size:12px;color:#8993a8}.compare-row em{font-size:10px;color:#687287;font-style:normal}.compare-row.dim{opacity:.55}.compare-row.bright{background:linear-gradient(110deg,rgba(91,105,235,.15),rgba(53,189,225,.07));border:1px solid rgba(104,121,255,.2)}.compare-row.bright b,.compare-row.bright em{color:#79d7ff}.security{display:grid;grid-template-columns:1fr 1.1fr;gap:100px}.security h2{font-size:clamp(42px,5vw,70px);letter-spacing:-.05em;line-height:1.05}.security-list>div{position:relative;padding:25px 50px 25px 0;border-top:1px solid rgba(255,255,255,.09)}.security-list b{right:0;top:28px}.security-list h3{margin:0 0 7px}.security-list p{margin:0}.how-section{max-width:1180px;margin:auto;padding:130px 28px;text-align:center}.steps{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:25px;align-items:center;margin-top:60px}.steps>div{padding:35px 20px}.steps>div>span{width:35px;height:35px;border:1px solid rgba(117,132,255,.35);border-radius:10px;display:grid;place-items:center;margin:0 auto 22px;color:#8996ff}.steps>i{color:#404a61}.final-cta{position:relative;text-align:center;padding:150px 28px 170px;border-top:1px solid rgba(255,255,255,.07);overflow:hidden}.final-cta p{color:#8b95aa;font-size:17px;margin-bottom:28px}.cta-glow{position:absolute;width:600px;height:300px;left:50%;top:40%;transform:translate(-50%,-50%);background:rgba(81,96,235,.13);filter:blur(90px);border-radius:50%}.final-cta>*:not(.cta-glow){position:relative}.landing-footer{max-width:1180px;margin:auto;padding:28px;display:flex;justify-content:space-between;align-items:center;border-top:1px solid rgba(255,255,255,.07);font-size:11px}.landing-footer .landing-logo{color:#dfe4f3}.landing .auth{color:#101828}.landing.hidden{display:none!important}@media(max-width:800px){.landing-links{display:none}.hero{padding-top:80px}.hero h1{font-size:58px}.hero-copy{font-size:16px}.hero-actions,.hero-pills{flex-direction:column}.network{transform:scale(.8);margin:-20px -80px}.flow-line{width:55px}.feature-grid{grid-template-columns:1fr}.token-section,.security{grid-template-columns:1fr;gap:45px}.steps{grid-template-columns:1fr}.steps>i{transform:rotate(90deg)}.landing-footer{gap:18px;flex-direction:column}.landing-section,.how-section{padding-top:90px;padding-bottom:90px}}
.brand img{display:block;width:min(250px,100%);height:auto;margin-bottom:8px}.logo img{display:block;width:184px;height:auto;background:#fff;border-radius:9px;padding:5px 9px}.landing-logo img{display:block;height:44px;width:auto;background:#fff;border-radius:9px;padding:4px 8px}.core-ring img{width:66px;height:66px;object-fit:contain;background:#fff;border-radius:18px;padding:5px}.landing-footer .landing-logo img{height:38px}@media(max-width:850px){.logo img{width:150px}}
</style>
<link rel="icon" type="image/png" href="/assets/lucas-logo-square.png" />
</head>
<body>
<section id="landing" class="landing">
  <nav class="landing-nav"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div><div class="landing-links"><a href="#capabilities">Capabilities</a><a href="#security">Security</a><a href="#how">How it works</a></div><button class="landing-signin" onclick="openAuth()">Sign in <span>→</span></button></nav>
  <div class="hero-glow glow-a"></div><div class="hero-glow glow-b"></div>
  <main class="hero"><div class="eyebrow"><span class="pulse"></span>MCP-NATIVE COMPUTER EXECUTION</div><h1>Let your AI leave<br><span>the chat box.</span></h1><p class="hero-copy">Give any MCP-compatible AI secure access to the computer where your real work happens — files, terminal, browser, Git and desktop apps.</p><div class="hero-actions"><button class="hero-primary" onclick="openAuth()">Connect your computer <span>↗</span></button><a class="hero-secondary" href="#how">See how it works ↓</a></div><div class="hero-pills"><span>◆ Model agnostic</span><span>◈ Cross-platform</span><span>⚡ Token-free execution</span></div>
  <div class="network-card"><div class="network-head"><span>UNIVERSAL MCP BRIDGE</span><span class="live"><i></i> READY</span></div><div class="network"><div class="ai-stack"><div class="mini-node">AI</div><div class="mini-node">LLM</div><div class="mini-node">Agent</div><small>ANY MCP CLIENT</small></div><div class="flow-line"><i></i></div><div class="lucas-core"><div class="core-ring"><img src="/assets/lucas-logo-square.png" alt="Lucas" /></div><strong>LUCAS</strong><small>SECURE EXECUTION LAYER</small></div><div class="flow-line"><i></i></div><div class="computer-node"><div class="screen"><span></span><span></span><span></span><b>~/ project</b><em>$ lucas ready_</em></div><small>YOUR COMPUTER</small></div></div></div></main>
  <section id="capabilities" class="landing-section"><div class="section-kicker">WHAT LUCAS UNLOCKS</div><h2>Your AI can finally <span>do the work.</span></h2><p class="section-copy">Lucas is the execution layer between intelligence and your computer. One secure MCP connection exposes the tools an AI needs to act.</p><div class="feature-grid"><article><b>01</b><div class="feature-icon">⌘</div><h3>Terminal & Code</h3><p>Run commands, build projects, execute scripts and work directly inside your development environment.</p></article><article><b>02</b><div class="feature-icon">▱</div><h3>Files & Projects</h3><p>Read and write real project files with folder-level boundaries you explicitly control.</p></article><article><b>03</b><div class="feature-icon">◎</div><h3>Browser</h3><p>Navigate sites, interact with web apps and automate browser workflows from the same AI session.</p></article><article><b>04</b><div class="feature-icon">◇</div><h3>Computer Use</h3><p>Extend beyond APIs into desktop applications and the graphical workflows where your work lives.</p></article><article><b>05</b><div class="feature-icon">⑂</div><h3>Git</h3><p>Inspect changes, work with repositories and execute development workflows without another agent layer.</p></article><article><b>06</b><div class="feature-icon">⌁</div><h3>Remote Access</h3><p>Your computer connects outbound through Lucas, making it available securely wherever your AI runs.</p></article></div></section>
  <section class="token-section"><div class="token-copy"><div class="section-kicker">A DIFFERENT ARCHITECTURE</div><h2>Token-free<br><span>execution.</span></h2><p>Lucas doesn't put another AI agent between your model and your computer. Tool execution happens directly through the Lucas node — no second model loop consuming AI tokens just to operate your machine.</p><div class="token-points"><span>✓ No extra model layer</span><span>✓ No execution-agent token burn</span><span>✓ Bring any MCP-compatible AI</span></div></div><div class="compare-card"><div class="compare-row dim"><span>Traditional agent stack</span><div>YOUR AI → <b>ANOTHER AI AGENT</b> → COMPUTER</div><em>extra model usage</em></div><div class="compare-row bright"><span>Lucas</span><div>YOUR AI → <b>LUCAS</b> → COMPUTER</div><em>direct execution</em></div></div></section>
  <section id="security" class="landing-section security"><div><div class="section-kicker">CONTROL WITHOUT COMPROMISE</div><h2>Your computer.<br><span>Your boundaries.</span></h2></div><div class="security-list"><div><b>01</b><h3>Project-scoped access</h3><p>Expose only the folders and projects you choose — not your entire machine.</p></div><div><b>02</b><h3>Local permission control</h3><p>Security mode and allowed folders are changed only on the computer itself, never from the web.</p></div><div><b>03</b><h3>OAuth-secured MCP</h3><p>Independent authorization for every MCP client with secure account isolation.</p></div><div><b>04</b><h3>Activity visibility</h3><p>Review operations and connection activity from your Lucas dashboard.</p></div></div></section>
  <section id="how" class="how-section"><div class="section-kicker">THREE STEPS</div><h2>From AI to action.</h2><div class="steps"><div><span>1</span><h3>Connect a computer</h3><p>Install Lucas Node and pair your machine securely.</p></div><i>→</i><div><span>2</span><h3>Add Lucas MCP</h3><p>Use one MCP endpoint with any compatible AI or agent.</p></div><i>→</i><div><span>3</span><h3>Start working</h3><p>Your AI can now use the tools you've explicitly allowed.</p></div></div></section>
  <section class="final-cta"><div class="cta-glow"></div><div class="section-kicker">THE BRIDGE IS READY</div><h2>Any AI.<br>Any computer.</h2><p>Connect intelligence to the computer where the work actually happens.</p><button class="hero-primary" onclick="openAuth()">Get started with Lucas <span>↗</span></button></section>
  <footer class="landing-footer"><div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div><span>Any AI · Any Computer · MCP Native</span><span>© 2026 Lucas</span></footer>
</section>
<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div><div class="sub">Connect any MCP-compatible AI to your computers through Lucas.</div><div id="authError" class="error hidden"></div><div id="loginForm"><div class="field"><label>Email</label><input id="loginEmail" class="input" type="email" autocomplete="email"></div><div class="field"><label>Password</label><input id="loginPassword" class="input" type="password" autocomplete="current-password"></div><button class="btn primary" style="width:100%" onclick="login()">Sign in</button><button class="btn google" onclick="location.href='/auth/google/start'">Continue with Google</button><p class="muted" style="margin:16px 0 0">No account? <button class="switch" onclick="showRegister(true)">Create one</button></p></div><div id="registerForm" class="hidden"><div class="field"><label>Name</label><input id="regName" class="input"></div><div class="field"><label>Email</label><input id="regEmail" class="input" type="email"></div><div class="field"><label>Password</label><input id="regPassword" class="input" type="password" placeholder="At least 10 characters"></div><input id="regWebsite" type="text" tabindex="-1" autocomplete="off" style="position:absolute;left:-10000px;opacity:0" aria-hidden="true"><div id="turnstileWrap" class="field __TURNSTILE_CLASS__"><div class="cf-turnstile" data-sitekey="__TURNSTILE_SITE_KEY__"></div></div><button class="btn primary" style="width:100%" onclick="registerUser()">Create account</button><button class="btn google" onclick="location.href='/auth/google/start'">Sign up with Google</button><p class="muted" style="margin:16px 0 0">Already registered? <button class="switch" onclick="showRegister(false)">Sign in</button></p></div><div id="verifyForm" class="hidden"><p class="muted">We sent a 6-digit verification code to <b id="verifyEmailLabel"></b>.</p><div class="field"><label>Verification code</label><input id="verifyCode" class="input" inputmode="numeric" maxlength="6" autocomplete="one-time-code"></div><button class="btn primary" style="width:100%" onclick="verifyEmail()">Verify email</button><button class="btn secondary" style="width:100%;margin-top:10px" onclick="resendVerification()">Resend code</button></div></div></div>
<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div><button class="nav active" data-view="dashboard" onclick="view('dashboard',this)">Dashboard</button><button class="nav" data-view="nodes" onclick="view('nodes',this)">Computer Nodes</button><button class="nav" data-view="ai" onclick="view('ai',this)">AI Connections</button><button class="nav" data-view="tasks" onclick="view('tasks',this)">Task Runs</button><button class="nav" data-view="logs" onclick="view('logs',this)">Activity Logs</button><button class="nav" data-view="account" onclick="view('account',this)">Account & Security</button><button id="adminNav" class="nav hidden" data-view="admin" onclick="view('admin',this)">Admin</button><div class="userbox"><div id="userName"></div><small id="userEmail"></small><div style="margin-top:10px"><button class="btn secondary" onclick="logout()">Sign out</button></div></div></aside><main class="main"><div id="dashboard" class="view"><div class="top"><div><h2>Dashboard</h2><p class="muted">Your computers, AI connections, and recent activity.</p></div></div><div class="grid"><div class="card"><div class="muted">Paired computers</div><div id="metricPairedNodes" class="metric">0</div></div><div class="card"><div class="muted">Online computers</div><div id="metricNodes" class="metric">0</div></div><div class="card"><div class="muted">AI clients</div><div id="metricAiClients" class="metric">0</div></div></div><div class="card" style="margin-top:16px"><h3>Recent activity</h3><div id="recentLogs"></div></div></div><div id="nodes" class="view hidden"><div class="top"><div><h2>Computer Nodes</h2><p class="muted">Connect Lucas to your computers. Windows is available now; macOS and Linux support are coming soon.</p></div></div><div class="platform-grid"><div class="platform-card"><div class="platform-head"><span class="platform-name">Windows</span><span class="badge online">Available</span></div><p>Full Lucas Node support for Windows computers.</p><div class="platform-actions"><a class="btn secondary" style="text-decoration:none" href="/download/Lucas-Node.bat">Download Lucas Node</a><button class="btn primary" onclick="openPairModal()">Pair computer</button></div></div><div class="platform-card"><div class="platform-head"><span class="platform-name">macOS</span><span class="badge coming">Coming Soon</span></div><p>Lucas Node for macOS is in development.</p><div class="platform-actions"><button class="btn disabled-btn" type="button" disabled>Coming Soon</button></div></div><div class="platform-card"><div class="platform-head"><span class="platform-name">Linux</span><span class="badge coming">Coming Soon</span></div><p>Lucas Node for Linux is in development.</p><div class="platform-actions"><button class="btn disabled-btn" type="button" disabled>Coming Soon</button></div></div></div><div id="nodeTable"></div></div><div id="ai" class="view hidden"><div class="top"><div><h2>AI Connections</h2><p class="muted">Connect multiple AI and MCP clients to the same Lucas account securely with OAuth.</p></div><button class="btn primary" onclick="openAiModal()">Add AI</button></div><div class="card"><div style="display:flex;justify-content:space-between;gap:16px;align-items:center;flex-wrap:wrap"><div><h3 style="margin-bottom:6px">Lucas MCP Gateway</h3><p class="muted" style="margin:0">OAuth 2.0 + PKCE · refresh tokens · dynamic client registration</p></div><span class="badge online">Ready</span></div><div class="field"><label>MCP Server URL</label><input id="mcpUrl" class="input" readonly value="https://lucasmcp.com/mcp"></div><p class="muted">Use this same URL from ChatGPT, Claude, Gemini, Cursor, Codex, Claude Code, or any compatible MCP client. Each AI authorizes independently.</p><div class="toolbar"><button class="btn primary" onclick="openAiModal()">Add AI connection</button><button class="btn secondary" onclick="copyMcpUrl()">Copy MCP URL</button></div></div><div class="card" style="margin-top:16px"><h3>Registered AI / MCP clients</h3><div id="aiClientTable"><div class="empty">No OAuth clients registered yet.</div></div></div></div><div id="tasks" class="view hidden"><div class="top"><div><h2>Task Runs</h2><p class="muted">Task and subtask execution time measured by Lucas MCP.</p></div><button class="btn secondary" onclick="loadTaskRuns()">Refresh</button></div><div id="taskRunSummary" class="grid" style="margin-bottom:16px"></div><div id="taskRunTable"></div></div><div id="logs" class="view hidden"><div class="top"><div><h2>Activity Logs</h2><p class="muted">Only activity belonging to your account is shown.</p></div></div><div class="log-filter"><input id="logAction" class="input" placeholder="Action filter"><input id="logTarget" class="input" placeholder="Target"><button class="btn secondary" onclick="loadLogs()">Filter</button></div><div id="logTable"></div></div><div id="account" class="view hidden"><div class="top"><div><h2>Account & Security</h2><p class="muted">Authentication and connector security information.</p></div></div><div class="card"><h3 id="accountName"></h3><p id="accountEmail"></p><p class="muted">Authentication provider: <span id="accountProvider"></span></p><p class="muted">All AI-to-computer traffic is relayed through this VPS Gateway. Nodes do not require a public inbound port.</p></div></div><div id="admin" class="view hidden"><div class="top"><div><h2>Admin</h2><p class="muted">Lucas SaaS operations, users, usage, nodes, subscriptions, audit logs, and system health.</p></div></div><div class="toolbar" id="adminTabs"><button class="btn primary" onclick="adminTab('dashboard',this)">Dashboard</button><button class="btn secondary" onclick="adminTab('users',this)">Users</button><button class="btn secondary" onclick="adminTab('usage',this)">Usage</button><button class="btn secondary" onclick="adminTab('nodes',this)">Nodes</button><button class="btn secondary" onclick="adminTab('operations',this)">Operations</button><button class="btn secondary" onclick="adminTab('subscriptions',this)">Subscriptions</button><button class="btn secondary" onclick="adminTab('system',this)">System</button></div><div id="adminContent"><div class="card empty">Loading admin dashboard…</div></div></div></main></div><div id="adminUserModal" class="modal-backdrop hidden"><div class="modal" style="width:min(900px,100%)"><div id="adminUserDetail"></div><div class="actions"><button class="btn secondary" onclick="closeModal('adminUserModal')">Close</button></div></div></div>
<div id="nodeModal" class="modal-backdrop hidden"><div class="modal"><h3>Computer Node</h3><p class="muted">Rename this computer here. Security settings remain controlled locally from the Lucas tray.</p><div class="card"><div class="field"><label>Display name</label><input id="manageNodeNameInput" class="input" maxlength="120"></div><div class="field"><label>Security mode</label><div id="managePermissionText"></div></div><div class="field"><label>Allowed folders</label><pre id="manageRootsText" class="details"></pre></div></div><div class="field"><label>Node log</label><pre id="manageLogs" class="details card" style="max-height:220px;overflow:auto">Load logs after the node is online.</pre></div><div class="actions"><button class="btn danger" onclick="unpairNode()">Unpair</button><button class="btn secondary" onclick="loadNodeLogs()">Refresh logs</button><button class="btn secondary" onclick="closeModal('nodeModal')">Close</button><button class="btn primary" onclick="saveNodeName()">Save name</button></div></div></div>
<div id="aiModal" class="modal-backdrop hidden"><div class="modal"><h3>Add AI connection</h3><p class="muted">Lucas accepts multiple independent OAuth-capable MCP clients. Choose a client for setup guidance, then add the same MCP URL in that client.</p><div class="field"><label>AI / MCP client</label><select id="aiClientType" onchange="updateAiHelp()"><option>ChatGPT</option><option>Claude</option><option>Gemini</option><option>Cursor</option><option>Codex</option><option>Claude Code</option><option>Other MCP client</option></select></div><div class="field"><label>MCP Server URL</label><input id="aiModalUrl" class="input" readonly value="https://lucasmcp.com/mcp"></div><div id="aiHelp" class="card muted"></div><div class="actions"><button class="btn secondary" onclick="closeModal('aiModal')">Close</button><button class="btn primary" onclick="copyMcpUrl()">Copy MCP URL</button></div></div></div><div id="pairModal" class="modal-backdrop hidden"><div class="modal"><h3>Pair Windows Computer</h3><p class="muted">Download and run the Lucas Node script on the Windows PC, generate a one-time code here, then enter it in Lucas Settings. The computer name is detected automatically; you can rename it on this page after pairing.</p><p><a class="btn secondary" style="text-decoration:none" href="/download/Lucas-Node.bat">Download Lucas Node</a></p><div id="pairResult" class="card hidden"><div class="muted">Lucas pairing code</div><div id="pairCode" class="metric"></div><div class="path" id="pairCommand"></div></div><div class="actions"><button class="btn secondary" onclick="closeModal('pairModal')">Close</button><button class="btn primary" onclick="createPairCode()">Generate code</button></div></div></div>
<div id="toast" class="toast hidden"></div>
<script>
const state={user:null,nodes:[],aiClients:[]};
async function api(url,opt={}){const r=await fetch(url,{credentials:'include',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});let d={};try{d=await r.json()}catch{}if(r.status===401){showAuth();throw new Error('Please sign in')}if(!r.ok)throw new Error(d.error||('Request failed: '+r.status));return d}
function toast(t){const e=document.getElementById('toast');e.textContent=t;e.classList.remove('hidden');setTimeout(()=>e.classList.add('hidden'),2600)}
function showAuth(){stopRealtime();state.user=null;document.getElementById('app').classList.add('hidden');document.getElementById('auth').classList.remove('hidden')}
function showApp(){document.getElementById('auth').classList.add('hidden');document.getElementById('app').classList.remove('hidden')}
function authError(t){const e=document.getElementById('authError');e.textContent=t;e.classList.toggle('hidden',!t)}
let pendingVerificationEmail='';
function showRegister(v){authError('');document.getElementById('verifyForm').classList.add('hidden');document.getElementById('loginForm').classList.toggle('hidden',v);document.getElementById('registerForm').classList.toggle('hidden',!v)}
async function login(){try{await api('/auth/login',{method:'POST',body:JSON.stringify({email:loginEmail.value,password:loginPassword.value})});await boot()}catch(e){authError(e.message)}}
async function registerUser(){try{const widget=document.querySelector('[name="cf-turnstile-response"]');const d=await api('/auth/register',{method:'POST',body:JSON.stringify({name:regName.value,email:regEmail.value,password:regPassword.value,website:regWebsite.value,turnstile_token:widget?.value||''})});if(d.verification_required){pendingVerificationEmail=d.email;verifyEmailLabel.textContent=d.email;registerForm.classList.add('hidden');verifyForm.classList.remove('hidden');return}await boot()}catch(e){authError(e.message);if(window.turnstile)window.turnstile.reset()}}
async function verifyEmail(){try{await api('/auth/verify-email',{method:'POST',body:JSON.stringify({email:pendingVerificationEmail,code:verifyCode.value})});await boot()}catch(e){authError(e.message)}}
async function resendVerification(){try{await api('/auth/resend-verification',{method:'POST',body:JSON.stringify({email:pendingVerificationEmail})});toast('Verification code resent')}catch(e){authError(e.message)}}
async function logout(){await api('/api/logout',{method:'POST'}).catch(()=>{});showAuth()}
const viewPaths={dashboard:'/dashboard',nodes:'/nodes',ai:'/ai-connections',logs:'/logs',account:'/account',admin:'/admin'};
const adminPaths={dashboard:'/admin',users:'/admin/users',usage:'/admin/usage',nodes:'/admin/nodes',operations:'/admin/operations',subscriptions:'/admin/subscriptions',system:'/admin/system'};
function adminTabForPath(){const p=location.pathname.replace(/\/+$/,'')||'/admin';return Object.entries(adminPaths).find(([,v])=>v===p)?.[0]||'dashboard'}
function adminButton(tab){const order=['dashboard','users','usage','nodes','operations','subscriptions','system'];return document.querySelectorAll('#adminTabs button')[Math.max(0,order.indexOf(tab))]}
function view(id,el,updateUrl=true){document.querySelectorAll('.view').forEach(x=>x.classList.add('hidden'));document.getElementById(id).classList.remove('hidden');document.querySelectorAll('.nav').forEach(x=>x.classList.remove('active'));if(el)el.classList.add('active');if(updateUrl&&viewPaths[id]&&location.pathname!==viewPaths[id])history.pushState({view:id},'',viewPaths[id]);if(id==='logs')loadLogs();if(id==='admin'){const tab=adminTabForPath();adminTab(tab,adminButton(tab),false)}}
function routeFromLocation(){const p=location.pathname.replace(/\/+$/,'')||'/dashboard';if(p.startsWith('/admin'))return view('admin',adminNav,false);const id=Object.entries(viewPaths).find(([,v])=>v===p)?.[0]||'dashboard';const el=document.querySelector(`.nav[data-view="${id}"]`);view(id,el,false)}
window.addEventListener('popstate',routeFromLocation);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&state.user){refresh().catch(()=>{});startRealtime()}});
function closeModal(id){document.getElementById(id).classList.add('hidden')}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function timefmt(v){return v?new Date(v*1000).toLocaleString():'—'}
async function boot(){try{const me=await api('/auth/me');state.user=me.user;showApp();userName.textContent=state.user.name||state.user.email;userEmail.textContent=state.user.email;accountName.textContent=state.user.name||'Account';accountEmail.textContent=state.user.email;accountProvider.textContent=state.user.provider;if(['admin','super_admin'].includes(state.user.role))adminNav.classList.remove('hidden');await refresh();routeFromLocation();startRealtime()}catch(e){showAuth()}}
async function refresh(){const [n,l,a]=await Promise.all([api('/api/nodes'),api('/api/logs?limit=20'),api('/api/ai-connections')]);state.nodes=n.nodes;state.aiClients=a.clients||[];renderNodes();renderRecent(l.logs);renderAiClients();updateNodeMetrics();metricAiClients.textContent=state.aiClients.length}
function updateNodeMetrics(){metricPairedNodes.textContent=state.nodes.length;metricNodes.textContent=state.nodes.filter(x=>x.online).length}
function nodeRowHtml(n){return `<tr data-node-key="${encodeURIComponent(n.node_id)}"><td><b>${esc(n.name||n.node_id)}</b><div class="muted">${esc(n.node_id)}</div></td><td><span class="badge ${n.online?'online':'offline'}">${n.online?'Online':'Offline'}</span></td><td>${esc(n.permission_level||'operate')}</td><td class="path">${esc((n.allowed_roots||[]).join('\n')||'—')}</td><td>${esc(timefmt(n.last_seen||n.updated_at))}</td><td><button class="btn secondary" onclick="openNodeModal('${encodeURIComponent(n.node_id)}')">View</button></td></tr>`}
function renderNodes(){if(!state.nodes.length){nodeTable.innerHTML='<div class="card empty">No paired computers yet.</div>';updateNodeMetrics();return}nodeTable.innerHTML='<table class="table"><thead><tr><th>Computer</th><th>Status</th><th>Permission</th><th>Allowed folders</th><th>Last seen</th><th></th></tr></thead><tbody>'+state.nodes.map(nodeRowHtml).join('')+'</tbody></table>';updateNodeMetrics()}
function applyNodeUpsert(node){if(!node||!node.node_id)return;const i=state.nodes.findIndex(x=>x.node_id===node.node_id);const merged=i>=0?{...state.nodes[i],...node}:node;if(i>=0)state.nodes[i]=merged;else state.nodes.push(merged);const key=encodeURIComponent(node.node_id);const row=[...nodeTable.querySelectorAll('tr[data-node-key]')].find(x=>x.dataset.nodeKey===key);if(row)row.outerHTML=nodeRowHtml(merged);else{const body=nodeTable.querySelector('tbody');if(body)body.insertAdjacentHTML('beforeend',nodeRowHtml(merged));else renderNodes()}updateNodeMetrics();if(managedNodeId===node.node_id&&!nodeModal.classList.contains('hidden')){managePermissionText.textContent=({read:'Safe · Read-only',operate:'Standard · Operate',admin:'Full Access · Admin'})[merged.permission_level]||merged.permission_level||'Standard';manageRootsText.textContent=(merged.allowed_roots||[]).join('\n')||'—'}}
function applyNodeRemove(nodeId){state.nodes=state.nodes.filter(x=>x.node_id!==nodeId);const key=encodeURIComponent(nodeId);const row=[...nodeTable.querySelectorAll('tr[data-node-key]')].find(x=>x.dataset.nodeKey===key);if(row)row.remove();if(!state.nodes.length)renderNodes();else updateNodeMetrics();if(managedNodeId===nodeId){closeModal('nodeModal');managedNodeId=null}}
let eventSocket=null,eventReconnectTimer=null,eventHeartbeatTimer=null,eventWatchdogTimer=null,eventEverConnected=false,eventReconnectDelay=1000,eventLastAck=0;
function clearRealtimeTimers(){clearTimeout(eventReconnectTimer);clearInterval(eventHeartbeatTimer);clearInterval(eventWatchdogTimer);eventReconnectTimer=eventHeartbeatTimer=eventWatchdogTimer=null}
function stopRealtime(){clearRealtimeTimers();eventEverConnected=false;const socket=eventSocket;eventSocket=null;if(socket){socket.onclose=null;try{socket.close()}catch{}}}
function scheduleRealtimeReconnect(){if(!state.user||eventReconnectTimer)return;const delay=Math.min(eventReconnectDelay,30000);eventReconnectDelay=Math.min(eventReconnectDelay*2,30000);eventReconnectTimer=setTimeout(()=>{eventReconnectTimer=null;startRealtime()},delay+Math.floor(Math.random()*350))}
function startRealtime(){if(!state.user)return;if(eventSocket&&(eventSocket.readyState===WebSocket.OPEN||eventSocket.readyState===WebSocket.CONNECTING))return;const protocol=location.protocol==='https:'?'wss:':'ws:';const socket=new WebSocket(`${protocol}//${location.host}/ws/events`);eventSocket=socket;socket.onopen=()=>{const recovered=eventEverConnected;eventEverConnected=true;eventReconnectDelay=1000;eventLastAck=Date.now();clearInterval(eventHeartbeatTimer);clearInterval(eventWatchdogTimer);eventHeartbeatTimer=setInterval(()=>{if(socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'heartbeat'}))},20000);eventWatchdogTimer=setInterval(()=>{if(socket.readyState===WebSocket.OPEN&&Date.now()-eventLastAck>55000)socket.close(4000,'heartbeat timeout')},10000);if(recovered)refresh().catch(()=>{})};socket.onmessage=e=>{eventLastAck=Date.now();let message;try{message=JSON.parse(e.data)}catch{return}if(message.type==='node.upsert')applyNodeUpsert(message.node);else if(message.type==='node.remove')applyNodeRemove(message.node_id)};socket.onerror=()=>{};socket.onclose=()=>{if(eventSocket===socket)eventSocket=null;clearInterval(eventHeartbeatTimer);clearInterval(eventWatchdogTimer);eventHeartbeatTimer=eventWatchdogTimer=null;scheduleRealtimeReconnect()}}
function durationfmt(ms){ms=Math.max(0,Number(ms)||0);const sec=Math.floor(ms/1000),h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60),ss=sec%60;return h?`${h}h ${m}m ${ss}s`:m?`${m}m ${ss}s`:`${ss}s`}
function taskStatusBadge(s){return `<span class="badge ${s==='running'?'online':s==='failed'?'offline':'coming'}">${esc(s)}</span>`}
async function loadTaskRuns(){const d=await api('/api/task-runs?limit=100'),runs=d.runs||[];const total=runs.reduce((a,r)=>a+(Number(r.duration_ms)||0),0),steps=runs.reduce((a,r)=>a+(r.steps||[]).length,0);taskRunSummary.innerHTML=`<div class="card"><div class="muted">Task runs</div><div class="metric">${runs.length}</div></div><div class="card"><div class="muted">Subtasks</div><div class="metric">${steps}</div></div><div class="card"><div class="muted">Recorded time</div><div class="metric" style="font-size:22px">${durationfmt(total)}</div></div>`;taskRunTable.innerHTML=runs.length?runs.map(r=>`<div class="card" style="margin-bottom:12px"><div style="display:flex;justify-content:space-between;gap:12px"><div><b>${esc(r.title)}</b><div class="muted">${esc(r.node_id)} · ${esc(timefmt(r.started_at))}</div></div><div style="text-align:right">${taskStatusBadge(r.status)}<div style="margin-top:6px;font-weight:700">${esc(durationfmt(r.duration_ms))}</div></div></div><table class="table" style="margin-top:12px"><tbody>${(r.steps||[]).map(x=>`<tr><td style="width:35%"><b>${esc(x.action)}</b></td><td>${esc(x.status)}</td><td style="text-align:right">${esc(durationfmt(x.duration_ms))}</td></tr>`).join('')}</tbody></table></div>`).join(''):'<div class="card empty">No Task Runs recorded yet.</div>'}
function renderRecent(logs){recentLogs.innerHTML=logs.length?'<table class="table"><tbody>'+logs.slice(0,8).map(l=>`<tr><td>${esc(timefmt(l.created_at))}</td><td><b>${esc(l.action)}</b><div class="muted">${esc(l.target||'')}</div></td></tr>`).join('')+'</tbody></table>':'<div class="empty">No activity yet.</div>'}
async function loadLogs(){const q=new URLSearchParams({limit:'200'});if(logAction.value)q.set('action',logAction.value);if(logTarget.value)q.set('target',logTarget.value);const d=await api('/api/logs?'+q);logTable.innerHTML=d.logs.length?'<table class="table"><thead><tr><th>Time</th><th>Action</th><th>Target</th><th>Details</th></tr></thead><tbody>'+d.logs.map(l=>`<tr><td>${esc(timefmt(l.created_at))}</td><td>${esc(l.action)}</td><td>${esc(l.target||'')}</td><td><pre class="details">${esc(JSON.stringify(l.details||{},null,2))}</pre></td></tr>`).join('')+'</tbody></table>':'<div class="card empty">No matching activity.</div>'}
function renderAiClients(){if(!state.aiClients.length){aiClientTable.innerHTML='<div class="empty">No OAuth clients registered yet.</div>';return}aiClientTable.innerHTML='<table class="table"><thead><tr><th>Client</th><th>Registered</th></tr></thead><tbody>'+state.aiClients.map(c=>`<tr><td><b>${esc(c.client_name||'MCP Client')}</b></td><td>${esc(timefmt(c.created_at))}</td></tr>`).join('')+'</tbody></table>'}
let managedNodeId=null;
function openNodeModal(id){managedNodeId=decodeURIComponent(id);const n=state.nodes.find(x=>x.node_id===managedNodeId);if(!n)return;manageNodeNameInput.value=n.name||n.node_id;managePermissionText.textContent=({read:'Safe · Read-only',operate:'Standard · Operate',admin:'Full Access · Admin'})[n.permission_level]||n.permission_level||'Standard';manageRootsText.textContent=(n.allowed_roots||[]).join('\n')||'—';manageLogs.textContent='Click Refresh logs to load the latest local Lucas Node log.';nodeModal.classList.remove('hidden')}
async function saveNodeName(){if(!managedNodeId)return;const name=manageNodeNameInput.value.trim();if(!name){toast('Computer name is required');return}const d=await api('/api/nodes/'+encodeURIComponent(managedNodeId)+'/config',{method:'PUT',body:JSON.stringify({name})});const n=state.nodes.find(x=>x.node_id===managedNodeId);if(n)applyNodeUpsert({...n,name:d.name||name});manageNodeNameInput.value=d.name||name;toast('Computer name updated')}
async function loadNodeLogs(){if(!managedNodeId)return;try{const d=await api('/api/nodes/'+encodeURIComponent(managedNodeId)+'/logs?limit=250');manageLogs.textContent=(d.lines||[]).join('\n')||'No log lines yet.'}catch(e){manageLogs.textContent=e.message}}
async function unpairNode(){if(!managedNodeId||!confirm('Unpair this computer? It will need a new pairing code to reconnect.'))return;const nodeId=managedNodeId;await api('/api/nodes/'+encodeURIComponent(nodeId),{method:'DELETE'});applyNodeRemove(nodeId);toast('Computer node unpaired')}
async function copyMcpUrl(){const u='https://lucasmcp.com/mcp';mcpUrl.value=u;try{await navigator.clipboard.writeText(u);toast('MCP URL copied')}catch{mcpUrl.select();document.execCommand('copy');toast('MCP URL copied')}}
function openAiModal(){aiModal.classList.remove('hidden');aiModalUrl.value='https://lucasmcp.com/mcp';updateAiHelp()}
function updateAiHelp(){const n=aiClientType.value;const tips={ChatGPT:'Create a custom MCP app, use the Lucas MCP URL, choose OAuth, then scan tools.',Claude:'Add Lucas as a remote MCP connector and use OAuth when prompted.',Gemini:'Add Lucas through an MCP-compatible integration and authorize with Lucas OAuth.',Cursor:'Add a remote MCP server using the Lucas MCP URL and complete OAuth authorization.',Codex:'Configure Lucas as a remote MCP server using the URL shown above.','Claude Code':'Configure Lucas as a remote MCP server using the URL shown above.','Other MCP client':'Use Streamable HTTP with the Lucas MCP URL. OAuth metadata and dynamic client registration are published automatically.'};aiHelp.textContent=tips[n]||tips['Other MCP client']}
function openPairModal(){pairResult.classList.add('hidden');pairModal.classList.remove('hidden')}
async function createPairCode(){const d=await api('/api/nodes/pair',{method:'POST',body:JSON.stringify({})});pairCode.textContent=d.pairing_code;pairCommand.textContent=`Open Lucas Settings on the Windows PC and enter pairing code ${d.pairing_code}. Lucas will identify the computer automatically.`;pairResult.classList.remove('hidden')}
function adminMetric(label,value){return `<div class="card"><div class="muted">${esc(label)}</div><div class="metric">${esc(value)}</div></div>`}
async function adminTab(tab,el,updateUrl=true){if(updateUrl){const p=adminPaths[tab]||'/admin';if(location.pathname!==p)history.pushState({adminTab:tab},'',p)}document.querySelectorAll('#adminTabs button').forEach(b=>{b.classList.remove('primary');b.classList.add('secondary')});if(el){el.classList.remove('secondary');el.classList.add('primary')}adminContent.innerHTML='<div class="card empty">Loading…</div>';try{if(tab==='dashboard'){const d=await api('/api/admin/dashboard');adminContent.innerHTML=`<div class="grid">${adminMetric('Total users',d.users)}${adminMetric('Active users · 7d',d.active_users_7d)}${adminMetric('Online nodes',d.online_nodes)}${adminMetric('Operations today',d.operations_today)}${adminMetric('Operations · 30d',d.operations_30d)}${adminMetric('Paid users',d.paid_users)}</div><div class="card" style="margin-top:16px"><h3>Recent activity</h3>${d.recent.length?'<table class="table"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Target</th></tr></thead><tbody>'+d.recent.map(r=>`<tr><td>${esc(timefmt(r.created_at))}</td><td>${esc(r.email||'—')}</td><td>${esc(r.action)}</td><td>${esc(r.target||'—')}</td></tr>`).join('')+'</tbody></table>':'<div class="empty">No activity.</div>'}</div>`}else if(tab==='users'){const d=await api('/api/admin/users');adminContent.innerHTML=`<div class="toolbar"><input id="adminUserSearch" class="input" placeholder="Search email or name"><button class="btn secondary" onclick="adminSearchUsers()">Search</button></div><div id="adminUsersTable">${renderAdminUsers(d.users)}</div>`}else if(tab==='usage'){const d=await api('/api/admin/usage');adminContent.innerHTML=`<div class="grid">${adminMetric('Requests · 30d',d.requests_30d)}${adminMetric('Operations · 30d',d.operations_30d)}${adminMetric('Execution · 30d',Math.round(d.execution_seconds_30d)+'s')}${adminMetric('Success rate',d.success_rate+'%')}${adminMetric('Failed · 30d',d.errors_30d)}${adminMetric('Files / Shell / Git',(d.by_tool.files||0)+' / '+(d.by_tool.shell||0)+' / '+(d.by_tool.git||0))}</div><div class="card" style="margin-top:16px"><h3>Top users · 30d</h3><table class="table"><thead><tr><th>User</th><th>Operations</th></tr></thead><tbody>${d.top_users.map(r=>`<tr><td>${esc(r.email)}</td><td>${esc(r.n)}</td></tr>`).join('')}</tbody></table></div>`}else if(tab==='nodes'){const d=await api('/api/admin/nodes');adminContent.innerHTML=d.nodes.length?`<table class="table"><thead><tr><th>Node</th><th>Owner</th><th>Platform</th><th>Status</th><th>Allowed folders</th><th>Last seen</th></tr></thead><tbody>${d.nodes.map(n=>`<tr><td><b>${esc(n.name)}</b><div class="muted">${esc(n.node_id)}</div></td><td>${esc(n.owner||'—')}</td><td>${esc(n.platform)}</td><td><span class="badge ${n.online?'online':'offline'}">${n.online?'Online':'Offline'}</span></td><td>${esc(n.allowed_folder_count)}</td><td>${esc(timefmt(n.updated_at))}</td></tr>`).join('')}</tbody></table>`:'<div class="card empty">No nodes.</div>'}else if(tab==='operations'){const d=await api('/api/admin/operations?limit=300');adminContent.innerHTML=`<div class="toolbar"><input id="adminOpUser" class="input" placeholder="User"><input id="adminOpAction" class="input" placeholder="Tool / action"><button class="btn secondary" onclick="adminFilterOps()">Filter</button></div><div id="adminOpsTable">${renderAdminOps(d.operations)}</div>`}else if(tab==='subscriptions'){const d=await api('/api/admin/subscriptions');adminContent.innerHTML=`<table class="table"><thead><tr><th>User</th><th>Plan</th><th>Status</th><th>Provider</th><th>Ends</th></tr></thead><tbody>${d.subscriptions.map(s=>`<tr><td>${esc(s.email)}</td><td>${esc(s.plan)}</td><td>${esc(s.status)}</td><td>${esc(s.billing_provider||'—')}</td><td>${esc(timefmt(s.ends_at))}</td></tr>`).join('')}</tbody></table>`}else if(tab==='system'){const d=await api('/api/admin/system');adminContent.innerHTML=`<div class="grid">${adminMetric('Gateway',d.gateway)}${adminMetric('Database',d.database)}${adminMetric('Online nodes',d.online_nodes)}${adminMetric('Total nodes',d.total_nodes)}${adminMetric('Users',d.users)}${adminMetric('Server time',new Date(d.server_time*1000).toLocaleString())}</div>`}}catch(e){adminContent.innerHTML=`<div class="error">${esc(e.message)}</div>`}}
function renderAdminUsers(rows){return rows.length?'<table class="table"><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Plan</th><th>Nodes</th><th>Ops 30d</th><th>Last active</th></tr></thead><tbody>'+rows.map(u=>`<tr style="cursor:pointer" onclick="showAdminUser('${u.id}')"><td><b>${esc(u.email)}</b><div class="muted">${esc(u.name||'')}</div></td><td>${esc(u.role)}</td><td>${esc(u.status)}</td><td>${esc(u.plan)}</td><td>${esc(u.node_count)}</td><td>${esc(u.operations_30d)}</td><td>${esc(timefmt(u.last_login_at))}</td></tr>`).join('')+'</tbody></table>':'<div class="card empty">No users.</div>'}
async function adminSearchUsers(){const d=await api('/api/admin/users?q='+encodeURIComponent(adminUserSearch.value));adminUsersTable.innerHTML=renderAdminUsers(d.users)}
function renderAdminOps(rows){return rows.length?'<table class="table"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Target</th><th>Status</th></tr></thead><tbody>'+rows.map(o=>`<tr><td>${esc(timefmt(o.created_at))}</td><td>${esc(o.email||'—')}</td><td>${esc(o.action)}</td><td>${esc(o.target||'—')}</td><td>${esc(o.status)}</td></tr>`).join('')+'</tbody></table>':'<div class="card empty">No operations.</div>'}
async function adminFilterOps(){const q=new URLSearchParams({limit:'300'});if(adminOpUser.value)q.set('user',adminOpUser.value);if(adminOpAction.value)q.set('action',adminOpAction.value);const d=await api('/api/admin/operations?'+q);adminOpsTable.innerHTML=renderAdminOps(d.operations)}
async function saveAdminUser(id){await api('/api/admin/users/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify({status:adminDetailStatus.value,plan:adminDetailPlan.value})});toast('User updated');await showAdminUser(id)}
async function showAdminUser(id){const d=await api('/api/admin/users/'+encodeURIComponent(id));const u=d.user;adminUserDetail.innerHTML=`<h3>${esc(u.email)}</h3><div class="grid">${adminMetric('Plan',d.subscription.plan)}${adminMetric('Nodes',d.nodes.length)}${adminMetric('Operations · 30d',d.usage.last30||0)}</div><div class="card" style="margin-top:14px"><div class="row"><div><b>Role</b><div>${esc(u.role)}</div></div><div><b>Status</b><select id="adminDetailStatus"><option value="active" ${u.status==='active'?'selected':''}>active</option><option value="disabled" ${u.status==='disabled'?'selected':''}>disabled</option></select></div><div><b>Plan</b><select id="adminDetailPlan"><option value="free" ${d.subscription.plan==='free'?'selected':''}>free</option><option value="pro" ${d.subscription.plan==='pro'?'selected':''}>pro</option><option value="team" ${d.subscription.plan==='team'?'selected':''}>team</option><option value="enterprise" ${d.subscription.plan==='enterprise'?'selected':''}>enterprise</option></select></div></div><div class="actions"><button class="btn primary" onclick="saveAdminUser('${u.id}')">Save account</button></div></div><h3 style="margin-top:18px">Nodes</h3>${d.nodes.length?'<table class="table"><tbody>'+d.nodes.map(n=>`<tr><td>${esc(n.name)}</td><td>${esc(n.permission_level)}</td><td>${esc(timefmt(n.updated_at))}</td></tr>`).join('')+'</tbody></table>':'<div class="empty">No nodes.</div>'}<h3 style="margin-top:18px">Recent operations</h3>${renderAdminOps(d.operations.map(o=>({...o,email:u.email,status:(o.details||{}).status||'success'})))}`;adminUserModal.classList.remove('hidden')}
boot();
</script>
</body></html>'''


def _auth_user(request: Request):
    token = ""
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        token = request.cookies.get("gwc_access_token", "")
    return gateway.auth.verify_token(token)


def _safe_details(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    blocked = {"password", "token", "access_token", "authorization", "cookie", "clipboard", "content"}
    return {k: ("[redacted]" if k.lower() in blocked else v) for k, v in data.items()}


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(gateway.db_path, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def _landing_html() -> str:
    css_marker = '/* Lucas public landing */'
    css_start = DASHBOARD_HTML.index(css_marker)
    css_end = DASHBOARD_HTML.index('</style>', css_start)
    landing_css = DASHBOARD_HTML[css_start:css_end]
    section_start = DASHBOARD_HTML.index('<section id="landing" class="landing">')
    section_end = DASHBOARD_HTML.index('\n<div id="auth"', section_start)
    landing = DASHBOARD_HTML[section_start:section_end]
    landing = landing.replace('onclick="openAuth()"', 'onclick="location.href=\'/dashboard\'"')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<meta name="theme-color" content="#05070d" />
<meta name="description" content="Lucas connects any MCP-compatible AI to any computer with secure, token-free execution." />
<title>Lucas — Any AI. Any Computer.</title>
<style>
*{{box-sizing:border-box}}html{{scroll-behavior:smooth;background:#05070d}}body{{margin:0;background:#05070d}}button{{font:inherit}}
{landing_css}
</style>
</head>
<body>{landing}</body>
</html>"""


def _dashboard_html() -> str:
    html = DASHBOARD_HTML
    turnstile_site_key = os.getenv("GWC_TURNSTILE_SITE_KEY", "").strip()
    html = html.replace("__TURNSTILE_SITE_KEY__", turnstile_site_key).replace("__TURNSTILE_CLASS__", "" if turnstile_site_key else "hidden")
    css_marker = '/* Lucas public landing */'
    css_start = html.index(css_marker)
    css_end = html.index('</style>', css_start)
    html = html[:css_start] + html[css_end:]
    section_start = html.index('<section id="landing" class="landing">')
    section_end = html.index('\n<div id="auth"', section_start)
    html = html[:section_start] + html[section_end + 1:]
    return html


async def home(request: Request):
    html = _landing_html()
    try:
        _auth_user(request)
        html = html.replace('Sign in <span>→</span>', 'Dashboard <span>→</span>', 1)
    except Exception:
        pass
    return HTMLResponse(html)


async def dashboard(_: Request):
    return HTMLResponse(_dashboard_html())


async def admin_page(request: Request):
    try:
        user = _auth_user(request)
    except Exception:
        return RedirectResponse("/dashboard", status_code=302)
    if user.role not in {"admin", "super_admin"}:
        return RedirectResponse("/dashboard", status_code=302)
    return HTMLResponse(_dashboard_html())


async def download_lucas_node(_: Request):
    return FileResponse(
        "/app/scripts/install-node.ps1",
        media_type="application/octet-stream",
        filename="Lucas-Node.ps1",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


async def download_lucas_launcher(_: Request):
    return FileResponse(
        "/app/scripts/Lucas-Node.bat",
        media_type="application/octet-stream",
        filename="Lucas-Node.bat",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


async def api_logout(_: Request):
    response = JSONResponse({"ok": True})
    response.delete_cookie("gwc_access_token")
    return response


async def api_nodes(request: Request):
    user = _auth_user(request)
    online = {n["node_id"]: n for n in gateway.registry.list(user.id)}
    with _db() as db:
        rows = db.execute("SELECT node_id,name,updated_at,permission_level,allowed_roots FROM nodes WHERE owner_user_id=? ORDER BY name", (user.id,)).fetchall()
    result = []
    for row in rows:
        live = online.pop(row["node_id"], None)
        if live:
            result.append(live)
        else:
            try:
                roots = json.loads(row["allowed_roots"] or "[]")
            except json.JSONDecodeError:
                roots = []
            result.append({"node_id": row["node_id"], "name": row["name"], "online": False, "updated_at": row["updated_at"], "permission_level": row["permission_level"] or "operate", "allowed_roots": roots})
    result.extend(online.values())
    return JSONResponse({"nodes": result})


async def api_pair_node(request: Request):
    user = _auth_user(request)
    body = await request.json()
    node_id = str(body.get("node_id", "")).strip()
    name = str(body.get("name") or node_id or "Windows PC").strip()
    ttl = max(60, min(int(body.get("ttl_seconds", 600)), 3600))
    code = f"{secrets.randbelow(1_000_000):06d}"
    gateway._pairings[code] = {"node_id": node_id or None, "name": name, "owner_user_id": user.id, "expires": time.time() + ttl}
    gateway.auth.audit(user.id, "node.pair_code", node_id or "pending")
    return JSONResponse({"node_id": node_id or None, "name": name, "pairing_code": code, "expires_in": ttl})


async def api_node_config(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    record = await gateway.auth_store.record_for(node_id)
    if not record or record.get("owner_user_id") != user.id:
        return JSONResponse({"error": "Node not found"}, status_code=404)
    if request.method == "GET":
        try:
            roots = json.loads(record.get("allowed_roots") or "[]")
        except json.JSONDecodeError:
            roots = []
        return JSONResponse({"node_id": node_id, "name": record.get("name"), "permission_level": record.get("permission_level") or "operate", "allowed_roots": roots})
    body = await request.json()
    requested_keys = set(body.keys())
    if requested_keys - {"name"}:
        return JSONResponse({"error": "Only the display name can be changed on the website. Security settings are local-only."}, status_code=403)
    name = str(body.get("name") or "").strip()
    try:
        updated = await gateway.auth_store.update_name(node_id, user.id, name)
        live = gateway.registry.nodes.get(node_id)
        if live and live.owner_user_id == user.id:
            live.name = name
            node = next((item for item in gateway.registry.list(user.id) if item["node_id"] == node_id), None)
        else:
            try:
                roots = json.loads(updated.get("allowed_roots") or "[]")
            except json.JSONDecodeError:
                roots = []
            node = {"node_id": node_id, "name": name, "online": False, "updated_at": updated.get("updated_at"), "permission_level": updated.get("permission_level") or "operate", "allowed_roots": roots}
        gateway.auth.audit(user.id, "node.rename", node_id, {"name": name})
        if node:
            await gateway.dashboard_events.publish(user.id, "node.upsert", {"node": node})
        return JSONResponse({"ok": True, "node_id": node_id, "name": name})
    except (PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    body = await request.json()
    name = str(body.get("name") or record.get("name") or node_id).strip()
    permission = str(body.get("permission_level") or "operate").strip().lower()
    roots = [str(item).strip() for item in (body.get("allowed_roots") or []) if str(item).strip()]
    if permission not in {"read", "operate", "admin"}:
        return JSONResponse({"error": "Invalid permission level"}, status_code=400)
    if not roots:
        return JSONResponse({"error": "At least one allowed folder is required"}, status_code=400)
    try:
        if node_id in gateway.registry.nodes:
            await gateway.registry.rpc(node_id, user.id, "node.configure", {"node_name": name, "permission_level": permission, "allowed_roots": roots}, timeout=30)
        updated = await gateway.auth_store.update_config(node_id, user.id, name, permission, roots)
        live = gateway.registry.nodes.get(node_id)
        if live:
            live.name = name
            live.permission_level = permission
            live.allowed_roots = roots
        gateway.auth.audit(user.id, "node.configure", node_id, {"permission_level": permission, "allowed_roots": roots})
        return JSONResponse({"ok": True, "node_id": node_id})
    except (RuntimeError, PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_node_logs(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    try:
        gateway.registry.require_owned(node_id, user.id)
        limit = max(20, min(int(request.query_params.get("limit", "250")), 1000))
        result = await gateway.registry.rpc(node_id, user.id, "node.logs", {"limit": limit}, timeout=30)
        return JSONResponse(result)
    except (RuntimeError, PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_node_delete(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    removed = await gateway.auth_store.delete(node_id, user.id)
    connection = gateway.registry.nodes.get(node_id)
    if connection and connection.owner_user_id == user.id:
        await connection.websocket.close(code=4002)
    gateway.auth.audit(user.id, "node.unpair", node_id)
    await gateway.dashboard_events.publish(user.id, "node.remove", {"node_id": node_id})
    return JSONResponse({"removed": removed})


async def api_folders(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    path = request.query_params.get("path")
    try:
        gateway.registry.require_owned(node_id, user.id)
        result = await gateway.registry.rpc(node_id, user.id, "workspace.browse", {"path": path} if path else {})
        return JSONResponse(result)
    except (RuntimeError, PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_ai_connections(request: Request):
    user = _auth_user(request)
    with _db() as db:
        rows = db.execute(
            """SELECT c.client_id,c.client_name,c.created_at
               FROM oauth_clients c
               JOIN oauth_client_users cu ON cu.client_id=c.client_id
              WHERE cu.user_id=?
              ORDER BY cu.authorized_at DESC,c.created_at DESC""",
            (user.id,),
        ).fetchall()
    return JSONResponse({"clients": [{"client_id": r["client_id"], "client_name": r["client_name"], "created_at": r["created_at"]} for r in rows]})



async def api_task_runs(request: Request):
    user = _auth_user(request)
    limit = max(1, min(int(request.query_params.get("limit", "100")), 500))
    node_id = request.query_params.get("node_id", "").strip() or None
    return JSONResponse({"runs": gateway.task_runs.list_runs(user.id, node_id=node_id, limit=limit)})

async def api_logs(request: Request):
    user = _auth_user(request)
    limit = max(1, min(int(request.query_params.get("limit", "100")), 500))
    action = request.query_params.get("action", "").strip()
    target = request.query_params.get("target", "").strip()
    sql = "SELECT id,action,target,details,created_at FROM audit_logs WHERE user_id=?"
    params: list[object] = [user.id]
    if action:
        sql += " AND action LIKE ?"
        params.append(f"%{action}%")
    if target:
        sql += " AND target LIKE ?"
        params.append(f"%{target}%")
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _db() as db:
        rows = db.execute(sql, params).fetchall()
    logs = [{"id": r["id"], "action": r["action"], "target": r["target"], "details": _safe_details(r["details"]), "created_at": r["created_at"]} for r in rows]
    return JSONResponse({"logs": logs})


async def brand_asset(request: Request):
    name = str(request.path_params.get("name") or "")
    if name not in {"lucas-logo-horizontal.png", "lucas-logo-square.png"}:
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(
        BRAND_ASSET_DIR / name,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


routes = [
    Route("/assets/{name:str}", brand_asset, methods=["GET"]),
    Route("/", home, methods=["GET"]),
    Route("/dashboard", dashboard, methods=["GET"]),
    Route("/nodes", dashboard, methods=["GET"]),
    Route("/ai-connections", dashboard, methods=["GET"]),
    Route("/logs", dashboard, methods=["GET"]),
    Route("/account", dashboard, methods=["GET"]),
    Route("/admin", admin_page, methods=["GET"]),
    Route("/admin/users", admin_page, methods=["GET"]),
    Route("/admin/usage", admin_page, methods=["GET"]),
    Route("/admin/nodes", admin_page, methods=["GET"]),
    Route("/admin/operations", admin_page, methods=["GET"]),
    Route("/admin/subscriptions", admin_page, methods=["GET"]),
    Route("/admin/system", admin_page, methods=["GET"]),
    Route("/download/Lucas-Node.ps1", download_lucas_node, methods=["GET"]),
    Route("/download/Lucas-Node.bat", download_lucas_launcher, methods=["GET"]),
    Route("/api/logout", api_logout, methods=["POST"]),
    Route("/api/nodes", api_nodes, methods=["GET"]),
    Route("/api/nodes/pair", api_pair_node, methods=["POST"]),
    Route("/api/nodes/{node_id}/config", api_node_config, methods=["GET", "PUT"]),
    Route("/api/nodes/{node_id}/logs", api_node_logs, methods=["GET"]),
    Route("/api/nodes/{node_id}", api_node_delete, methods=["DELETE"]),
    Route("/api/nodes/{node_id}/folders", api_folders, methods=["GET"]),
    Route("/api/ai-connections", api_ai_connections, methods=["GET"]),
    Route("/api/task-runs", api_task_runs, methods=["GET"]),
    Route("/api/logs", api_logs, methods=["GET"]),
    *admin_routes,
    Mount("/", app=gateway.app),
]

app = Starlette(routes=routes)


def main() -> None:
    uvicorn.run(app, host=gateway.settings.host, port=gateway.settings.port, log_level="info")


if __name__ == "__main__":
    main()
