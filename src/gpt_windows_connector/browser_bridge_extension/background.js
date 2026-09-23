const BRIDGE_URL = "ws://127.0.0.1:8766/bridge";
let socket = null, reconnectTimer = null, heartbeatTimer = null;

async function getSettings() {
  const stored = await chrome.storage.local.get(["installationId","browserType","profileName","profileId","alias","tags","groups"]);
  if (!stored.installationId) {
    stored.installationId = crypto.randomUUID();
    await chrome.storage.local.set({installationId: stored.installationId});
  }
  return {
    installation_id: stored.installationId,
    extension_id: chrome.runtime.id,
    browser_type: stored.browserType || "ixbrowser",
    profile_name: stored.profileName || "",
    profile_id: stored.profileId || "",
    alias: stored.alias || "",
    tags: Array.isArray(stored.tags) ? stored.tags : [],
    groups: Array.isArray(stored.groups) ? stored.groups : []
  };
}
function badge(text,color){ chrome.action.setBadgeText({text:text||""}).catch(()=>{}); if(color) chrome.action.setBadgeBackgroundColor({color}).catch(()=>{}); }
function scheduleReconnect(){ clearTimeout(reconnectTimer); reconnectTimer=setTimeout(connect,2500); }
async function connect(){
  if(socket && (socket.readyState===0 || socket.readyState===1)) return;
  try { socket=new WebSocket(BRIDGE_URL); } catch(_) { scheduleReconnect(); return; }
  socket.onopen=async()=>{ socket.send(JSON.stringify({type:"hello",...(await getSettings())})); badge("…","#64748b"); clearInterval(heartbeatTimer); heartbeatTimer=setInterval(()=>{if(socket?.readyState===1) socket.send(JSON.stringify({type:"heartbeat",time:Date.now()}));},20000); };
  socket.onmessage=async(event)=>{
    let m; try{m=JSON.parse(event.data);}catch(_){return;}
    if(m.type==="hello_ack"){ badge(m.paired?"L":"!",m.paired?"#16a34a":"#d97706"); await chrome.storage.local.set({paired:!!m.paired,pairingCode:String(m.pairing_code||"")}); return; }
    if(m.type==="paired"){ badge("L","#16a34a"); await chrome.storage.local.set({paired:true,pairingCode:""}); return; }
    if(m.type==="heartbeat_ack") return;
    if(m.type!=="command") return;
    const id=String(m.id||"");
    try{ const result=await executeCommand(String(m.action||""),m.params||{}); socket.send(JSON.stringify({type:"response",id,ok:true,result})); }
    catch(error){ socket.send(JSON.stringify({type:"response",id,ok:false,error:(error?.name||"Error")+": "+(error?.message||String(error))})); }
  };
  socket.onclose=()=>{ badge("×","#dc2626"); clearInterval(heartbeatTimer); scheduleReconnect(); };
  socket.onerror=()=>{};
}
async function getTab(tabId){
  if(tabId!=null) return chrome.tabs.get(Number(tabId));
  const tabs=await chrome.tabs.query({lastFocusedWindow:true});
  const usable=tabs.filter(t=>/^https?:|^file:|^chrome-extension:/.test(t.url||""));
  return usable.find(t=>t.active)||usable[0]||tabs[0];
}
async function runInTab(tabId,func,args=[]){
  const out=await chrome.scripting.executeScript({target:{tabId:Number(tabId)},func,args});
  return out?.[0]?.result;
}
function pageSnapshot(limit,maxChars){
  const visible=el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return r.width>0&&r.height>0&&s.visibility!=="hidden"&&s.display!=="none";};
  const textOf=el=>String(el.innerText||el.value||el.textContent||"").replace(/\s+/g," ").trim();
  const selectorFor=el=>{
    if(el.id) return "#"+CSS.escape(el.id);
    const parts=[]; let node=el;
    while(node&&node.nodeType===1&&parts.length<5){
      let part=node.tagName.toLowerCase();
      if(node.classList?.length) part+="."+[...node.classList].slice(0,2).map(CSS.escape).join(".");
      if(node.parentElement){const siblings=[...node.parentElement.children].filter(x=>x.tagName===node.tagName);if(siblings.length>1) part+=":nth-of-type("+(siblings.indexOf(node)+1)+")";}
      parts.unshift(part); node=node.parentElement;
    }
    return parts.join(" > ");
  };
  const nodes=[...document.querySelectorAll("button,a,input,textarea,select,[role=button],[role=link],[role=checkbox],[role=radio],[role=menuitem],[contenteditable=true]")].filter(visible).slice(0,Number(limit||400));
  const elements=nodes.map((el,index)=>({index,tag:el.tagName.toLowerCase(),role:el.getAttribute("role")||"",text:textOf(el).slice(0,500),aria_label:el.getAttribute("aria-label")||"",name:el.getAttribute("name")||"",placeholder:el.getAttribute("placeholder")||"",type:el.getAttribute("type")||"",selector:selectorFor(el),disabled:!!el.disabled}));
  const bodyText=String(document.body?.innerText||"").slice(0,Number(maxChars||50000));
  const lower=(document.title+" "+location.href+" "+bodyText).toLowerCase();
  const captcha=!!document.querySelector('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="challenges.cloudflare.com"],[data-sitekey],[class*="captcha" i],[id*="captcha" i]')||/verify you are human|human verification|人机验证|安全验证/.test(lower);
  const otp=!!document.querySelector('input[autocomplete="one-time-code"]')||/two[- ]factor|2fa|verification code|authenticator code|短信验证码|两步验证|双重验证/.test(lower);
  const password=!!document.querySelector('input[type="password"]');
  const passkey=/passkey|security key|windows hello|通行密钥|安全密钥/.test(lower);
  const identity=/verify your identity|identity verification|government-issued id|business verification|身份验证|实名认证|营业执照/.test(lower);
  return {url:location.href,title:document.title,text:bodyText,elements,blocker:captcha?"captcha":otp?"2fa":passkey?"passkey":identity?"identity_verification":password&&/login|signin|sign-in|登录/.test(lower)?"login":null};
}
function findTarget(target,editable=false){
  const q=String(target||"").trim(); if(!q) throw new Error("target is required");
  const visible=el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return r.width>0&&r.height>0&&s.display!=="none"&&s.visibility!=="hidden";};
  try{const el=document.querySelector(q.startsWith("css=")?q.slice(4):q);if(el&&visible(el))return el;}catch(_){}
  const nodes=[...document.querySelectorAll(editable?'input,textarea,select,[contenteditable=true]':'button,a,[role=button],[role=link],[role=checkbox],[role=radio],[role=menuitem],input[type=submit],input[type=button]')].filter(visible);
  const needle=q.toLowerCase();
  const score=el=>{const vals=[el.getAttribute("aria-label"),el.getAttribute("name"),el.getAttribute("placeholder"),el.innerText,el.value,el.labels?.[0]?.innerText].filter(Boolean).map(v=>String(v).replace(/\s+/g," ").trim().toLowerCase());if(vals.some(v=>v===needle))return 100;if(vals.some(v=>v.includes(needle)))return 60;return 0;};
  const ranked=nodes.map(el=>[score(el),el]).filter(x=>x[0]>0).sort((a,b)=>b[0]-a[0]); if(!ranked.length)throw new Error("No browser element matched: "+q); return ranked[0][1];
}
function clickTarget(target){const el=findTarget(target,false);el.scrollIntoView({block:"center",inline:"center"});el.click();return{target,url:location.href};}
function typeTarget(target,value,clear){const el=findTarget(target,true);el.scrollIntoView({block:"center",inline:"center"});el.focus({preventScroll:true});if("value"in el){let proto=el.tagName==="TEXTAREA"?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;if(el.tagName==="SELECT")proto=HTMLSelectElement.prototype;const d=Object.getOwnPropertyDescriptor(proto,"value");const next=clear===false?String(el.value||"")+String(value):String(value);if(d?.set)d.set.call(el,next);else el.value=next;el.dispatchEvent(new Event("input",{bubbles:true}));el.dispatchEvent(new Event("change",{bubbles:true}));}else{el.textContent=clear===false?String(el.textContent||"")+String(value):String(value);el.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:String(value)}));}return{target,characters:String(value).length,url:location.href};}
function selectTarget(target,value){const el=findTarget(target,true);if(!(el instanceof HTMLSelectElement))throw new Error("Matched element is not a select");el.value=String(value);el.dispatchEvent(new Event("input",{bubbles:true}));el.dispatchEvent(new Event("change",{bubbles:true}));return{target,value:el.value};}
function scrollPage(target,dx,dy){if(target){const el=findTarget(target,false);el.scrollIntoView({block:"center",inline:"center"});return{target,url:location.href};}window.scrollBy(Number(dx||0),Number(dy||700));return{x:scrollX,y:scrollY,url:location.href};}
function hoverTarget(target){const el=findTarget(target,false);el.scrollIntoView({block:"center",inline:"center"});["pointerover","mouseover","mouseenter"].forEach(type=>el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window})));return{target,url:location.href};}
function pressTarget(target,key){const el=target?findTarget(target,true):(document.activeElement||document.body);el.focus?.({preventScroll:true});["keydown","keyup"].forEach(type=>el.dispatchEvent(new KeyboardEvent(type,{key:String(key),bubbles:true,cancelable:true})));if(String(key)==="Enter"&&el.form?.requestSubmit)el.form.requestSubmit();return{target:target||null,key:String(key),url:location.href};}
function uploadFiles(target,files){const el=findTarget(target,true);if(!(el instanceof HTMLInputElement)||el.type!=="file")throw new Error("Matched element is not a file input");const dt=new DataTransfer();for(const item of files||[]){const bytes=Uint8Array.from(atob(item.base64),c=>c.charCodeAt(0));dt.items.add(new File([bytes],item.name||"upload.bin",{type:item.type||"application/octet-stream"}));}el.files=dt.files;el.dispatchEvent(new Event("input",{bubbles:true}));el.dispatchEvent(new Event("change",{bubbles:true}));return{target,files:dt.files.length};}
async function waitCondition(tabId,p){const deadline=Date.now()+Math.min(Math.max(Number(p.timeout_ms||15000),250),120000);while(Date.now()<deadline){const ok=await runInTab(tabId,(selector,text,urlContains)=>{if(selector)return!!document.querySelector(selector);if(text)return String(document.body?.innerText||"").toLowerCase().includes(String(text).toLowerCase());if(urlContains)return location.href.includes(String(urlContains));return document.readyState==="complete"||document.readyState==="interactive";},[p.selector||null,p.text||null,p.url_contains||null]);if(ok)return{waited:true};await new Promise(r=>setTimeout(r,250));}throw new Error("Timeout waiting for page condition");}
async function pageCommand(tabId,action,p){const response=await chrome.tabs.sendMessage(tabId,{type:"lucas_command",action,params:p||{}});if(!response||!response.ok)throw new Error(response?.error||"Browser Bridge content runtime unavailable");return response.result;}
async function executeCommand(action,p){
  if(action==="ping")return{ok:true,time:Date.now()};
  if(action==="tabs.list"){const tabs=await chrome.tabs.query({});return tabs.map(t=>({id:t.id,window_id:t.windowId,active:!!t.active,title:t.title||"",url:t.url||"",status:t.status||""}));}
  if(action==="tab.open"){const t=await chrome.tabs.create({url:p.url||"about:blank",active:false});return{id:t.id,window_id:t.windowId,url:t.url||p.url||"about:blank",title:t.title||""};}
  if(action==="tab.close"){await chrome.tabs.remove(Number(p.tab_id));return{closed:true,tab_id:Number(p.tab_id)};}
  const tab=await getTab(p.tab_id); if(!tab?.id)throw new Error("No usable browser tab found"); const tabId=tab.id;
  if(action==="tab.navigate"){const t=await chrome.tabs.update(tabId,{url:String(p.url)});return{tab_id:tabId,url:t.url||p.url};}
  if(action==="tab.reload"){await chrome.tabs.reload(tabId);return{tab_id:tabId,reloaded:true};}
  if(action==="tab.back"||action==="tab.forward"){await chrome.scripting.executeScript({target:{tabId},func:action==="tab.back"?()=>history.back():()=>history.forward()});return{tab_id:tabId,action};}
  if(action.startsWith("page."))return pageCommand(tabId,action,p);
  if(action==="download.url"){const id=await chrome.downloads.download({url:String(p.url),filename:p.filename||undefined,saveAs:false});return{download_id:id};}
  throw new Error("Unsupported Bridge action: "+action);
}
chrome.runtime.onInstalled.addListener(connect);
chrome.runtime.onStartup.addListener(connect);
chrome.storage.onChanged.addListener(()=>{if(socket?.readyState===1)socket.close(4002,"settings changed");});
connect();
