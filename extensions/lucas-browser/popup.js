const $ = id => document.getElementById(id);
async function refresh() {
  const state = await chrome.runtime.sendMessage({type:'status'});
  $('status').textContent = state.status;
  const chosen=$('owner').value;
  $('owner').replaceChildren(...state.owners.map(o => { const x=document.createElement('option'); x.value=o.user_id; x.textContent=o.name||o.email||o.user_id; return x; }));
  if(state.owners.some(o=>o.user_id===chosen)) $('owner').value=chosen;
  $('sessions').replaceChildren(...state.sessions.map(s => { const x=document.createElement('li'); x.textContent=`${s.title||'Tab'} — ${s.session_id}`; return x; }));
  $('grant').disabled = !state.owners.length || !state.can_grant;
}
$('connect').onclick = async () => { await chrome.runtime.sendMessage({type:'pair',token:$('token').value,port:Number($('port').value)}); $('token').value=''; await refresh(); };
$('grant').onclick = async () => { const [tab]=await chrome.tabs.query({active:true,currentWindow:true}); const r=await chrome.runtime.sendMessage({type:'grant',owner_id:$('owner').value,tab_id:tab.id}); $('status').textContent=r.error||'Authorization requested'; setTimeout(refresh,300); };
$('revoke').onclick = async () => { await chrome.runtime.sendMessage({type:'revoke'}); await refresh(); };
refresh();

setInterval(refresh,1000);
