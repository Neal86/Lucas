"""Own AI metadata editor responses without cancelling dispatched saves."""
from __future__ import annotations

AI_CONNECTION_EDITOR_SCRIPT = r'''let managedAiClientId=null,aiEditorGeneration=0,aiEditorSequence=0,aiEditorInputGeneration=0,aiEditorBusy=false;
function renderAiConnectionSaveBusy(){
  const button=document.getElementById('aiManageSave');
  if(button){button.disabled=aiEditorBusy;button.setAttribute('aria-busy',String(aiEditorBusy))}
}
function invalidateAiConnectionEditor(hide=true){
  aiEditorGeneration++;managedAiClientId=null;aiEditorBusy=false;renderAiConnectionSaveBusy();
  if(hide)document.getElementById('aiManageModal')?.classList.add('hidden');
}
function aiConnectionEditorOwner(){
  const generation=aiEditorGeneration,login=loginGeneration,user=state.user,clientId=managedAiClientId;
  return ()=>!!user&&user===state.user&&login===loginGeneration&&generation===aiEditorGeneration&&clientId===managedAiClientId;
}
function aiConnectionEditorInputChanged(){aiEditorInputGeneration++}
function editAiConnection(id){
  const clientId=decodeURIComponent(id),c=state.aiClients.find(x=>x.client_id===clientId);
  invalidateAiConnectionEditor();if(!c||!state.user)return;
  managedAiClientId=clientId;aiManageName.value=c.display_name||c.client_name||'MCP Client';aiManageNote.value=c.note||'';
  aiManageModal.classList.remove('hidden');
  const owns=aiConnectionEditorOwner();setTimeout(()=>{if(owns()&&!aiManageModal.classList.contains('hidden'))aiManageName.focus()},50);
}
async function saveAiConnection(){
  if(aiEditorBusy||!managedAiClientId||aiManageModal.classList.contains('hidden'))return;
  const viewOwns=aiConnectionEditorOwner();if(!viewOwns())return;
  const clientId=managedAiClientId,display_name=aiManageName.value.trim(),note=aiManageNote.value.trim();
  const sequence=++aiEditorSequence,inputGeneration=aiEditorInputGeneration;
  const ownsLifecycle=()=>viewOwns()&&sequence===aiEditorSequence;
  const ownsResponse=()=>ownsLifecycle()&&inputGeneration===aiEditorInputGeneration&&aiManageName.value.trim()===display_name&&aiManageNote.value.trim()===note;
  aiEditorBusy=true;renderAiConnectionSaveBusy();
  try{
    await api('/api/ai-connections/'+encodeURIComponent(clientId),{method:'PUT',body:JSON.stringify({display_name,note})},ownsResponse);
    if(!ownsResponse())return;
    // The current successful save hides its editor but owns its follow-up read.
    // Explicit Close, reopening, navigation and auth changes invalidate that owner.
    aiManageModal.classList.add('hidden');
    await refresh(ownsResponse);if(ownsResponse())toast('AI connection saved');
  }catch(e){if(ownsResponse())toast(e.message)}
  finally{if(ownsLifecycle()){aiEditorBusy=false;renderAiConnectionSaveBusy()}}
}
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!aiManageModal.classList.contains('hidden'))closeModal('aiManageModal')});
'''
