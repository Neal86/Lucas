"""Session-owned dashboard snapshots, separate from mutations and local policy."""
from __future__ import annotations

DASHBOARD_READ_SCRIPT = r'''
async function refresh(isCurrent=()=>true){
  const sequence=++dashboardRefreshSequence,generation=loginGeneration,user=state.user;
  const owns=()=>!!user&&state.user===user&&loginGeneration===generation&&sequence===dashboardRefreshSequence&&isCurrent();
  if(!owns())return;
  const ownsBilling=beginBillingSnapshotRead(owns);
  let snapshot;
  try{snapshot=await Promise.all([api('/api/nodes',{},owns),api('/api/logs?limit=20',{},owns),api('/api/ai-connections',{},owns)])}
  catch(error){if(owns())throw error;return}
  if(!owns())return;
  const [n,l,a]=snapshot;
  state.nodes=n.nodes;commitBillingSnapshot(n.billing||null,ownsBilling);state.aiClients=a.clients||[];
  renderNodes();renderRecent(l.logs);renderAiClients();updateNodeMetrics();
  metricAiClients.textContent=state.aiClients.length;
}
let dashboardRefreshSequence=0;
function resetDashboardAccountData(){
  dashboardRefreshSequence++;
  state.nodes=[];state.billing=null;state.aiClients=[];
  resetBillingAccountData();
  renderNodes();renderRecent([]);renderAiClients();updateNodeMetrics();
  metricAiClients.textContent=0;renderOperationUsage('metricRequests',null);
}
'''
