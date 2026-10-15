const $ = id => document.getElementById(id);
let actionSequence=0, refreshSequence=0;
const errorText=error=>error?.message||String(error||'Unknown error');

async function refresh() {
  const sequence=++refreshSequence;
  try {
    const state=await chrome.runtime.sendMessage({type:'status'});
    if(state?.error) throw Error(state.error);
    if(typeof state?.status!=='string'||!Array.isArray(state.owners)||!Array.isArray(state.sessions)) throw Error('Invalid status response');
    if(sequence!==refreshSequence) return;
    $('status').textContent=state.status;
    const chosen=$('owner').value;
    $('owner').replaceChildren(...state.owners.map(o => { const x=document.createElement('option'); x.value=o.user_id; x.textContent=o.name||o.email||o.user_id; return x; }));
    if(state.owners.some(o=>o.user_id===chosen)) $('owner').value=chosen;
    $('sessions').replaceChildren(...state.sessions.map(s => { const x=document.createElement('li'); x.textContent=`${s.title||'Tab'} — ${s.session_id}`; return x; }));
    $('grant').disabled=!state.owners.length||!state.can_grant;
  } catch(error) {
    if(sequence!==refreshSequence) return;
    $('status').textContent=`Unable to refresh status: ${errorText(error)}`;
    $('grant').disabled=true;
  }
}

async function request(message) {
  const response=await chrome.runtime.sendMessage(message);
  if(response?.error) throw Error(response.error);
  if(response?.ok!==true) throw Error('No confirmation received. Try again.');
}

async function runAction(label,operation,successMessage) {
  const sequence=++actionSequence;
  ++refreshSequence;
  const current=()=>sequence===actionSequence;
  try {
    await operation(current);
    if(!current()) return;
    // Polling only updates connection status; an action error lasts until a
    // newer user action succeeds. Late replies cannot erase newer feedback.
    $('action-error').textContent='';
    if(successMessage) {
      $('status').textContent=successMessage;
      setTimeout(()=>{if(current()) void refresh();},300);
    } else await refresh();
  } catch(error) {
    if(current()) $('action-error').textContent=`${label}: ${errorText(error)}`;
  }
}

$('connect').onclick=()=>runAction('Pairing request failed',async current=>{
  const token=$('token').value;
  await request({type:'pair',token,port:Number($('port').value)});
  // This acknowledges the connection attempt, not authentication by the Node.
  if(current()&&$('token').value===token) $('token').value='';
});
$('grant').onclick=()=>runAction('Tab authorization failed',async current=>{
  const owner=$('owner').value;
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  if(!current()) return;
  if(!Number.isInteger(tab?.id)||tab.id<0) throw Error('No active tab is available. Choose a tab and try again.');
  await request({type:'grant',owner_id:owner,tab_id:tab.id});
},'Authorization requested');
$('revoke').onclick=()=>runAction('Revocation failed',()=>request({type:'revoke'}));
void refresh();
setInterval(()=>void refresh(),1000);
