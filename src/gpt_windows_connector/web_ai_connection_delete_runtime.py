"""Response-side AI deletion ownership without changing OAuth revocation."""
from __future__ import annotations

AI_CONNECTION_DELETE_SCRIPT = r'''
let aiDeleteGeneration=0;
const aiDeleteAttempts=new Map(),aiDeleteCommits=new Map();
function invalidateAiConnectionDeletes(clearCommits=true){aiDeleteGeneration++;aiDeleteAttempts.clear();if(clearCommits)aiDeleteCommits.clear();renderAiClients()}
function aiConnectionDeleteButtonState(clientId){return aiDeleteAttempts.has(clientId)?' disabled aria-busy="true"':' aria-busy="false"'}
async function deleteAiConnection(id){
  const clientId=decodeURIComponent(id);
  if(aiDeleteAttempts.has(clientId))return;
  const c=state.aiClients.find(x=>x.client_id===clientId),name=c?.display_name||c?.client_name||'MCP Client';
  if(!clientId||!c){toast('AI connection not found. Refresh and try again.');return}
  const user=state.user,login=loginGeneration,generation=aiDeleteGeneration;
  const ownsSession=()=>!!user&&state.user===user&&login===loginGeneration&&generation===aiDeleteGeneration;
  if(!ownsSession())return;
  if(!window.confirm(`Delete AI connection ${name}?\n\nThis removes the Lucas OAuth connection. You can reconnect it later.`))return;
  if(!ownsSession())return;
  const attempt={};aiDeleteAttempts.set(clientId,attempt);aiDeleteCommits.set(clientId,attempt);renderAiClients();
  const ownsCommit=()=>state.user===user&&login===loginGeneration&&aiDeleteCommits.get(clientId)===attempt;
  const owns=()=>ownsSession()&&aiDeleteAttempts.get(clientId)===attempt;
  try{
    await api('/api/ai-connections/'+encodeURIComponent(clientId),{method:'DELETE'},owns);
    if(ownsCommit()){
      state.aiClients=state.aiClients.filter(x=>x.client_id!==clientId);
      invalidateDashboardSnapshotReads();renderAiClients();metricAiClients.textContent=state.aiClients.length;
    }
    if(owns())toast('AI connection deleted');
  }catch(e){if(owns())toast(e.message)}
  finally{
    if(aiDeleteCommits.get(clientId)===attempt)aiDeleteCommits.delete(clientId);
    if(owns()){aiDeleteAttempts.delete(clientId);renderAiClients()}
  }
}
'''
