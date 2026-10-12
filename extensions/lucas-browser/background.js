let socket, owners=[], status='Disconnected';
const grants=new Map(), queues=new Map();
setInterval(()=>send({type:'ping'}),20000);
const command=(tabId,method,params={})=>chrome.debugger.sendCommand({tabId},method,params);
const send = data => { if(socket?.readyState===WebSocket.OPEN) socket.send(JSON.stringify(data)); };
function revoke(sid, notify=true) {
  const grant=grants.get(sid); if(!grant) return;
  grants.delete(sid); if(notify) send({type:'revoke',session_id:sid});
  if(![...grants.values()].some(g=>g.tab_id===grant.tab_id)) chrome.debugger.detach({tabId:grant.tab_id}).catch(()=>{});
}
async function connect() {
  const {token,port=8766}=await chrome.storage.local.get(['token','port']);
  if(!token) return;
  socket?.close();
  const current=new WebSocket(`ws://127.0.0.1:${port}`); socket=current; status='Connecting';
  current.onopen=()=>current.send(JSON.stringify({type:'hello',token}));
  current.onclose=()=>{ if(socket!==current) return; status='Disconnected — permissions revoked'; owners=[]; for(const sid of [...grants.keys()]) revoke(sid,false); };
  current.onmessage=async event=>{
    if(socket!==current) return;
    const msg=JSON.parse(event.data);
    if(msg.type==='ready'){owners=msg.owners; status='Paired';}
    if(msg.type==='grant_error') status=msg.error;
    if(msg.type==='granted'){
      const tab=await chrome.tabs.get(msg.tab_id).catch(()=>null);
      if(tab) { grants.set(msg.session_id,{...msg,title:tab.title}); status='Tab authorized'; }
      else send({type:'revoke',session_id:msg.session_id});
    }
    if(msg.type==='revoked') revoke(msg.session_id,false);
    if(msg.type==='request'){
      const previous=queues.get(msg.tab_id)||Promise.resolve();
      const next=previous.catch(()=>{}).then(async()=>{
        const grant=grants.get(msg.session_id);
        if(!grant||grant.tab_id!==msg.tab_id) throw Error('Tab is not authorized');
        return execute(msg.tab_id,msg.action,msg.params||{});
      });
      queues.set(msg.tab_id,next);
      try { const result=await next; if(grants.has(msg.session_id)) send({type:'response',id:msg.id,ok:true,result}); }
      catch(error){send({type:'response',id:msg.id,ok:false,error:error.message});}
      finally {if(queues.get(msg.tab_id)===next) queues.delete(msg.tab_id);}
    }
  };
}
chrome.alarms.create('reconnect',{periodInMinutes:0.5});
chrome.alarms.onAlarm.addListener(()=>{if(!socket||socket.readyState===WebSocket.CLOSED) connect();});
chrome.tabs.onRemoved.addListener(tab=>{for(const [sid,g] of grants) if(g.tab_id===tab) revoke(sid);});
chrome.debugger.onDetach.addListener(source=>{for(const [sid,g] of grants) if(g.tab_id===source.tabId) revoke(sid);});
chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
  if(sender.id!==chrome.runtime.id) return false;
  (async()=>{
    if(msg.type==='status') return {status,owners,sessions:[...grants.values()]};
    if(msg.type==='pair'){
      if(typeof msg.token!=='string'||msg.token.length<32||!Number.isInteger(msg.port)||msg.port<1024||msg.port>65535) throw Error('Invalid token or port');
      for(const sid of [...grants.keys()]) revoke(sid);
      await chrome.storage.local.set({token:msg.token,port:msg.port}); await connect(); return {ok:true};
    }
    if(msg.type==='grant'){
      if(socket?.readyState!==WebSocket.OPEN||!owners.some(o=>o.user_id===msg.owner_id)) throw Error('Pair and choose an approved account first');
      const tab=await chrome.tabs.get(msg.tab_id);
      if(!/^https?:\/\//i.test(tab.url||'')) throw Error('Only HTTP(S) tabs can be authorized');
      if(![...grants.values()].some(g=>g.tab_id===tab.id)) await chrome.debugger.attach({tabId:tab.id},'1.3');
      send({type:'grant',owner_id:msg.owner_id,tab_id:tab.id,title:tab.title,url:tab.url}); return {ok:true};
    }
    if(msg.type==='revoke'){for(const sid of [...grants.keys()]) revoke(sid); return {ok:true};}
    throw Error('Unsupported popup request');
  })().then(reply).catch(error=>reply({error:error.message})); return true;
});

