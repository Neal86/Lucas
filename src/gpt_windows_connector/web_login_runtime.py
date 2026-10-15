"""Dashboard password-login and email-verification UI state.

A generation identifies the current login attempt. Mode changes invalidate
pending responses so an interrupted request cannot restore the old UI.
"""
from __future__ import annotations

LOGIN_SCRIPT = r'''
let pendingLoginChallenge='',loginResendCooldownTimer=null,loginResendCooldownUntil=0,loginResendBusy=false;
let loginGeneration=0,loginBusy=false,loginVerifyBusy=false,pendingLoginCredential=null;

async function rememberCredential(credential){
  try{
    if(credential.remember){
      localStorage.setItem('lucas_login_email',credential.email.trim());
      if(window.PasswordCredential&&navigator.credentials){
        await navigator.credentials.store(new PasswordCredential({id:credential.email.trim(),password:credential.password,name:credential.email.trim()}));
      }
    }else localStorage.removeItem('lucas_login_email');
  }catch{}
}
function renderLoginButtons(){
  const submit=document.querySelector('#loginForm button[onclick="login()"]');
  const verify=document.querySelector('#loginVerifyForm button[onclick="verifyLogin()"]');
  if(submit)submit.disabled=loginBusy;
  if(verify)verify.disabled=loginVerifyBusy||loginResendBusy;
  renderLoginResendButton();
}
function renderLoginResendButton(){
  const b=document.getElementById('loginResendBtn');if(!b)return;
  const left=Math.max(0,Math.ceil((loginResendCooldownUntil-Date.now())/1000));
  b.disabled=!pendingLoginChallenge||loginResendBusy||loginVerifyBusy||left>0;
  if(loginResendBusy)b.textContent=WEB_LANG==='zh'?'发送中…':'Sending…';
  else if(left>0)b.textContent=WEB_LANG==='zh'?`重新发送 (${left}秒)`:`Resend (${left}s)`;
  else b.textContent=WEB_LANG==='zh'?'重新发送':'Resend';
}
function startLoginResendCooldown(seconds=60){
  loginResendCooldownUntil=Date.now()+seconds*1000;
  clearInterval(loginResendCooldownTimer);renderLoginResendButton();
  loginResendCooldownTimer=setInterval(()=>{
    renderLoginResendButton();
    if(Date.now()>=loginResendCooldownUntil){clearInterval(loginResendCooldownTimer);loginResendCooldownTimer=null}
  },250);
}
function resetLoginVerification(){
  loginGeneration++;
  pendingLoginChallenge='';pendingLoginCredential=null;
  clearInterval(loginResendCooldownTimer);
  loginResendCooldownTimer=null;loginResendCooldownUntil=0;
  loginBusy=false;loginVerifyBusy=false;loginResendBusy=false;
  const code=document.getElementById('loginVerifyCode'),email=document.getElementById('loginVerifyEmailLabel');
  if(code)code.value='';if(email)email.textContent='';
  document.getElementById('loginVerifyForm')?.classList.add('hidden');
  renderLoginButtons();
}
async function completeLogin(){
  resetLoginVerification();
  const generation=loginGeneration;
  loginBusy=true;renderLoginButtons();
  try{await boot(()=>generation===loginGeneration)}
  finally{if(generation===loginGeneration){loginBusy=false;renderLoginButtons()}}
}
async function login(){
  if(loginBusy||loginVerifyBusy||pendingLoginChallenge||loginForm.classList.contains('hidden'))return;
  const generation=loginGeneration;
  const credential={email:loginEmail.value,password:loginPassword.value,remember:!!document.getElementById('loginRemember')?.checked};
  authError('');loginBusy=true;renderLoginButtons();
  try{
    const d=await api('/auth/login',{method:'POST',body:JSON.stringify(credential)});
    if(generation!==loginGeneration)return;
    if(d.verification_required){
      pendingLoginChallenge=d.challenge_id;pendingLoginCredential=credential;
      loginVerifyCode.value='';loginVerifyEmailLabel.textContent=d.email||credential.email;
      loginForm.classList.add('hidden');registerForm.classList.add('hidden');loginVerifyForm.classList.remove('hidden');
      startLoginResendCooldown(60);
      setTimeout(()=>{if(generation===loginGeneration&&pendingLoginChallenge)loginVerifyCode.focus()},50);
      return;
    }
    await rememberCredential(credential);
    if(generation!==loginGeneration)return;
    await completeLogin();
  }catch(e){if(generation===loginGeneration)authError(e.message)}
  finally{if(generation===loginGeneration){loginBusy=false;renderLoginButtons()}}
}
async function resendLoginVerification(){
  if(loginResendBusy||loginVerifyBusy||Date.now()<loginResendCooldownUntil||!pendingLoginChallenge)return;
  const generation=loginGeneration,challenge=pendingLoginChallenge;
  authError('');loginResendBusy=true;renderLoginButtons();
  try{
    await api('/auth/login/resend',{method:'POST',body:JSON.stringify({challenge_id:challenge})});
    if(generation!==loginGeneration||challenge!==pendingLoginChallenge)return;
    toast(WEB_LANG==='zh'?'登录验证码已重新发送':'Login verification code resent');startLoginResendCooldown(60);
  }catch(e){if(generation===loginGeneration)authError(e.message)}
  finally{if(generation===loginGeneration){loginResendBusy=false;renderLoginButtons()}}
}
async function verifyLogin(){
  if(loginVerifyBusy||loginResendBusy||!pendingLoginChallenge)return;
  const generation=loginGeneration,challenge=pendingLoginChallenge,credential=pendingLoginCredential;
  authError('');loginVerifyBusy=true;renderLoginButtons();
  try{
    await api('/auth/login/verify',{method:'POST',body:JSON.stringify({challenge_id:challenge,code:loginVerifyCode.value})});
    if(generation!==loginGeneration||challenge!==pendingLoginChallenge)return;
    await rememberCredential(credential);
    if(generation!==loginGeneration)return;
    await completeLogin();
  }catch(e){if(generation===loginGeneration)authError(e.message)}
  finally{if(generation===loginGeneration){loginVerifyBusy=false;renderLoginButtons()}}
}
function cancelLoginVerification(){showRegister(false)}
function togglePassword(id,button){
  const input=document.getElementById(id),show=input.type==='password';input.type=show?'text':'password';
  button.textContent=show?'🙈':'👁';button.setAttribute('aria-label',show?'Hide password':'Show password');button.title=show?'Hide password':'Show password';
}
'''
