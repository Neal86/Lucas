"""OAuth sign-in view. Authentication belongs exclusively to login_policy."""
from html import escape
from urllib.parse import urlencode


def login_page(request_id: str) -> str:
    # Attribute escaping and URL encoding keep opaque server state out of JS.
    return _PAGE.replace("__REQUEST_ID__", escape(request_id, quote=True)).replace(
        "__RESUME_URL__", escape("/oauth/authorize/resume?" + urlencode({"request_id": request_id}), quote=True)
    )


_PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in to Lucas</title>
<style>
body{font:15px Segoe UI,Arial;background:#f6f7fb;padding:24px;color:#101828}
.card{max-width:440px;margin:8vh auto;background:white;border:1px solid #e4e7ec;border-radius:16px;padding:28px}
input:not([type=checkbox]){width:100%;box-sizing:border-box;padding:11px;margin:6px 0 14px;border:1px solid #d0d5dd;border-radius:9px}
button{width:100%;padding:11px;border:1px solid #d0d5dd;border-radius:9px;background:white;color:#101828;font-weight:650;cursor:pointer;margin-top:10px}
button.primary{background:#155eef;color:white;border-color:#155eef}button:disabled{opacity:.55;cursor:wait}
.remember{display:flex;gap:8px;margin:8px 0}.muted{color:#667085}#loginError{color:#b42318;white-space:pre-wrap}[hidden]{display:none!important}
</style></head><body><main class="card" data-resume-url="__RESUME_URL__">
<h1>Sign in to Lucas</h1><p class="muted">Sign in, then review the connection before authorizing it.</p>
<p id="loginError" role="alert" hidden></p>
<form id="loginForm"><label for="email">Email</label><input id="email" type="email" autocomplete="username" required>
<label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required>
<label class="remember"><input id="remember" type="checkbox" checked>Remember this device for 30 days</label>
<button class="primary" type="submit">Sign in and continue</button></form>
<form id="verifyForm" hidden><p>Enter the 6-digit verification code sent to <b id="verifyEmail"></b>.</p>
<label for="code">Verification code</label><input id="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required>
<button class="primary" type="submit">Verify and continue</button><button id="resendBtn" type="button">Resend</button>
<button id="backBtn" type="button">Back to sign in</button></form>
<form id="cancelForm" method="post" action="/oauth/authorize/cancel"><input type="hidden" name="request_id" value="__REQUEST_ID__"><button type="submit">Cancel connection</button></form>
<noscript><p>JavaScript is required for secure sign-in. You can still cancel this connection.</p></noscript>
</main><script>
(()=>{'use strict';
const el=id=>document.getElementById(id),login=el('loginForm'),verify=el('verifyForm'),resend=el('resendBtn');
let challenge='',busy=false,cooldown=0,timer=null;
function error(text){el('loginError').textContent=text;el('loginError').hidden=!text}
function render(){for(const button of document.querySelectorAll('#loginForm button,#verifyForm button'))button.disabled=busy;
 const left=Math.max(0,Math.ceil((cooldown-Date.now())/1000));resend.disabled=busy||left>0;resend.textContent=left?`Resend (${left}s)`:'Resend'}
function startCooldown(){cooldown=Date.now()+60000;clearInterval(timer);timer=setInterval(()=>{render();if(Date.now()>=cooldown){clearInterval(timer);timer=null}},250);render()}
async function api(path,body){const response=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 let data;try{data=await response.json()}catch{throw new Error('Unable to sign in. Please try again.')}
 if(!response.ok)throw new Error(data.error||'Unable to sign in. Please try again.');return data}
async function act(callback){if(busy)return;busy=true;error('');render();try{await callback()}catch(e){error(e.message)}finally{busy=false;render()}}
function resume(){el('password').value='';el('code').value='';challenge='';clearInterval(timer);window.location.replace(document.querySelector('main').dataset.resumeUrl)}
login.addEventListener('submit',event=>{event.preventDefault();act(async()=>{const data=await api('/auth/login',{email:el('email').value,password:el('password').value,remember:el('remember').checked});
 el('password').value='';if(data.verification_required){challenge=data.challenge_id;el('verifyEmail').textContent=data.email;login.hidden=true;verify.hidden=false;el('code').value='';startCooldown();el('code').focus()}else resume()})});
verify.addEventListener('submit',event=>{event.preventDefault();act(async()=>{await api('/auth/login/verify',{challenge_id:challenge,code:el('code').value});resume()})});
resend.addEventListener('click',()=>{if(Date.now()<cooldown||!challenge)return;act(async()=>{await api('/auth/login/resend',{challenge_id:challenge});el('code').value='';startCooldown()})});
el('backBtn').addEventListener('click',()=>{if(busy)return;challenge='';el('code').value='';clearInterval(timer);timer=null;cooldown=0;verify.hidden=true;login.hidden=false;error('');render();el('password').focus()});
el('cancelForm').addEventListener('submit',()=>{el('password').value='';el('code').value='';challenge='';clearInterval(timer)});
})();
</script></body></html>'''