// Only this fixed function executes in a page. Remote callers cannot supply JS.
function pageAction(action,p) {
  const info=()=>({url:location.href,title:document.title});
  const norm=x=>String(x||'').replace(/\s+/g,' ').trim().toLowerCase();
  const all='button,a,input,textarea,select,[role="button"],[role="link"],[contenteditable="true"]';
  const visible=e=>!!e.getClientRects().length;
  const human=!!document.querySelector('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="challenges.cloudflare.com"],input[autocomplete="one-time-code"]') || /verify (your identity|you are human)|security key|passkey/i.test(document.body?.innerText||'');
  if(human && !['inspect','observe'].includes(action)) return {handoff_required:true,reason:'Complete verification manually in the authorized tab'};
  if(action==='inspect') return {...info(),text:(document.querySelector(p.selector||'body')?.innerText||'').slice(0,Math.min(Math.max(Number(p.max_chars)||30000,1),100000))};
  if(action==='observe') return {...info(),handoff_required:human,elements:[...document.querySelectorAll(all)].filter(visible).slice(0,Math.min(Number(p.limit)||300,1000)).map((e,index)=>({index,tag:e.tagName.toLowerCase(),id:e.id,role:e.getAttribute('role')||'',text:(e.type==='password'?'':e.innerText||e.value||'').slice(0,300),aria_label:e.getAttribute('aria-label')||'',placeholder:e.getAttribute('placeholder')||'',disabled:!!e.disabled}))};
  if(action==='scroll'){window.scrollBy(Number(p.x)||0,Number(p.y)||0);return {...info(),x:scrollX,y:scrollY};}
  let element;
  if(action.startsWith('semantic_')){
    const target=norm(p.target); if(!target) throw Error('target is required');
    const editable=action==='semantic_type';
    const candidates=[...document.querySelectorAll(editable?'input,textarea,[contenteditable="true"]':all)].filter(visible);
    const score=e=>{
      const labels=[e.getAttribute('aria-label'),e.getAttribute('placeholder'),e.innerText,...(e.labels||[])].map(x=>norm(x?.textContent||x)).filter(Boolean);
      return labels.some(x=>x===target)?2:labels.some(x=>x.includes(target))?1:0;
    };
    const ranked=candidates.map(e=>({e,score:score(e)})).filter(x=>x.score).sort((a,b)=>b.score-a.score);
    if(!ranked.length) throw Error('No matching control');
    if(ranked.length>1&&ranked[0].score===ranked[1].score) throw Error('Ambiguous control; use a precise selector');
    element=ranked[0].e;
  }else element=document.querySelector(p.selector);
  if(!element||!visible(element)||element.disabled) throw Error('Control missing, hidden or disabled');
  if(action==='click'||action==='semantic_click'){
    if(element.closest('a')?.target==='_blank'||element.form?.target==='_blank') return {handoff_required:true,reason:'This control opens another tab; open and authorize it manually'};
    element.click();return info();
  }
  if(action==='type'||action==='semantic_type'){
    const text=String(p.text||'');
    if(element.isContentEditable) element.textContent=(p.clear===false?element.textContent:'')+text;
    else {
      if(!['INPUT','TEXTAREA'].includes(element.tagName)||element.type==='file') throw Error('Not a text input');
      const setter=Object.getOwnPropertyDescriptor(element.tagName==='INPUT'?HTMLInputElement.prototype:HTMLTextAreaElement.prototype,'value').set;
      setter.call(element,(p.clear===false?element.value:'')+text);
    }
    element.dispatchEvent(new Event('input',{bubbles:true})); element.dispatchEvent(new Event('change',{bubbles:true})); return {...info(),characters:text.length};
  }
  if(action==='select'){
    if(element.tagName!=='SELECT'||![...element.options].some(o=>o.value===p.value)) throw Error('Unknown option');
    element.value=p.value; element.dispatchEvent(new Event('change',{bubbles:true})); return {...info(),selected:[p.value]};
  }
  throw Error('Unsupported page action');
}
async function evaluate(tab,action,p) {
  const result=await command(tab,'Runtime.evaluate',{expression:`(${pageAction.toString()})(${JSON.stringify(action)},${JSON.stringify(p)})`,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
  return result.result.value;
}
async function execute(tab,action,p) {
  const current=await chrome.tabs.get(tab);
  if(!/^https?:\/\//i.test(current.url||'')) throw Error('Authorized tab must be HTTP(S)');
  if(action==='new_page') return {handoff_required:true,reason:'Open a new tab and explicitly authorize it in Lucas Browser'};
  if(action==='resolve') return {resolved:true,page_index:0,url:current.url,title:current.title,tab_id:tab};
  if(action==='handoff') return {handoff_required:true,reason:'Complete the manual step in this tab, then ask the AI to observe again',tab_id:tab};
  if(action==='pages') return [{index:0,tab_id:tab,url:current.url,title:current.title}];
  if(action==='navigate') {
    const url=new URL(p.url); if(!['http:','https:'].includes(url.protocol)||url.username||url.password) throw Error('Only HTTP(S) navigation is allowed');
    const result=await command(tab,'Page.navigate',{url:url.href}); if(result.errorText) throw Error(result.errorText); return {url:url.href};
  }
  if(action==='screenshot'){
    const options={format:'png',captureBeyondViewport:!!p.full_page};
    if(p.full_page){const {cssContentSize:s}=await command(tab,'Page.getLayoutMetrics'); options.clip={x:0,y:0,width:s.width,height:s.height,scale:1};}
    const result=await command(tab,'Page.captureScreenshot',options); return {mime_type:'image/png',base64:result.data};
  }
  if(action==='upload'){
    if(!Array.isArray(p.paths)||!p.paths.length) throw Error('paths required');
    const {root}=await command(tab,'DOM.getDocument');
    const {nodeId}=await command(tab,'DOM.querySelector',{nodeId:root.nodeId,selector:p.selector});
    if(!nodeId) throw Error('File input not found');
    await command(tab,'DOM.setFileInputFiles',{nodeId,files:p.paths}); return {files:p.paths};
  }
  if(action==='download'){
    // Fetch an authorized HTTP(S) link inside the tab. Never change the
    // browser-wide download directory or intercept other tabs' downloads.
    const result=await command(tab,'Runtime.evaluate',{expression:`(${downloadLink.toString()})(${JSON.stringify(p.selector)})`,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
    return result.result.value;
  }
  return evaluate(tab,action,p);
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
