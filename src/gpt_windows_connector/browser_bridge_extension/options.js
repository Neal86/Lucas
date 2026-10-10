const identityIds=['browserType','profileName','profileId','alias','tags','groups'];
const listIds=['tags','groups','allowedHosts','blockedHosts'];
const ids=[...identityIds,'siteMode','allowedHosts','blockedHosts','paused','developerMode'];
const result=document.getElementById('result');
async function load(){
  const s=await chrome.storage.local.get(ids);
  for(const id of ids){const el=document.getElementById(id);if(el.type==='checkbox')el.checked=!!s[id];else el.value=Array.isArray(s[id])?s[id].join(id.endsWith('Hosts')?'\n':', '):(s[id] || (id==='siteMode'?'all':id==='browserType'?'chrome':''));}
}
document.getElementById('save').onclick=async()=>{
  try{
    const data={};for(const id of ids){const el=document.getElementById(id);data[id]=el.type==='checkbox'?el.checked:listIds.includes(id)?el.value.split(/[,\n]/).map(x=>x.trim()).filter(Boolean):el.value.trim();}
    await chrome.storage.local.set(data);result.textContent='Settings saved.';
  }catch(error){result.textContent=error.message;}
};
document.getElementById('history').onclick=async()=>{
  const allowed=await chrome.permissions.request({permissions:['history']});
  if(allowed){await chrome.storage.session.set({historyConsentUntil:Date.now()+60000});result.textContent='One history lookup approved. Ask your AI to retry within 60 seconds.';}
  else result.textContent='History access was declined.';
};
document.getElementById('bookmarks').onclick=async()=>{result.textContent=await chrome.permissions.request({permissions:['bookmarks']})?'Bookmarks enabled.':'Bookmarks permission declined.';};
document.getElementById('revoke').onclick=async()=>{await chrome.permissions.remove({permissions:['history','bookmarks']});await chrome.storage.session.remove('historyConsentUntil');result.textContent='Optional access revoked.';};
load().catch(error=>{result.textContent=error.message;});
