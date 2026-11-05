// Unit/runtime tests execute shipped code against explicit Chrome API doubles.
// These are not real-browser or Windows acceptance tests.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const base='src/gpt_windows_connector/browser_bridge_extension/';
const event=()=>({listeners:[],addListener(fn){this.listeners.push(fn);}});
function environment(local={},session={}){
 const changed=event(),messages=event(),activated=event(),updated=event();
 let active=1,nextId=10;const tabs=new Map([[1,{id:1,active:true,url:'https://human.test'}]]),sent=[],sockets=[];
 const store=data=>({async get(keys){return Object.fromEntries(keys.filter(k=>k in data).map(k=>[k,data[k]]));},async set(values){Object.assign(data,structuredClone(values));for(const fn of changed.listeners)fn(Object.fromEntries(Object.entries(values).map(([k,v])=>[k,{newValue:v}])),'local');}});
 const chrome={runtime:{id:'a'.repeat(32),onInstalled:event(),onStartup:event(),onMessage:messages},storage:{local:store(local),session:{async get(keys){return Object.fromEntries(keys.filter(k=>k in session).map(k=>[k,session[k]]));},async set(v){Object.assign(session,structuredClone(v));}},onChanged:changed},action:{async setBadgeText(){},async setBadgeBackgroundColor(){}},tabs:{onRemoved:event(),onActivated:activated,onUpdated:updated,async query(q){return [...tabs.values()].filter(t=>!q.active||t.id===active);},async get(id){if(!tabs.has(id))throw Error('No tab');return tabs.get(id);},async create(p){assert.equal(p.active,false);const t={id:nextId++,url:p.url,active:false};tabs.set(t.id,t);return t;},async sendMessage(id,m){sent.push({id,m});return {ok:true,result:{tab_id:id}};},async update(id,p){Object.assign(tabs.get(id),p);return tabs.get(id);},async remove(id){tabs.delete(id);for(const fn of this.onRemoved.listeners)fn(id);}},downloads:{async download(){return 1;}}};
 class Socket{constructor(){this.readyState=0;sockets.push(this);}send(m){this.sent=JSON.parse(m);}close(){this.readyState=3;this.onclose?.();}}
 const elements=Object.fromEntries(['status','profile','tabState'].map(id=>[id,{textContent:''}]));
 const ctx=vm.createContext({chrome,WebSocket:Socket,crypto:{randomUUID:()=> 'install'},navigator:{userAgent:'Chrome'},Date,console,setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,clearInterval(){},document:{getElementById:id=>elements[id]}});
 vm.runInContext(fs.readFileSync(base+'background.js','utf8'),ctx);
 return {ctx,chrome,local,session,tabs,sent,sockets,elements,setActive(id){active=id;},call:(action,p)=>vm.runInContext(`executeCommand(${JSON.stringify(action)},${JSON.stringify(p)})`,ctx),message(m,id){return new Promise(resolve=>{const fn=messages.listeners.find(fn=>fn(m,{tab:{id}},resolve)===true);if(!fn)resolve(null);});}};
}
(async()=>{
 const e=environment();await new Promise(setImmediate);
 const a=await e.call('tab.open',{task_key:'a',url:'https://a.test'}),b=await e.call('tab.open',{task_key:'b'});
 assert.equal(e.tabs.get(1).active,true);
 await assert.rejects(e.call('tab.navigate',{task_key:'a',tab_id:b.id,url:'https://wrong.test'}),/another/);
 await assert.rejects(e.call('tab.claim',{task_key:'a',tab_id:1}),/confirmation/);
 await e.message({type:'lucas_human_takeover',tab_id:b.id},a.id);
 assert.equal(e.local.lucasTabStates[a.id].control,'human');assert.equal(e.local.lucasTabStates[b.id].paused,false);
 await assert.rejects(e.call('page.snapshot',{task_key:'a',tab_id:a.id}),/paused/);
 await e.call('page.snapshot',{task_key:'b',tab_id:b.id});
 await e.call('tab.claim',{task_key:'a',tab_id:a.id,user_confirmed:true});assert.equal(e.local.lucasTabStates[a.id].paused,true);
 await assert.rejects(e.call('tab.resume',{task_key:'a',tab_id:a.id}),/confirmation/);
 await e.message({type:'lucas_human_resume'},a.id);await e.call('page.snapshot',{task_key:'a',tab_id:a.id});
 await e.message({type:'lucas_human_pause'},a.id);assert.equal(e.local.lucasTabStates[a.id].control,'paused');
 const socket=e.sockets[0];socket.readyState=1;await socket.onopen();
 await socket.onmessage({data:JSON.stringify({type:'hello_ack',paired:true,node_id:'N20630',profile:{profile_name:'Test Chrome'}})});
 vm.runInContext(fs.readFileSync(base+'popup.js','utf8'),e.ctx);await new Promise(setImmediate);
 assert.equal(e.elements.status.textContent,'Connected');assert.equal(e.elements.profile.textContent,'N20630 / Test Chrome');assert.equal(e.elements.tabState.textContent,'Human');
 e.setActive(a.id);await vm.runInContext('render()',e.ctx);assert.equal(e.elements.tabState.textContent,'AI Paused');
 await e.message({type:'lucas_human_takeover'},a.id);await vm.runInContext('render()',e.ctx);assert.equal(e.elements.tabState.textContent,'Human Control');
 e.setActive(b.id);await vm.runInContext('render()',e.ctx);assert.equal(e.elements.tabState.textContent,'AI Running');
 e.local.lastSeen=Date.now()-50000;await vm.runInContext('render()',e.ctx);assert.equal(e.elements.status.textContent,'Disconnected');
 await socket.onmessage({data:JSON.stringify({type:'heartbeat_ack'})});await vm.runInContext('render()',e.ctx);assert.equal(e.elements.status.textContent,'Connected');
 socket.close();await vm.runInContext('render()',e.ctx);assert.equal(e.elements.status.textContent,'Disconnected');
 const restarted=environment({lucasTabStates:{1:{task_key:'old',paused:false}}});await new Promise(setImmediate);await assert.rejects(restarted.call('page.snapshot',{task_key:'old',tab_id:1}),/not claimed/);
 const worker=environment({}, {lucasTabStates:{1:{task_key:'saved',paused:true,control:'human'}}});await new Promise(setImmediate);await assert.rejects(worker.call('page.snapshot',{task_key:'saved',tab_id:1}),/paused/);
 console.log('PASS: background ownership, task isolation, per-tab human pause/resume, reclaim guard, live Popup states, heartbeat/disconnect, safe restart');
})().catch(e=>{console.error(e);process.exitCode=1;});
