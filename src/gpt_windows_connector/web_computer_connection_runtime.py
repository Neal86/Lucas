"""Own connection-modal responses without cancelling dispatched access requests."""
from __future__ import annotations

COMPUTER_CONNECTION_SCRIPT = r'''
function openConnectModal(){
  invalidateComputerConnection(false);
  connectNodeId.value='';connectCode.value='';connectResult.textContent='';connectResult.classList.add('hidden');
  connectModal.classList.remove('hidden');
  const owns=computerConnectionViewOwner();setTimeout(()=>{if(owns())connectNodeId.focus()},50);
}
function openConnectModalForNode(id){openConnectModal();connectNodeId.value=decodeURIComponent(id);connectCode.focus()}
let computerConnectionGeneration=0,computerConnectionSequence=0,computerConnectionInputGeneration=0,computerConnectionBusy=false;
function renderComputerConnectionBusy(){
  const button=document.getElementById('connectSubmit');
  if(button){button.disabled=computerConnectionBusy;button.setAttribute('aria-busy',String(computerConnectionBusy))}
}
function invalidateComputerConnection(hide=true){
  computerConnectionGeneration++;computerConnectionBusy=false;renderComputerConnectionBusy();
  if(hide)document.getElementById('connectModal')?.classList.add('hidden');
}
function computerConnectionViewOwner(){
  const generation=computerConnectionGeneration,login=loginGeneration,user=state.user;
  return ()=>!!user&&user===state.user&&login===loginGeneration&&generation===computerConnectionGeneration&&!connectModal.classList.contains('hidden');
}
function computerConnectionInputChanged(){
  computerConnectionInputGeneration++;
  connectResult.textContent='';connectResult.classList.add('hidden');
}
async function requestNodeAccess(){
  if(computerConnectionBusy)return;
  const node_id=connectNodeId.value.trim(),connection_code=connectCode.value.trim();
  if(!node_id){toast(wt('Node ID is required'));return}
  if(!/^\d{8}$/.test(connection_code)){toast(wt('Enter the 8-digit Connection Code'));return}
  const viewOwns=computerConnectionViewOwner();if(!viewOwns())return;
  const sequence=++computerConnectionSequence,inputGeneration=computerConnectionInputGeneration;
  const ownsLifecycle=()=>viewOwns()&&sequence===computerConnectionSequence;
  const ownsResponse=()=>ownsLifecycle()&&inputGeneration===computerConnectionInputGeneration&&connectNodeId.value.trim()===node_id&&connectCode.value.trim()===connection_code;
  computerConnectionBusy=true;renderComputerConnectionBusy();
  connectResult.textContent=wt('Sending access request…');connectResult.classList.remove('hidden');
  try{
    const d=await api('/api/nodes/request-access',{method:'POST',body:JSON.stringify({node_id,connection_code})},ownsResponse);
    if(!ownsResponse())return;
    if(d.authorized){connectResult.textContent=wt('Access approved on the target computer.');await refresh(ownsResponse)}
    else if(d.pending){connectResult.textContent=wt('Access request sent. Waiting for local approval on the target computer.');await refresh(ownsResponse)}
    else connectResult.textContent=wt(d.error==='invalid connection code'?'Connection Code is incorrect.':'Access request was not accepted.');
  }catch(e){if(ownsResponse())connectResult.textContent=e.message}
  finally{if(ownsLifecycle()){computerConnectionBusy=false;renderComputerConnectionBusy();if(!ownsResponse()){connectResult.textContent='';connectResult.classList.add('hidden')}}}
}
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!connectModal.classList.contains('hidden'))closeModal('connectModal')});
'''
