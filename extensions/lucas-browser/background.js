import {GrantLifecycle} from './grant_lifecycle.js';
import {pageAction} from './page_actions.js';

let socket, owners=[], status='Disconnected', canGrant=false;
let connectionAttempt=0, connecting=0, pairingWrites=Promise.resolve();
const queues=new Map();
const sendTo=(connection,data)=>{if(connection?.readyState===WebSocket.OPEN) connection.send(JSON.stringify(data));};
const lifecycle=new GrantLifecycle({
  getTab:tab=>chrome.tabs.get(tab),
  attach:tab=>chrome.debugger.attach({tabId:tab},'1.3'),
  detach:tab=>chrome.debugger.detach({tabId:tab}),
  send:sendTo,
});
setInterval(()=>sendTo(socket,{type:'ping'}),20000);
const command=(tabId,method,params={})=>chrome.debugger.sendCommand({tabId},method,params);

function beginConnection() {
  const attempt=++connectionAttempt; connecting=attempt;
  const previous=socket; socket=undefined; owners=[]; canGrant=false;
  lifecycle.replaceConnection(null); previous?.close();
  status='Connecting'; return attempt;
}
async function openConnection(attempt) {
  try {
    const {token,port=8766}=await chrome.storage.local.get(['token','port']);
    if(attempt!==connectionAttempt) return;
    if(!token) {status='Disconnected'; return;}
    const current=new WebSocket(`ws://127.0.0.1:${port}`); socket=current;
    lifecycle.replaceConnection(current);
    current.onopen=()=>{if(socket===current) sendTo(current,{type:'hello',token});};
    current.onclose=()=>{
      if(socket!==current) return;
      status='Disconnected — permissions revoked'; owners=[]; canGrant=false;
      lifecycle.replaceConnection(null);
    };
    current.onmessage=async event=>{
      if(socket!==current) return;
      const msg=JSON.parse(event.data);
      if(msg.type==='ready') {
        owners=msg.owners; canGrant=Array.isArray(msg.capabilities)&&msg.capabilities.includes('grant_request_id');
        status=canGrant?'Paired':'Update Lucas Node to support safe tab authorization';
      }
      if(msg.type==='grant_error' && lifecycle.reject(current,msg)) status=msg.error;
      if(msg.type==='granted' && await lifecycle.acknowledge(current,msg)) status='Tab authorized';
      if(msg.type==='revoked') lifecycle.revoke(msg.session_id,false);
      if(msg.type==='request') {
        const previous=queues.get(msg.tab_id)||Promise.resolve();
        const next=previous.catch(()=>{}).then(async()=>{
          const guard=lifecycle.guard(current,msg.session_id,msg.tab_id);
          const result=await execute(msg.tab_id,msg.action,msg.params||{},guard);
          guard(); return result;
        });
        queues.set(msg.tab_id,next);
        try { const result=await next; lifecycle.guard(current,msg.session_id,msg.tab_id)(); sendTo(current,{type:'response',id:msg.id,ok:true,result}); }
        catch(error) { sendTo(current,{type:'response',id:msg.id,ok:false,error:error.message}); }
        finally { if(queues.get(msg.tab_id)===next) queues.delete(msg.tab_id); }
      }
    };
  } finally { if(connecting===attempt) connecting=0; }
}
async function connect() {
  const attempt=beginConnection();
  await pairingWrites.catch(()=>{});
  if(attempt===connectionAttempt) await openConnection(attempt);
}
chrome.alarms.create('reconnect',{periodInMinutes:0.5});
chrome.alarms.onAlarm.addListener(()=>{if(!connecting&&(!socket||socket.readyState===WebSocket.CLOSED)) void connect();});
chrome.tabs.onRemoved.addListener(tab=>lifecycle.removeTab(tab));
chrome.debugger.onDetach.addListener(source=>lifecycle.removeTab(source.tabId,true));
chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
  if(sender.id!==chrome.runtime.id) return false;
  (async()=>{
    if(msg.type==='status') return {status,owners,sessions:lifecycle.sessions(),can_grant:canGrant};
    if(msg.type==='pair') {
      if(typeof msg.token!=='string'||msg.token.length<32||!Number.isInteger(msg.port)||msg.port<1024||msg.port>65535) throw Error('Invalid token or port');
      const attempt=beginConnection();
      const write=pairingWrites.catch(()=>{}).then(()=>chrome.storage.local.set({token:msg.token,port:msg.port}));
      pairingWrites=write;
      try {
        await write;
        if(attempt!==connectionAttempt) throw Error('Pairing was replaced by a newer request');
        await openConnection(attempt); return {ok:true};
      } finally {if(connecting===attempt) connecting=0;}
    }
    if(msg.type==='grant') {
      if(!canGrant) throw Error('Update Lucas Node to support safe tab authorization');
      if(socket?.readyState!==WebSocket.OPEN||!owners.some(o=>o.user_id===msg.owner_id)) throw Error('Pair and choose an approved account first');
      return lifecycle.request(socket,msg.owner_id,msg.tab_id);
    }
    if(msg.type==='revoke') { lifecycle.revokeAll(); status='Permissions revoked'; return {ok:true}; }
    throw Error('Unsupported popup request');
  })().then(reply).catch(error=>reply({error:error.message})); return true;
});

