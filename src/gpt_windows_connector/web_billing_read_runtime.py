"""Session-owned billing reads and the shared dashboard quota snapshot.

This module only projects read results. Paid mutations and entitlement policy
remain in their existing modules; no dispatched request is cancelled or retried.
"""
from __future__ import annotations

BILLING_READ_SCRIPT = r'''
// Both billing-summary and dashboard reads compete for this one snapshot owner.
let billingSnapshotSequence=0;
function beginBillingSnapshotRead(isCurrent=()=>true){
  const sequence=++billingSnapshotSequence,generation=loginGeneration,user=state.user;
  return ()=>!!user&&state.user===user&&generation===loginGeneration&&sequence===billingSnapshotSequence&&isCurrent();
}
function billingText(id,text){const element=billingEl(id);if(element)element.textContent=text}
function clearBillingFeedback(){
  for(const id of ['billingError','billingNotice']){
    const element=billingEl(id);if(element){element.textContent='';element.classList.add('hidden')}
  }
}
function renderBillingSnapshot(s){
  clearBillingFeedback();
  billingText('billingPlan',s?s.plan_name+(s.expansion_quantity?' + '+s.expansion_quantity+' Pack'+(s.expansion_quantity===1?'':'s'):''):'—');
  billingText('billingRenew',s?.renewal_at?'Renews '+new Date(s.renewal_at*1000).toLocaleDateString():'');
  billingText('billingPrice',!s?'—':s.plan==='free'?'$0':s.billing_interval==='year'?'$'+Number(s.billing_total||0).toFixed(2)+'/yr':'$'+Number(s.billing_total||s.monthly_price||0).toFixed(2)+'/mo');
  renderOperationUsage('billingRequests',s,'billingRequestsBar');
  billingText('billingComputers',s?Number(s.nodes_used||0)+' / '+Number(s.node_limit||0)+(Number(s.nodes_connected||0)>Number(s.node_limit||0)?' active · '+Number(s.nodes_connected||0)+' connected':''):'—');
  billingText('billingAi',s?Number(s.ai_accounts_used||0)+' / '+Number(s.ai_account_limit||0):'—');
  if(s?.beta_free)billingNotice(s.existing_paid_subscription?'Lucas Beta is free during testing. An existing paid subscription is on record; review it separately to avoid future charges.':'Lucas Beta is free during testing. Plans and limits may change.');
  else if(s&&!s.billing_configured)billingNotice('Stripe checkout is not active yet.');
}
function commitBillingSnapshot(snapshot,isCurrent){
  if(!isCurrent())return false;
  state.billing=snapshot;
  renderBillingSnapshot(snapshot);
  renderOperationUsage('metricRequests',snapshot);
  return true;
}
function resetBillingAccountData(){
  billingSnapshotSequence++;
  state.billing=null;
  renderBillingSnapshot(null);
}
async function loadBillingView(){
  const isCurrent=beginBillingSnapshotRead();
  if(!isCurrent())return;
  const error=billingEl('billingError');if(error){error.textContent='';error.classList.add('hidden')}
  try{
    const snapshot=await api('/api/billing/summary',{},isCurrent);
    commitBillingSnapshot(snapshot,isCurrent);
  }catch(error){if(isCurrent())billingShowError(error)}
}
'''
