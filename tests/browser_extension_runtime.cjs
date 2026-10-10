const fs=require('fs'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const root=process.argv[2];
const store={},session={},calls=[],tabs=new Map([[1,{id:1,url:'https://allowed.test',title:'Test'}],[2,{id:2,url:'https://second.test',title:'Second'}]]);
const event=()=>({addListener(){}});
const storage=data=>({get:async keys=>Object.fromEntries((typeof keys==='string'?[keys]:keys).map(k=>[k,data[k]])),set:async values=>Object.assign(data,values),remove:async keys=>{for(const k of typeof keys==='string'?[keys]:keys)delete data[k];}});
let delay=false,historyReads=0;
const chrome={runtime:{getManifest:()=>({version:'2.0.0'})},storage:{local:storage(store),session:storage(session)},permissions:{contains:async()=>true},
  debugger:{attach:async target=>calls.push(['attach',target]),detach:async target=>calls.push(['detach',target]),onDetach:event(),onEvent:event(),sendCommand:async(target,method,p)=>{
    calls.push([method,target,p]);if(method==='Page.captureScreenshot')return{data:'PNG_DATA'};if(method==='Runtime.evaluate')return{result:{value:42}};return{};}},
  tabs:{get:async id=>tabs.get(id),query:async()=>[...tabs.values()],create:async p=>{calls.push(['create',p]);return{id:3,...p};},
    update:async(id,p)=>{calls.push(['update',id,p]);Object.assign(tabs.get(id),p);},remove:async id=>calls.push(['remove',id]),
    sendMessage:async(id,m,p)=>{calls.push(['message-start',id,m.action]);if(delay)await new Promise(r=>setTimeout(r,20));calls.push(['message-end',id,m.action]);return{ok:true,result:{x:10,y:20,elements:[],url:tabs.get(id).url}};},
    goBack:async()=>{},goForward:async()=>{},reload:async()=>{},group:async()=>4,ungroup:async()=>{}},
  tabGroups:{update:async()=>{}},
  scripting:{executeScript:async()=>calls.push(['inject'])},
  webNavigation:{getFrame:async({tabId})=>({url:tabs.get(tabId).url}),getAllFrames:async()=>[{frameId:0,parentFrameId:-1,url:'https://allowed.test'}]},
  history:{search:async()=>{historyReads++;return[];}},bookmarks:{search:async()=>[{id:'1',title:'test',url:'https://example.com'}]},
  downloads:{download:async()=>8,search:async()=>[{id:8,state:'complete'}]}};
const ctx=vm.createContext({chrome,URL,console,crypto:crypto.webcrypto,setTimeout,Promise});
for(const file of ['access.js','debugger.js','commands.js'])vm.runInContext(fs.readFileSync(root+'/'+file,'utf8'),ctx);
const run=(a,p)=>ctx.LucasCommands.run(a,p);
(async()=>{
  store.siteMode='ask';let r=await run('page.snapshot',{tab_id:1});assert(r.action_type==='website_permission');
  assert(!calls.some(c=>c[0]==='message-start'));
  store.allowedHosts=['allowed.test'];r=await run('page.snapshot',{tab_id:1});assert(r.elements);
  store.blockedHosts=['allowed.test'];r=await run('page.screenshot',{tab_id:1});assert(r.action_type==='website_blocked');
  store.blockedHosts=[];store.siteMode='all';
  r=await run('page.click',{tab_id:1,target:'ref:x'});assert(r.tab_id===1);
  const input=calls.filter(c=>c[0]==='Input.dispatchMouseEvent');assert(input.length===2);assert(input[0][2].x===10);
  r=await run('page.screenshot',{tab_id:2});assert(r.base64==='PNG_DATA');
  r=await run('developer.evaluate',{tab_id:1,expression:'1+1'});assert(r.action_type==='developer_permission');
  r=await run('page.evaluate_readonly',{tab_id:1,expression:'1+1'});assert(r.value===42);assert(calls.filter(c=>c[0]==='Runtime.evaluate').at(-1)[2].throwOnSideEffect===true);
  store.developerMode=true;r=await run('developer.evaluate',{tab_id:1,expression:'1+1'});assert(r.value===42);
  await assert.rejects(run('developer.cdp',{tab_id:1,method:'Target.createTarget'}),/selected page/);
  await assert.rejects(run('page.snapshot',{}),/tab_id/);
  await assert.rejects(run('tab.navigate',{tab_id:1,url:'javascript:alert(1)'}),/internal/);
  const created=await run('tab.open',{url:'https://allowed.test'});assert(created.id===3);assert(calls.find(c=>c[0]==='create')[1].active===false);
  store.paused=true;r=await run('page.click',{tab_id:1,target:'Save'});assert(r.action_type==='browser_paused');store.paused=false;
  r=await run('history.search',{});assert(r.action_type==='history_permission');session.historyConsentUntil=Date.now()+60000;
  const results=await Promise.all([run('history.search',{}),run('history.search',{})]);assert(historyReads===1);assert(results[1].action_type==='history_permission');
  delay=true;calls.length=0;await Promise.all([run('page.snapshot',{tab_id:1}),run('page.selection',{tab_id:1}),run('page.snapshot',{tab_id:2})]);
  const one=calls.filter(c=>c[1]===1&&c[0].startsWith('message'));assert.deepEqual(one.map(c=>c[0]),['message-start','message-end','message-start','message-end']);
  const twoStart=calls.findIndex(c=>c[0]==='message-start'&&c[1]===2),oneEnd=calls.findIndex(c=>c[0]==='message-end'&&c[1]===1);assert(twoStart<oneEnd);
  delay=false;await run('download.url',{tab_id:1,url:'https://allowed.test/file'});await run('download.status',{tab_id:1,download_id:8});
  await assert.rejects(run('download.status',{tab_id:2,download_id:8}),/does not belong/);
  assert(ctx.LucasAccess.matches('sub.example.com',['*.example.com']));assert(!ctx.LucasAccess.matches('example.com.evil',['*.example.com']));
  console.log('extension runtime assertions passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
