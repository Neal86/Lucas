"""Login verification runtime, composed explicitly after the core runtime."""

LOGIN_SCRIPT = r"""
let pendingLoginChallenge='',loginChallengeEmail='',loginChallengeExpiresAt=0;
let loginResendCooldownTimer=null,loginResendCooldownUntil=0,loginResendBusy=false;
const coreShowRegister=showRegister;
showRegister=function(v){
  if(v)cancelLoginVerification(false);
  coreShowRegister(v);
  document.getElementById('loginVerifyForm').classList.add('hidden');
  if(!v)restoreLoginChallenge();
};
async function rememberCredential(){
  try{
    if(loginRemember.checked){
      localStorage.setItem('lucas_login_email',loginEmail.value.trim());
      if(window.PasswordCredential&&navigator.credentials){
        await navigator.credentials.store(new PasswordCredential({id:loginEmail.value.trim(),password:loginPassword.value,name:loginEmail.value.trim()}));
      }
    }else localStorage.removeItem('lucas_login_email');
  }catch{}
}
function saveLoginChallenge(){
  try{sessionStorage.setItem('lucas_login_challenge',JSON.stringify({id:pendingLoginChallenge,email:loginChallengeEmail,expiresAt:loginChallengeExpiresAt,resendUntil:loginResendCooldownUntil}));}catch{}
}
function clearLoginChallenge(){try{sessionStorage.removeItem('lucas_login_challenge');}catch{}}
function showLoginVerification(){
  loginVerifyEmailLabel.textContent=loginChallengeEmail;
  loginForm.classList.add('hidden');
  registerForm.classList.add('hidden');
  document.getElementById('verifyForm').classList.add('hidden');
  loginVerifyForm.classList.remove('hidden');
}
function restoreLoginChallenge(){
  try{
    const raw=sessionStorage.getItem('lucas_login_challenge');
    if(!raw)return;
    const state=JSON.parse(raw);
    if(typeof state.id!=='string'||!state.id||!Number.isFinite(state.expiresAt)||Date.now()>=state.expiresAt){
      cancelLoginVerification(false);return;
    }
    pendingLoginChallenge=state.id;
    loginChallengeEmail=String(state.email||'');
    loginChallengeExpiresAt=state.expiresAt;
    loginResendCooldownUntil=Number.isFinite(state.resendUntil)?state.resendUntil:0;
    showLoginVerification();
    startLoginResendCooldown(Math.max(0,(loginResendCooldownUntil-Date.now())/1000));
  }catch{cancelLoginVerification(false);}
}
window.addEventListener('load',restoreLoginChallenge);
function renderLoginResendButton(){
  const b=document.getElementById('loginResendBtn');if(!b)return;
  const left=Math.max(0,Math.ceil((loginResendCooldownUntil-Date.now())/1000));
  b.disabled=loginResendBusy||left>0;
  if(loginResendBusy)b.textContent=WEB_LANG==='zh'?'发送中…':'Sending…';
  else if(left>0)b.textContent=WEB_LANG==='zh'?`重新发送 (${left}秒)`:`Resend (${left}s)`;
  else b.textContent=WEB_LANG==='zh'?'重新发送':'Resend';
}
function startLoginResendCooldown(seconds=60){
  loginResendCooldownUntil=Date.now()+seconds*1000;
  clearInterval(loginResendCooldownTimer);loginResendCooldownTimer=null;
  renderLoginResendButton();
  if(seconds>0)loginResendCooldownTimer=setInterval(()=>{
    renderLoginResendButton();
    if(Date.now()>=loginResendCooldownUntil){clearInterval(loginResendCooldownTimer);loginResendCooldownTimer=null;}
  },250);
}
function loginChallengeIsCurrent(){
  if(pendingLoginChallenge&&Date.now()<loginChallengeExpiresAt)return true;
  cancelLoginVerification(false);
  authError('Login verification session is missing');return false;
}
function loginChallengeError(error){
  if(['Login verification session expired','Verification code expired','Login verification session is missing','Login network changed. Please sign in again.','Too many verification attempts'].includes(error.message))cancelLoginVerification(false);
  authError(error.message);
}
async function login(){
  authError('');
  try{
    const d=await api('/auth/login',{method:'POST',body:JSON.stringify({email:loginEmail.value,password:loginPassword.value,remember:!!loginRemember.checked})});
    cancelLoginVerification(false);
    if(d.verification_required){
      pendingLoginChallenge=String(d.challenge_id||'');
      if(!pendingLoginChallenge)throw new Error('Login verification session is missing');
      loginChallengeEmail=String(d.email||loginEmail.value);
      loginChallengeExpiresAt=Date.now()+600000;
      startLoginResendCooldown(60);saveLoginChallenge();showLoginVerification();
      setTimeout(()=>loginVerifyCode.focus(),50);return;
    }
    await rememberCredential();await boot();
  }catch(e){authError(e.message);}
}
async function resendLoginVerification(){
  if(loginResendBusy||Date.now()<loginResendCooldownUntil)return;
  if(!loginChallengeIsCurrent())return;
  authError('');loginResendBusy=true;renderLoginResendButton();
  try{
    await api('/auth/login/resend',{method:'POST',body:JSON.stringify({challenge_id:pendingLoginChallenge})});
    loginChallengeExpiresAt=Date.now()+600000;
    startLoginResendCooldown(60);saveLoginChallenge();
    toast(WEB_LANG==='zh'?'登录验证码已重新发送':'Login verification code resent');
  }catch(e){loginChallengeError(e);}
  finally{loginResendBusy=false;renderLoginResendButton();}
}
async function verifyLogin(){
  authError('');if(!loginChallengeIsCurrent())return;
  try{
    await api('/auth/login/verify',{method:'POST',body:JSON.stringify({challenge_id:pendingLoginChallenge,code:loginVerifyCode.value})});
    await rememberCredential();cancelLoginVerification(false);await boot();
  }catch(e){loginChallengeError(e);}
}
function cancelLoginVerification(resetError=true){
  pendingLoginChallenge='';loginChallengeEmail='';loginChallengeExpiresAt=0;
  clearLoginChallenge();loginVerifyCode.value='';
  clearInterval(loginResendCooldownTimer);loginResendCooldownTimer=null;
  loginResendCooldownUntil=0;loginResendBusy=false;
  if(resetError)authError('');
  loginVerifyForm.classList.add('hidden');loginForm.classList.remove('hidden');renderLoginResendButton();
}
function togglePassword(id,button){
  const input=document.getElementById(id),show=input.type==='password';input.type=show?'text':'password';
  button.textContent=show?'🙈':'👁';button.setAttribute('aria-label',show?'Hide password':'Show password');button.title=show?'Hide password':'Show password';
}
"""
