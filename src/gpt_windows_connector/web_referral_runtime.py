from __future__ import annotations

REFERRAL_SCRIPT = r"""<script>
async function loadReferralView(){try{const e=document.getElementById('referralError');if(e)e.classList.add('hidden');const s=await api('/api/referrals/summary');referralUrl.value=s.url||'';referralCode.textContent=s.code||'—';referralTotal.textContent=Number(s.total_referrals||0).toLocaleString();referralPaid.textContent=Number(s.paid_referrals||0).toLocaleString();referralEarned.textContent=Number(s.earned_requests||0).toLocaleString()}catch(err){const e=document.getElementById('referralError');if(e){e.textContent=err?.message||String(err);e.classList.remove('hidden')}}}
async function copyReferralLink(){const e=document.getElementById('referralUrl');if(!e)return;try{await navigator.clipboard.writeText(e.value);toast('Invite link copied')}catch{e.select();document.execCommand('copy');toast('Invite link copied')}}
window.loadReferralView=loadReferralView;window.copyReferralLink=copyReferralLink;
</script>"""
