importScripts('access.js','debugger.js','commands.js');
const BRIDGE_URL = 'ws://127.0.0.1:8766/bridge';
let socket=null, reconnectTimer=null, heartbeatTimer=null;
const identityKeys=['installationId','browserType','profileName','profileId','alias','tags','groups'];
async function getSettings() {
  const s=await chrome.storage.local.get(identityKeys);
  if(!s.installationId){s.installationId=crypto.randomUUID();await chrome.storage.local.set({installationId:s.installationId});}
  return {installation_id:s.installationId,extension_id:chrome.runtime.id,browser_type:s.browserType || 'chrome',
    profile_name:s.profileName || '',profile_id:s.profileId || '',alias:s.alias || '',tags:s.tags || [],groups:s.groups || []};
}
function badge(text,color) {
  chrome.action.setBadgeText({text}).catch(()=>{});
  chrome.action.setBadgeBackgroundColor({color}).catch(()=>{});
}
function reconnect(){clearTimeout(reconnectTimer);reconnectTimer=setTimeout(connect,2500);}
async function status(connected,paired=false,extra={}) {
  await chrome.storage.local.set({connected,paired,lastConnectionUpdate:Date.now(),...extra});
  badge(connected?(paired?'L':'!'):'×',connected?(paired?'#16a34a':'#d97706'):'#dc2626');
}
function connect() {
  if(socket && [WebSocket.CONNECTING,WebSocket.OPEN].includes(socket.readyState))return;
  const ws=new WebSocket(BRIDGE_URL);socket=ws;
  ws.onopen=async()=>{
    const settings=await getSettings();if(ws.readyState !== WebSocket.OPEN)return;
    ws.send(JSON.stringify({type:'hello',...settings}));
    await status(true,false);
    clearInterval(heartbeatTimer);
    heartbeatTimer=setInterval(()=>{if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'heartbeat',time:Date.now()}));},20000);
  };
  ws.onmessage=async event=>{
    let m;try{m=JSON.parse(event.data);}catch(_){return;}
    if(m.type==='hello_ack'){await status(true,!!m.paired,{pairingCode:String(m.pairing_code || '')});return;}
    if(m.type==='paired'){await status(true,true,{pairingCode:''});return;}
    if(m.type!=='command')return;
    const id=String(m.id || '');
    try {
      const result=await LucasCommands.run(String(m.action || ''),m.params || {});
      // Never deliver an old command result into a new transport connection.
      if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'response',id,ok:true,result}));
    } catch(error) {if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'response',id,ok:false,error:String(error?.message || error)}));}
  };
  ws.onclose=()=>{if(socket!==ws)return;clearInterval(heartbeatTimer);status(false).catch(()=>{});reconnect();};
  ws.onerror=()=>{};
}
chrome.storage.onChanged.addListener((changes,area)=>{
  if(area!=='local')return;
  if(identityKeys.some(key=>changes[key]) && socket?.readyState===WebSocket.OPEN)socket.close(4002,'identity changed');
  if(changes.paused?.newValue || changes.developerMode?.newValue===false) LucasDebugger.detachAll().catch(()=>{});
});
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='lucas-reconnect')connect();});
chrome.alarms.create('lucas-reconnect',{periodInMinutes:1});
chrome.runtime.onInstalled.addListener(()=>{
  chrome.contextMenus.removeAll().then(()=>chrome.contextMenus.create({id:'lucas-context',title:'Ask AI with Lucas context',contexts:['page','selection']}));
  connect();
});
chrome.runtime.onStartup.addListener(connect);
chrome.contextMenus.onClicked.addListener((info,tab)=>{
  if(info.menuItemId!=='lucas-context' || !tab?.id)return;
  chrome.storage.session.set({selectedContext:{tab_id:tab.id,url:tab.url,title:tab.title,selection:info.selectionText || ''}});
  chrome.sidePanel?.open({tabId:tab.id}).catch(()=>{});
});
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  // UI control is only accepted from our own extension pages, not site content.
  if(sender.id!==chrome.runtime.id || sender.tab || !sender.url?.startsWith(chrome.runtime.getURL('')))return;
  if(message.type!=='lucas_ui')return;
  (async()=>{
    if(message.action==='reconnect'){socket?.close();connect();return{ok:true};}
    if(message.action==='context') {
      const tab=await chrome.tabs.get(Number(message.tab_id));
      const context=await LucasCommands.run('page.selection',{tab_id:tab.id});
      if(context.requires_user_action)return context;
      const selectedContext={tab_id:tab.id,title:tab.title,url:tab.url,...context};
      await chrome.storage.session.set({selectedContext});return selectedContext;
    }
    if(message.action==='tabs')return LucasCommands.run('tabs.list');
    throw new Error('Unsupported extension UI action');
  })().then(result=>reply({ok:true,result})).catch(error=>reply({ok:false,error:String(error.message || error)}));
  return true;
});
connect();

chrome.commands.onCommand.addListener((command,tab)=>{if(command==='open-lucas' && tab?.id)chrome.sidePanel.open({tabId:tab.id}).catch(()=>{});});
