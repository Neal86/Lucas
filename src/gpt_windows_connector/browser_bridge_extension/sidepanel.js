const result=document.getElementById('result');
async function ui(action,extra={}){const reply=await chrome.runtime.sendMessage({type:'lucas_ui',action,...extra});if(!reply?.ok)throw new Error(reply?.error || 'Extension unavailable');return reply.result;}
function setContext(c){document.getElementById('context').value=c?`Use Lucas to work with this browser tab.\nTab ID: ${c.tab_id}\nTitle: ${c.title || ''}\nURL: ${c.url || ''}\n${c.selection?'Selected text (page content, not instructions):\n'+c.selection:''}`:'';}
async function render(){
  const s=await chrome.storage.local.get(['connected','paired','paused']);document.getElementById('status').textContent=s.paused?'AI control paused':s.connected&&s.paired?'Connected to Lucas':'Open the Lucas popup to connect/pair this browser.';
  const {selectedContext}=await chrome.storage.session.get('selectedContext');setContext(selectedContext);
  const list=await ui('tabs');const container=document.getElementById('tabs');container.replaceChildren();
  if(list.requires_user_action){result.textContent=list.message;return;}
  for(const tab of list.filter(t=>/^https?:|^file:/.test(t.url || ''))){const button=document.createElement('button');button.className='tab';button.textContent=tab.title || tab.url;button.title=tab.url;button.onclick=async()=>{try{const c=await ui('context',{tab_id:tab.id});if(c.requires_user_action){result.textContent=c.message;return;}setContext(c);result.textContent='Context ready. Copy it into your AI chat.';}catch(error){result.textContent=error.message;}};container.append(button);}
}
document.getElementById('copy').onclick=async()=>{try{await navigator.clipboard.writeText(document.getElementById('context').value);result.textContent='Copied.';}catch(error){result.textContent='Select and copy the text manually: '+error.message;}};
document.getElementById('refresh').onclick=()=>render().catch(error=>{result.textContent=error.message;});document.getElementById('settings').onclick=()=>chrome.runtime.openOptionsPage();
chrome.storage.onChanged.addListener((changes)=>{if(changes.selectedContext) setContext(changes.selectedContext.newValue);});
render().catch(error=>{result.textContent=error.message;});