async function evaluate(tab,action,p,dispatch) {
  const result=await dispatch('Runtime.evaluate',{expression:`(${pageAction.toString()})(${JSON.stringify(action)},${JSON.stringify(p)})`,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
  return result.result.value;
}
async function execute(tab,action,p,guard) {
  const dispatch=(method,params)=>{guard(); return command(tab,method,params);};
  const current=await chrome.tabs.get(tab); guard();
  if(!/^https?:\/\//i.test(current.url||'')) throw Error('Authorized tab must be HTTP(S)');
  if(action==='new_page') return {handoff_required:true,reason:'Open a new tab and explicitly authorize it in Lucas Browser'};
  if(action==='resolve') return {resolved:true,page_index:0,url:current.url,title:current.title,tab_id:tab};
  if(action==='handoff') return {handoff_required:true,reason:'Complete the manual step in this tab, then ask the AI to observe again',tab_id:tab};
  if(action==='pages') return [{index:0,tab_id:tab,url:current.url,title:current.title}];
  if(action==='navigate') {
    const url=new URL(p.url); if(!['http:','https:'].includes(url.protocol)||url.username||url.password) throw Error('Only HTTP(S) navigation is allowed');
    await dispatch('Page.enable');
    let listener,timer,done;
    const loaded=new Promise((resolve,reject)=>{
      done=resolve;
      listener=(source,method)=>{if(source.tabId===tab&&method==='Page.domContentEventFired') resolve();};
      chrome.debugger.onEvent.addListener(listener);
      timer=setTimeout(()=>reject(Error('Navigation timed out')),20000);
    });
    // Attach rejection handling before the CDP command so a stalled command
    // cannot leave an unhandled load-timeout rejection.
    loaded.catch(()=>{});
    try {
      const result=await dispatch('Page.navigate',{url:url.href});
      if(result.errorText) throw Error(result.errorText);
      if(!result.loaderId) done();
      await loaded;
      guard();
      const current=await chrome.tabs.get(tab);
      return {url:current.url,title:current.title};
    }finally{clearTimeout(timer);chrome.debugger.onEvent.removeListener(listener);}
  }
  if(action==='screenshot'){
    const options={format:'png',captureBeyondViewport:!!p.full_page};
    if(p.full_page){const {cssContentSize:s}=await dispatch('Page.getLayoutMetrics'); options.clip={x:0,y:0,width:s.width,height:s.height,scale:1};}
    const result=await dispatch('Page.captureScreenshot',options); return {mime_type:'image/png',base64:result.data};
  }
  if(action==='upload'){
    if(!Array.isArray(p.paths)||!p.paths.length) throw Error('paths required');
    const {root}=await dispatch('DOM.getDocument');
    const {nodeId}=await dispatch('DOM.querySelector',{nodeId:root.nodeId,selector:p.selector});
    if(!nodeId) throw Error('File input not found');
    await dispatch('DOM.setFileInputFiles',{nodeId,files:p.paths}); return {files:p.paths};
  }
  if(action==='download'){
    // Fetch an authorized HTTP(S) link inside the tab. Never change the
    // browser-wide download directory or intercept other tabs' downloads.
    const result=await dispatch('Runtime.evaluate',{expression:`(${downloadLink.toString()})(${JSON.stringify(p.selector)})`,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
    return result.result.value;
  }
  return evaluate(tab,action,p,dispatch);
}
connect();

async function downloadLink(selector) {
  const element=document.querySelector(selector);
  if(!element?.href) return {handoff_required:true,reason:'This download requires a manual export; use an HTTP(S) download link or complete it manually'};
  const url=new URL(element.href,location.href);
  if(!['http:','https:'].includes(url.protocol)) throw Error('Only HTTP(S) downloads are supported');
  const response=await fetch(url.href,{credentials:'include',signal:AbortSignal.timeout(60000)});
  if(!response.ok) throw Error(`Download returned HTTP ${response.status}`);
  const reader=response.body.getReader();const chunks=[];let length=0;
  while(true){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>20*1024*1024){await reader.cancel();throw Error('Download exceeds 20 MiB; download it manually');}chunks.push(value);}
  let binary='';for(const chunk of chunks) for(let i=0;i<chunk.length;i+=8192) binary+=String.fromCharCode(...chunk.subarray(i,i+8192));
  return {base64:btoa(binary),suggested_filename:element.download||url.pathname.split('/').pop()||'download'};
}
