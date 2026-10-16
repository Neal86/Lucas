"""Dashboard account bootstrap and response-side session presentation.

The browser cannot undo a dispatched logout or its cookie effects. Ownership
only controls which response may update this page's current account display.
"""
from __future__ import annotations

SESSION_LOGOUT_SCRIPT = r'''
let sessionLogoutSequence=0;
async function logout(){
  const sequence=++sessionLogoutSequence,generation=loginGeneration,user=state.user;
  // A same-account bootstrap replaces its object without starting a new login.
  const sameAccount=()=>state.user===user||!!user?.id&&state.user?.id===user.id;
  const owns=()=>sequence===sessionLogoutSequence&&generation===loginGeneration&&sameAccount();
  await api('/api/logout',{method:'POST'},owns).catch(()=>{});
  if(owns())showAuth();
}
'''

SESSION_BOOT_SCRIPT = r'''
let sessionBootstrapSequence=0;
function invalidateSessionBootstrap(){sessionBootstrapSequence++}
function resetSessionAccountPresentation(){
  if(typeof resetReferralAccountData==='function')resetReferralAccountData();
  document.getElementById('adminNav')?.classList.add('hidden');
  for(const id of ['userName','userEmail','accountName','accountEmail','accountProvider']){
    const element=document.getElementById(id);if(element)element.textContent='';
  }
}
async function boot(isCurrent=()=>true){
  if(!isCurrent())return;
  const sequence=++sessionBootstrapSequence,generation=loginGeneration;
  let owner=state.user;
  const owns=()=>sequence===sessionBootstrapSequence&&generation===loginGeneration&&state.user===owner&&isCurrent();
  let me;
  try{me=await api('/auth/me',{},owns)}catch(e){if(owns())showAuth();return}
  if(!owns())return;
  if(state.user?.id!==me.user?.id){
    if(typeof resetDashboardAccountData==='function')resetDashboardAccountData();
    resetSessionAccountPresentation();
  }
  if(state.user!==me.user){
    if(typeof invalidateComputerManagementSession==='function')invalidateComputerManagementSession();
    if(typeof invalidateAiConnectionDeletes==='function')invalidateAiConnectionDeletes();
    if(typeof invalidateAiConnectionEditor==='function')invalidateAiConnectionEditor();
    if(typeof invalidateAdminReads==='function')invalidateAdminReads();
    if(window.hideGettingStarted)window.hideGettingStarted();
    stopRealtime();
  }
  owner=me.user;state.user=owner;showApp();
  const qp=new URLSearchParams(location.search),googleMetaId=qp.get('meta_registration');
  if(googleMetaId&&window.lucasMetaTrackOnce){
    lucasMetaTrackOnce('google-registration:'+googleMetaId,'CompleteRegistration',{content_name:'Google Registration',status:'completed'},googleMetaId);
    qp.delete('meta_registration');history.replaceState(history.state,'',location.pathname+(qp.toString()?'?'+qp.toString():'')+location.hash);
  }
  userName.textContent=state.user.name||state.user.email;userEmail.textContent=state.user.email;
  accountName.textContent=state.user.name||'Account';accountEmail.textContent=state.user.email;accountProvider.textContent=state.user.provider;
  adminNav.classList.toggle('hidden',!['admin','super_admin'].includes(state.user.role));
  try{await refresh(owns)}catch(e){
    if(!owns())return;
    console.error('Dashboard refresh failed',e);
    toast(WEB_LANG==='zh'?'部分数据加载失败，请刷新重试':'Some dashboard data failed to load. Refresh to retry.');
  }
  if(!owns())return;
  routeFromLocation();startRealtime();maybeStartOnboarding();
}
'''
