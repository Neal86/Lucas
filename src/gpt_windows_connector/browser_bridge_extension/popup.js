let pendingHost='', panelWindowId=null;
chrome.windows.getCurrent().then(w=>{panelWindowId=w.id;});
async function render(){
  const s=await chrome.storage.local.get(['connected','paired','pairingCode','profileName','alias','browserType','paused','pendingSite']);
  const st=document.getElementById('status');st.textContent=s.paused?'AI control paused':s.connected?(s.paired?'Connected to Lucas':'Waiting for pairing'):'Lucas Node disconnected';st.className=s.connected&&s.paired?'ok':'warn';
  document.getElementById('profile').textContent=[s.browserType || 'chrome',s.profileName || s.alias].filter(Boolean).join(' · ');
  document.getElementById('code').textContent=s.connected&&!s.paired&&s.pairingCode?'Pairing code: '+s.pairingCode:'';
  document.getElementById('pause').textContent=s.paused?'Resume AI control':'Pause AI control';
  pendingHost=s.pendingSite || '';document.getElementById('site').hidden=!pendingHost;document.getElementById('siteName').textContent='AI requests website access: '+pendingHost;
}
function safe(fn){return async()=>{try{await fn();await render();}catch(error){document.getElementById('error').textContent=error.message;}};}
document.getElementById('pause').onclick=safe(async()=>{const {paused=false}=await chrome.storage.local.get('paused');await chrome.storage.local.set({paused:!paused});});
document.getElementById('once').onclick=safe(async()=>{const {temporaryHosts={}}=await chrome.storage.session.get('temporaryHosts');temporaryHosts[pendingHost]=Date.now()+10*60*1000;await chrome.storage.session.set({temporaryHosts});await chrome.storage.local.remove('pendingSite');});
for(const [id,key] of [['always','allowedHosts'],['block','blockedHosts']])document.getElementById(id).onclick=safe(async()=>{const data=await chrome.storage.local.get(key);await chrome.storage.local.set({[key]:[...new Set([...(data[key] || []),pendingHost])]});await chrome.storage.local.remove('pendingSite');});
document.getElementById('options').onclick=()=>chrome.runtime.openOptionsPage();
document.getElementById('reconnect').onclick=safe(async()=>{await chrome.runtime.sendMessage({type:'lucas_ui',action:'reconnect'});});
document.getElementById('panel').onclick=()=>{
  if(chrome.sidePanel && panelWindowId!=null){chrome.sidePanel.open({windowId:panelWindowId}).catch(error=>{document.getElementById('error').textContent=error.message;});}
  else chrome.tabs.create({url:chrome.runtime.getURL('sidepanel.html')});
};
chrome.storage.onChanged.addListener(render);render();
