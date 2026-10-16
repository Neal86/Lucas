"""Account-owned referral presentation; server awards and copy effects unchanged."""
from test_session_lifecycle import run_session_cases


def test_referral_read_ownership(tmp_path):
    run_session_cases(tmp_path, REFERRAL_CASES, "referral-response-ownership")


REFERRAL_CASES = r'''
function referral(mark){return {url:'https://fixture.invalid/refer?ref='+mark,code:mark,total_referrals:2,paid_referrals:1,earned_requests:6000}}
async function setReferral(f,mark){const i=f.requests.length,p=f.call('loadReferralView()');f.respond(i,referral(mark));await p}
for(const language of ['en','zh-CN']){
 lifecycleTest(language+': current referral uses actual summary shape and GET',async()=>{const f=fixture(language);await setReferral(f,'CURRENT');assert.equal(f.ctx.referralUrl.value,'https://fixture.invalid/refer?ref=CURRENT');assert.equal(f.ctx.referralCode.textContent,'CURRENT');assert.equal(f.ctx.referralTotal.textContent,'2');assert.equal(f.ctx.referralPaid.textContent,'1');assert.equal(f.ctx.referralEarned.textContent,Number(6000).toLocaleString());assert.equal(f.requests[0].options.method,undefined)});
 for(const outcome of [200,401,503,'network'])lifecycleTest(language+': stale referral result cannot affect replacement account '+outcome,async()=>{const f=fixture(language),old=f.call('loadReferralView()');account(f);await setReferral(f,'NEW');if(outcome==='network')f.requests[0].reject(new Error('OLD'));else f.respond(0,outcome===200?referral('OLD'):{error:'OLD'},outcome);await old;assert.equal(f.ctx.referralCode.textContent,'NEW');assert.equal(f.call('state.user.id'),'user-b');assert.equal(f.ctx.referralError.textContent,'')});
 for(const oldFirst of [true,false])lifecycleTest(language+': same-account latest referral request owns both completion orders '+oldFirst,async()=>{const f=fixture(language),old=f.call('loadReferralView()'),fresh=f.call('loadReferralView()');if(oldFirst){f.respond(0,referral('OLD'));await old;assert.notEqual(f.ctx.referralCode.textContent,'OLD')}f.respond(1,referral('NEW'));await fresh;if(!oldFirst){f.respond(0,referral('OLD'));await old}assert.equal(f.ctx.referralCode.textContent,'NEW')});
 lifecycleTest(language+': latest failed referral keeps committed display but never accepts older fallback',async()=>{const f=fixture(language);await setReferral(f,'COMMITTED');const old=f.call('loadReferralView()'),fresh=f.call('loadReferralView()');f.respond(2,{error:'CURRENT'},503);await fresh;f.respond(1,referral('OLD'));await old;assert.equal(f.ctx.referralCode.textContent,'COMMITTED');assert.equal(f.ctx.referralError.textContent,'CURRENT');await setReferral(f,'RETRY');assert.equal(f.ctx.referralError.textContent,'')});
 lifecycleTest(language+': delayed stale JSON401 cannot sign out current account',async()=>{const f=fixture(language),old=f.call('loadReferralView()');let deliver;f.requests[0].resolve({status:401,ok:false,json:()=>new Promise(r=>deliver=r)});await settle();account(f);await setReferral(f,'NEW');deliver({error:'OLD'});await old;assert.equal(f.call('state.user.id'),'user-b');assert.equal(f.ctx.referralCode.textContent,'NEW')});
 lifecycleTest(language+': current401 clears referral and guest reads do not dispatch',async()=>{const f=fixture(language);await setReferral(f,'OLD');const p=f.call('loadReferralView()');f.respond(1,{error:'CURRENT'},401);await p;assert.equal(f.call('state.user'),null);assert.equal(f.ctx.referralUrl.value,'');assert.equal(f.ctx.referralCode.textContent,'—');assert.equal(f.ctx.referralError.textContent,'');await f.call('loadReferralView()');assert.equal(f.requests.length,2)});
 lifecycleTest(language+': direct account bootstrap clears old summary before next view read',async()=>{const f=fixture(language);await setReferral(f,'OLD');const p=f.call('boot()');f.respond(1,currentMe('user-b'));await settle();assert.equal(f.ctx.referralUrl.value,'');assert.equal(f.ctx.referralCode.textContent,'—');reply(f,2,'CURRENT');await p});
}
'''
