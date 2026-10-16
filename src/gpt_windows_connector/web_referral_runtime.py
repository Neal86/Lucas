"""Referral summary presentation owned by the current account and read."""
from __future__ import annotations

REFERRAL_SCRIPT = r"""
let referralReadSequence=0;
function resetReferralAccountData(){
  referralReadSequence++;
  const url=document.getElementById('referralUrl');if(url)url.value='';
  for(const id of ['referralCode','referralTotal','referralPaid','referralEarned']){
    const element=document.getElementById(id);if(element)element.textContent='—';
  }
  const error=document.getElementById('referralError');if(error){error.textContent='';error.classList.add('hidden')}
}
async function loadReferralView(){
  const sequence=++referralReadSequence,generation=loginGeneration,user=state.user;
  const owns=()=>!!user&&state.user===user&&loginGeneration===generation&&sequence===referralReadSequence;
  if(!owns())return;
  const error=document.getElementById('referralError');if(error){error.textContent='';error.classList.add('hidden')}
  try{
    const summary=await api('/api/referrals/summary',{},owns);if(!owns())return;
    referralUrl.value=summary.url||'';referralCode.textContent=summary.code||'—';
    referralTotal.textContent=Number(summary.total_referrals||0).toLocaleString();
    referralPaid.textContent=Number(summary.paid_referrals||0).toLocaleString();
    referralEarned.textContent=Number(summary.earned_requests||0).toLocaleString();
  }catch(err){if(owns()&&error){error.textContent=err?.message||String(err);error.classList.remove('hidden')}}
}
async function copyReferralLink(){const e=document.getElementById('referralUrl');if(!e)return;try{await navigator.clipboard.writeText(e.value);toast('Invite link copied')}catch{e.select();document.execCommand('copy');toast('Invite link copied')}}
window.loadReferralView=loadReferralView;window.copyReferralLink=copyReferralLink;
"""
