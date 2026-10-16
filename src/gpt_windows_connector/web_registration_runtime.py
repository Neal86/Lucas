"""Dashboard email-registration UI state and asynchronous response guards.

Mode changes share the login generation. These are client-side guards only:
ignoring an obsolete response cannot undo an email or server-issued session.
"""
from __future__ import annotations

REGISTRATION_SCRIPT = r'''
let pendingVerificationEmail='',pendingRegistrationMetaEventId='',resendCooldownTimer=null,resendCooldownUntil=0,resendVerificationBusy=false;
let registrationBusy=false,registrationVerifyBusy=false;

function renderRegistrationButtons(){
  const submit=document.querySelector('#registerForm button[onclick="registerUser()"]');
  const verify=document.querySelector('#verifyForm button[onclick="verifyEmail()"]');
  if(submit)submit.disabled=registrationBusy;
  if(verify)verify.disabled=registrationVerifyBusy||resendVerificationBusy;
  renderResendVerificationButton();
}
function renderResendVerificationButton(){
  const b=document.getElementById('resendVerificationBtn');if(!b)return;
  const left=Math.max(0,Math.ceil((resendCooldownUntil-Date.now())/1000));
  b.disabled=!pendingVerificationEmail||resendVerificationBusy||registrationVerifyBusy||left>0;
  b.classList.toggle('disabled-btn',b.disabled);
  if(resendVerificationBusy)b.textContent=wt('Sending…');
  else if(left>0)b.textContent=wt('Resend code')+` (${left}${WEB_LANG==='zh'?'秒':'s'})`;
  else b.textContent=wt('Resend code');
}
function startResendCooldown(seconds=60){
  const generation=loginGeneration,email=pendingVerificationEmail,metaId=pendingRegistrationMetaEventId;
  resendCooldownUntil=Date.now()+seconds*1000;
  clearInterval(resendCooldownTimer);renderResendVerificationButton();
  const timer=setInterval(()=>{
    if(generation!==loginGeneration||email!==pendingVerificationEmail||metaId!==pendingRegistrationMetaEventId||timer!==resendCooldownTimer)return;
    renderResendVerificationButton();
    if(Date.now()>=resendCooldownUntil){clearInterval(timer);resendCooldownTimer=null}
  },250);
  resendCooldownTimer=timer;
}
function resetRegistrationVerification(){
  pendingVerificationEmail='';pendingRegistrationMetaEventId='';
  clearInterval(resendCooldownTimer);resendCooldownTimer=null;resendCooldownUntil=0;
  registrationBusy=false;registrationVerifyBusy=false;resendVerificationBusy=false;
  const code=document.getElementById('verifyCode'),email=document.getElementById('verifyEmailLabel');
  if(code)code.value='';if(email)email.textContent='';
  document.getElementById('verifyForm')?.classList.add('hidden');
  renderRegistrationButtons();
}
function registrationFormActive(id){
  return !document.getElementById('auth').classList.contains('hidden')&&!document.getElementById(id).classList.contains('hidden');
}
async function registerUser(){
  if(registrationBusy||registrationVerifyBusy||resendVerificationBusy||!registrationFormActive('registerForm'))return;
  const generation=loginGeneration,widget=document.querySelector('[name="cf-turnstile-response"]'),metaId=metaEventId('email_registration');
  const payload={name:regName.value,email:regEmail.value,password:regPassword.value,website:regWebsite.value,turnstile_token:widget?.value||'',meta_event_id:metaId};
  pendingRegistrationMetaEventId=metaId;
  // The selected form remains current while boot hides the enclosing auth panel.
  const isCurrent=()=>generation===loginGeneration&&pendingRegistrationMetaEventId===metaId&&!registerForm.classList.contains('hidden');
  authError('');registrationBusy=true;renderRegistrationButtons();
  try{
    const d=await api('/auth/register',{method:'POST',body:JSON.stringify(payload)},isCurrent);
    if(!isCurrent())return;
    if(d.verification_required){
      pendingVerificationEmail=d.email;verifyEmailLabel.textContent=d.email;verifyCode.value='';
      registrationBusy=false;renderRegistrationButtons();
      registerForm.classList.add('hidden');verifyForm.classList.remove('hidden');
      startResendCooldown(60);return;
    }
    if(window.lucasMetaTrack)lucasMetaTrack('CompleteRegistration',{content_name:'Email Registration',status:'completed'},metaId);
    await boot(isCurrent);
    if(isCurrent())resetRegistrationVerification();
  }catch(e){if(isCurrent()){authError(e.message);if(window.turnstile)window.turnstile.reset()}}
  finally{if(isCurrent()){registrationBusy=false;renderRegistrationButtons()}}
}
async function verifyEmail(){
  if(registrationVerifyBusy||resendVerificationBusy||!pendingVerificationEmail||!registrationFormActive('verifyForm'))return;
  const generation=loginGeneration,email=pendingVerificationEmail,metaId=pendingRegistrationMetaEventId||metaEventId('email_registration');
  const payload={email,code:verifyCode.value,meta_event_id:metaId};
  pendingRegistrationMetaEventId=metaId;
  const isCurrent=()=>generation===loginGeneration&&email===pendingVerificationEmail&&metaId===pendingRegistrationMetaEventId&&!verifyForm.classList.contains('hidden');
  authError('');registrationVerifyBusy=true;renderRegistrationButtons();
  try{
    await api('/auth/verify-email',{method:'POST',body:JSON.stringify(payload)},isCurrent);
    if(!isCurrent())return;
    if(window.lucasMetaTrack)lucasMetaTrack('CompleteRegistration',{content_name:'Email Registration',status:'verified'},metaId);
    await boot(isCurrent);
    if(isCurrent())resetRegistrationVerification();
  }catch(e){if(isCurrent())authError(e.message)}
  finally{if(isCurrent()){registrationVerifyBusy=false;renderRegistrationButtons()}}
}
async function resendVerification(){
  if(resendVerificationBusy||registrationVerifyBusy||Date.now()<resendCooldownUntil||!pendingVerificationEmail||!registrationFormActive('verifyForm'))return;
  const generation=loginGeneration,email=pendingVerificationEmail,metaId=pendingRegistrationMetaEventId;
  const isCurrent=()=>generation===loginGeneration&&email===pendingVerificationEmail&&metaId===pendingRegistrationMetaEventId&&!verifyForm.classList.contains('hidden');
  authError('');resendVerificationBusy=true;renderRegistrationButtons();
  try{
    await api('/auth/resend-verification',{method:'POST',body:JSON.stringify({email})},isCurrent);
    if(!isCurrent())return;
    toast(wt('Verification code resent'));startResendCooldown(60);
  }catch(e){if(isCurrent())authError(e.message)}
  finally{if(isCurrent()){resendVerificationBusy=false;renderRegistrationButtons()}}
}
'''
