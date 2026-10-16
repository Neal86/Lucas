"""Computer-management presentation ownership, separate from Node authorization.

Retiring a view never cancels, reverses or retries an already dispatched rename
or activation. Log access and all actual local policy remain on the backend.
"""
from __future__ import annotations

COMPUTER_MANAGEMENT_SCRIPT = r'''let managedNodeId=null;
let computerManagementGeneration=0,computerNameSequence=0,computerNameInputGeneration=0,computerNameBusy=false;
let computerLogsSequence=0,computerLogsBusy=false,computerActivationGeneration=0;
const computerActivations=new Map(),computerActivationCommits=new Map(),computerNameCommits=new Map();
function renderComputerManagementBusy(){
  for(const [id,busy] of [['manageNodeSave',computerNameBusy],['manageNodeLogsRefresh',computerLogsBusy]]){
    const button=document.getElementById(id);if(button){button.disabled=busy;button.setAttribute('aria-busy',String(busy))}
  }
}
function invalidateComputerManagement(){
  computerManagementGeneration++;managedNodeId=null;computerNameBusy=false;computerLogsBusy=false;
  document.getElementById('nodeModal')?.classList.add('hidden');
  for(const id of ['manageNodeIdText','managePermissionText','manageRootsText','manageLogs']){
    const element=document.getElementById(id);if(element)element.textContent='';
  }
  renderComputerManagementBusy();
}
function invalidateComputerManagementSession(clearCommits=true){
  if(clearCommits){computerNameCommits.clear();computerActivationCommits.clear()}
  invalidateComputerManagement();computerActivationGeneration++;computerActivations.clear();renderNodes();
}
function computerManagementOwner(){
  const generation=computerManagementGeneration,login=loginGeneration,user=state.user,nodeId=managedNodeId;
  return ()=>!!user&&state.user===user&&login===loginGeneration&&generation===computerManagementGeneration&&nodeId===managedNodeId&&!nodeModal.classList.contains('hidden');
}
function computerManagementNameChanged(){computerNameInputGeneration++}
function openNodeModal(id){
  const nodeId=decodeURIComponent(id),n=state.nodes.find(x=>x.node_id===nodeId);
  invalidateComputerManagement();if(!n||!state.user)return;
  managedNodeId=nodeId;manageNodeName.value=n.display_name||n.name||n.node_id;
  manageNodeIdText.textContent=n.node_id;managePermissionText.textContent=accessMode(n);
  manageRootsText.textContent=(n.allowed_roots||[]).join('\n')||'—';
  manageLogs.textContent='Full Access is required to read Node logs.';nodeModal.classList.remove('hidden');
}
async function saveNodeName(){
  if(computerNameBusy||!managedNodeId)return;
  const viewOwns=computerManagementOwner();if(!viewOwns())return;
  const nodeId=managedNodeId,name=manageNodeName.value.trim(),sequence=++computerNameSequence,inputGeneration=computerNameInputGeneration;
  const ownsLifecycle=()=>viewOwns()&&sequence===computerNameSequence;
  const ownsResponse=()=>ownsLifecycle()&&inputGeneration===computerNameInputGeneration&&manageNodeName.value.trim()===name;
  const user=state.user,login=loginGeneration,commit={};computerNameCommits.set(nodeId,commit);
  const ownsCommit=()=>state.user===user&&loginGeneration===login&&computerNameCommits.get(nodeId)===commit;
  computerNameBusy=true;renderComputerManagementBusy();
  try{
    const d=await api('/api/nodes/'+encodeURIComponent(nodeId)+'/name',{method:'PUT',body:JSON.stringify({name})},ownsResponse);
    if(ownsCommit()){
      const n=state.nodes.find(x=>x.node_id===nodeId);if(n)n.display_name=d.display_name||n.name||n.node_id;
      invalidateDashboardSnapshotReads();renderNodes();
    }
    if(ownsResponse())toast('Computer name saved');
  }catch(e){if(ownsResponse())toast(e.message)}
  finally{
    if(computerNameCommits.get(nodeId)===commit)computerNameCommits.delete(nodeId);
    if(ownsLifecycle()){computerNameBusy=false;renderComputerManagementBusy()}
  }
}
async function loadNodeLogs(){
  if(!managedNodeId)return;
  const viewOwns=computerManagementOwner();if(!viewOwns())return;
  const nodeId=managedNodeId,sequence=++computerLogsSequence;
  const owns=()=>viewOwns()&&sequence===computerLogsSequence;
  computerLogsBusy=true;renderComputerManagementBusy();
  try{
    const d=await api('/api/nodes/'+encodeURIComponent(nodeId)+'/logs?limit=250',{},owns);
    if(owns())manageLogs.textContent=(d.lines||[]).join('\n')||'No log lines yet.';
  }catch(e){if(owns())manageLogs.textContent=e.message}
  finally{if(owns()){computerLogsBusy=false;renderComputerManagementBusy()}}
}
function computerActivationButtonState(nodeId){return computerActivations.has(encodeURIComponent(nodeId))?' disabled aria-busy="true"':' aria-busy="false"'}
async function activateNode(nodeId){
  if(computerActivations.has(nodeId)||!state.user)return;
  const user=state.user,login=loginGeneration,generation=computerActivationGeneration,attempt={};
  const owns=()=>state.user===user&&login===loginGeneration&&generation===computerActivationGeneration&&computerActivations.get(nodeId)===attempt;
  const ownsCommit=()=>state.user===user&&login===loginGeneration&&computerActivationCommits.get(nodeId)===attempt;
  computerActivations.set(nodeId,attempt);computerActivationCommits.set(nodeId,attempt);renderNodes();
  try{
    await api('/api/nodes/'+nodeId+'/activate',{method:'POST'},owns);
    if(owns())toast('Computer activated');
    if(ownsCommit())await refresh(ownsCommit);
  }catch(e){if(owns())toast(e.message)}
  finally{
    if(computerActivationCommits.get(nodeId)===attempt)computerActivationCommits.delete(nodeId);
    if(owns()){computerActivations.delete(nodeId);renderNodes()}
  }
}
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!nodeModal.classList.contains('hidden'))closeModal('nodeModal')});
'''
