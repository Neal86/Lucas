"""Computer metadata/log/activation UI ownership; no device operation occurs."""
from web_management_fixture import run_management_cases


def test_computer_management_ownership(tmp_path):
    run_management_cases(tmp_path, CASES, "computer-management-ownership")


CASES = r'''
for(const language of ['en','zh-CN']){
 managementTest(language+': current rename captures encoded target and trimmed payload once',async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);f.ctx.manageNodeName.value='  New A  ';const p=f.call('saveNodeName()'),again=f.call('saveNodeName()');
  assert.equal(f.requests.length,1);assert.equal(f.requests[0].url,'/api/nodes/a%20%2F%3F/name');assert.equal(f.requests[0].options.method,'PUT');assert.equal(f.requests[0].options.body,JSON.stringify({name:'New A'}));assert.equal(f.ctx.manageNodeSave.disabled,true);
  f.respond(0,{display_name:'New A'});await p;await again;assert.equal(f.call('state.nodes[0].display_name'),'New A');assert.equal(f.call('state.nodes[1].display_name'),undefined);assert.equal(f.ctx.manageNodeSave.disabled,false);
 });
 for(const change of ['reopen-same','reopen-other','close','escape','navigation','history','account','direct-user','login-generation','auth'])for(const outcome of [200,401,503,'network'])managementTest(language+': retired rename '+change+' '+outcome,async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);f.ctx.manageNodeName.value='OLD_NAME';const p=f.call('saveNodeName()');
  if(change==='reopen-same')openNode(f);else if(change==='reopen-other')openNode(f,'b');else if(change==='close')f.call("closeModal('nodeModal')");else if(change==='escape')for(const h of f.listeners.keydown||[])h({key:'Escape'});else ownerChange(f,change);
  const before=JSON.stringify(f.call('state.nodes')),user=f.call('state.user?.id');await respondOutcome(f,0,outcome,{display_name:'OLD_NAME'});await p;
  if(outcome===200&&['reopen-same','reopen-other','close','escape','navigation','history'].includes(change)){assert.equal(f.call('state.nodes[0].display_name'),'OLD_NAME');assert.equal(f.call('state.nodes[1].display_name'),undefined)}else assert.equal(JSON.stringify(f.call('state.nodes')),before);assert.equal(f.call('state.user?.id'),user);assert.equal(f.requests.length,1);assert.ok(!f.elements.get('toast').textContent.includes('OLD'));
 });
 for(const revert of [false,true])managementTest(language+': edited name suppresses old result including edit-revert='+revert,async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);f.ctx.manageNodeName.value='FIRST';const p=f.call('saveNodeName()');f.ctx.manageNodeName.value='SECOND';f.call('computerManagementNameChanged()');if(revert){f.ctx.manageNodeName.value='FIRST';f.call('computerManagementNameChanged()')}f.respond(0,{display_name:'FIRST'});await p;assert.equal(f.call('state.nodes[0].display_name'),'FIRST');assert.equal(f.ctx.manageNodeName.value,revert?'FIRST':'SECOND');assert.equal(f.ctx.manageNodeSave.disabled,false);
 });
 managementTest(language+': delayed rename JSON still checks selection ownership',async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);const p=f.call('saveNodeName()');let release;f.requests[0].resolve({status:200,ok:true,json:()=>new Promise(r=>release=r)});await settle();openNode(f,'b');release({display_name:'OLD'});await p;assert.equal(f.call('state.nodes[1].display_name'),undefined);
 });
 for(const outcome of [503,'network'])managementTest(language+': current rename failure retains deliberate retry '+outcome,async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);const p=f.call('saveNodeName()');await respondOutcome(f,0,outcome);await p;assert.equal(f.ctx.manageNodeSave.disabled,false);assert.match(f.elements.get('toast').textContent,/OLD_ERROR/);const retry=f.call('saveNodeName()');f.respond(1,{display_name:'RETRY'});await retry;assert.equal(f.call('state.nodes[0].display_name'),'RETRY');
 });
 managementTest(language+': obsolete rename finalizer cannot release a replacement save',async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);const old=f.call('saveNodeName()');openNode(f);const fresh=f.call('saveNodeName()');f.respond(0,{display_name:'OLD'});await old;assert.equal(f.ctx.manageNodeSave.disabled,true);f.respond(1,{display_name:'NEW'});await fresh;assert.equal(f.ctx.manageNodeSave.disabled,false);assert.equal(f.call('state.nodes[0].display_name'),'NEW');
 });
 for(const change of ['reopen-same','reopen-other','close','escape','navigation','history','account','direct-user','login-generation','auth'])for(const outcome of [200,401,503,'network'])managementTest(language+': retired log read '+change+' '+outcome,async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);const p=f.call('loadNodeLogs()');assert.equal(f.requests[0].url,'/api/nodes/a%20%2F%3F/logs?limit=250');
  if(change==='reopen-same')openNode(f);else if(change==='reopen-other')openNode(f,'b');else if(change==='close')f.call("closeModal('nodeModal')");else if(change==='escape')for(const h of f.listeners.keydown||[])h({key:'Escape'});else ownerChange(f,change);
  const before=f.ctx.manageLogs.textContent,user=f.call('state.user?.id');await respondOutcome(f,0,outcome,{lines:['OLD_LOG']});await p;assert.equal(f.ctx.manageLogs.textContent,before);assert.equal(f.call('state.user?.id'),user);
 });
 managementTest(language+': latest log response and finalizer own their loading button',async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);const old=f.call('loadNodeLogs()'),fresh=f.call('loadNodeLogs()');f.respond(0,{lines:['OLD']});await old;assert.equal(f.ctx.manageNodeLogsRefresh.disabled,true);assert.ok(!f.ctx.manageLogs.textContent.includes('OLD'));f.respond(1,{lines:['NEW','LINE']});await fresh;assert.equal(f.ctx.manageLogs.textContent,'NEW\nLINE');assert.equal(f.ctx.manageNodeLogsRefresh.disabled,false);
 });
 for(const outcome of [200,503,'network'])managementTest(language+': current log outcome remains visible '+outcome,async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);const p=f.call('loadNodeLogs()');await respondOutcome(f,0,outcome,{lines:[]});await p;assert.equal(f.ctx.manageLogs.textContent,outcome===200?'No log lines yet.':'OLD_ERROR');assert.equal(f.ctx.manageNodeLogsRefresh.disabled,false);
 });
 managementTest(language+': auth reset hides and clears account-owned computer presentation only',()=>{
  const f=fixture(language);seedNodes(f);openNode(f);f.ctx.connectNodeId.value='UNRELATED_DRAFT';f.stored.set('unrelated','keep');account(f);assert.equal(f.ctx.nodeModal.classList.contains('hidden'),true);for(const id of ['manageNodeIdText','managePermissionText','manageRootsText','manageLogs'])assert.equal(f.ctx[id].textContent,'');assert.equal(f.ctx.manageNodeName.value,'A');assert.equal(f.ctx.connectNodeId.value,'UNRELATED_DRAFT');assert.equal(f.stored.get('unrelated'),'keep');
 });
 managementTest(language+': committed rename invalidates an older dashboard snapshot',async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);const read=f.call('refresh()');f.ctx.manageNodeName.value='NEW';const save=f.call('saveNodeName()');f.respond(3,{display_name:'NEW'});await save;reply(f,0,'OLD');await read;assert.equal(f.call('state.nodes[0].display_name'),'NEW');
 });
 managementTest(language+': activation dispatch is once and busy through its current refresh',async()=>{
  const f=fixture(language);seedNodes(f);const p=f.call("activateNode('a%20%2F%3F')"),again=f.call("activateNode('a%20%2F%3F')");assert.equal(f.requests.length,1);assert.equal(f.requests[0].url,'/api/nodes/a%20%2F%3F/activate');assert.equal(f.requests[0].options.method,'POST');assert.equal(f.requests[0].options.body,undefined);f.respond(0,{ok:true});await settle();assert.equal(f.requests.length,4);assert.match(f.call("computerActivationButtonState('a /?')"),/disabled/);reply(f,1,'NEW');await p;await again;assert.ok(!f.call("computerActivationButtonState('a /?')").includes('disabled'));
 });
 for(const change of ['navigation','history','account','direct-user','login-generation','auth'])for(const outcome of [200,401,503,'network'])managementTest(language+': activation follow-up belongs to its same-account cache '+change+' '+outcome,async()=>{
  const f=fixture(language);seedNodes(f);const p=f.call("activateNode('b')");ownerChange(f,change);const user=f.call('state.user?.id');await respondOutcome(f,0,outcome,{ok:true});const sameAccountSuccess=outcome===200&&['navigation','history'].includes(change);if(sameAccountSuccess)reply(f,1,'CURRENT');await p;assert.equal(f.call('state.user?.id'),user);assert.equal(f.requests.length,sameAccountSuccess?4:1);
 });

 managementTest(language+': committed rename survives Close without changing a newer unsaved draft',async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);f.ctx.manageNodeName.value='SAVED';const p=f.call('saveNodeName()');f.call("closeModal('nodeModal')");openNode(f);f.ctx.manageNodeName.value='UNSAVED';f.call('computerManagementNameChanged()');f.respond(0,{display_name:'SAVED'});await p;assert.equal(f.ctx.manageNodeName.value,'UNSAVED');assert.equal(f.call('state.nodes[0].display_name'),'SAVED');f.call("closeModal('nodeModal')");openNode(f);assert.equal(f.ctx.manageNodeName.value,'SAVED');assert.equal(f.requests.length,1);
 });
 for(const reverse of [false,true])managementTest(language+': latest same-target rename owns cache across modal generations reverse='+reverse,async()=>{
  const f=fixture(language);seedNodes(f);openNode(f);f.ctx.manageNodeName.value='OLD';const old=f.call('saveNodeName()');openNode(f);f.ctx.manageNodeName.value='NEW';const fresh=f.call('saveNodeName()');
  if(reverse){f.respond(1,{display_name:'NEW'});await fresh;f.respond(0,{display_name:'OLD'});await old}else{f.respond(0,{display_name:'OLD'});await old;assert.equal(f.call('state.nodes[0].display_name'),undefined);f.respond(1,{display_name:'NEW'});await fresh}assert.equal(f.call('state.nodes[0].display_name'),'NEW');assert.equal(f.ctx.manageNodeName.value,'NEW');assert.equal(f.call('computerNameCommits.size'),0);
 });
 managementTest(language+': navigation preserves current-account activation refresh but not old toast',async()=>{
  const f=fixture(language);seedNodes(f);const p=f.call("activateNode('b')");f.call("view('account',null)");const toastBefore=f.elements.get('toast').textContent;f.respond(0,{ok:true});await settle();assert.equal(f.requests.length,4);reply(f,1,'ACTIVATED');await p;assert.equal(f.elements.get('toast').textContent,toastBefore);assert.equal(f.call('state.nodes[0].node_id'),'ACTIVATED');assert.equal(f.call('computerActivationCommits.size'),0);
 });
}
'''
