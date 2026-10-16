"""AI-delete response ownership using synthetic HTTP, never OAuth mutation."""
from web_management_fixture import run_management_cases


def test_ai_delete_response_ownership(tmp_path):
    run_management_cases(tmp_path, CASES, "ai-delete-ownership")


CASES = r'''
for(const language of ['en','zh-CN']){
 managementTest(language+': current delete confirms and dispatches once, with unchanged payload',async()=>{
  const f=fixture(language);seedClients(f);const p=deleteClient(f),again=deleteClient(f);assert.equal(f.requests.length,1);assert.equal(f.confirmations.length,1);assert.match(f.confirmations[0],/This removes the Lucas OAuth connection. You can reconnect it later./);assert.equal(f.requests[0].url,'/api/ai-connections/shared%20%2F%3F');assert.equal(f.requests[0].options.method,'DELETE');assert.equal(f.requests[0].options.body,undefined);assert.match(f.call("aiConnectionDeleteButtonState('shared /?')"),/disabled/);f.respond(0,{ok:true});await p;await again;assert.deepEqual(JSON.parse(f.call('JSON.stringify(state.aiClients.map(x=>x.client_id))')),['other']);assert.equal(f.ctx.metricAiClients.textContent,1);
 });
 for(const change of ['navigation','history','account','direct-user','login-generation','auth'])for(const outcome of [200,401,503,'network'])managementTest(language+': old delete cannot change new owner '+change+' '+outcome,async()=>{
  const f=fixture(language);seedClients(f);const p=deleteClient(f);ownerChange(f,change);if(change!=='auth')seedClients(f);const before=f.call('JSON.stringify(state.aiClients)'),user=f.call('state.user?.id');await respondOutcome(f,0,outcome,{ok:true});await p;if(outcome===200&&['navigation','history'].includes(change)){assert.equal(f.call('state.aiClients.length'),1);assert.equal(f.call('state.aiClients[0].client_id'),'other')}else assert.equal(f.call('JSON.stringify(state.aiClients)'),before);assert.equal(f.call('state.user?.id'),user);assert.equal(f.requests.length,1);
 });
 managementTest(language+': delayed parsed response cannot remove replacement account client',async()=>{
  const f=fixture(language);seedClients(f);const p=deleteClient(f);let release;f.requests[0].resolve({status:200,ok:true,json:()=>new Promise(r=>release=r)});await settle();account(f);seedClients(f);release({ok:true});await p;assert.equal(f.call('state.aiClients.length'),2);
 });
 managementTest(language+': concurrent deletes for different current clients remain independent',async()=>{
  const f=fixture(language);seedClients(f);const first=deleteClient(f),second=deleteClient(f,'other');assert.equal(f.requests.length,2);f.respond(1,{ok:true});await second;assert.equal(f.call('state.aiClients.length'),1);assert.match(f.call("aiConnectionDeleteButtonState('shared /?')"),/disabled/);f.respond(0,{ok:true});await first;assert.equal(f.call('state.aiClients.length'),0);assert.equal(f.ctx.metricAiClients.textContent,0);
 });
 for(const outcome of [503,'network'])managementTest(language+': current delete failure and deliberate retry '+outcome,async()=>{
  const f=fixture(language);seedClients(f);const p=deleteClient(f);await respondOutcome(f,0,outcome);await p;assert.equal(f.call('state.aiClients.length'),2);assert.ok(!f.call("aiConnectionDeleteButtonState('shared /?')").includes('disabled'));assert.match(f.elements.get('toast').textContent,/OLD_ERROR/);const retry=deleteClient(f);f.respond(1,{ok:true});await retry;assert.equal(f.call('state.aiClients.length'),1);assert.equal(f.confirmations.length,2);
 });
 managementTest(language+': old finalizer cannot unlock the same client in a newer attempt',async()=>{
  const f=fixture(language);seedClients(f);const old=deleteClient(f);f.call("view('account',null)");const fresh=deleteClient(f);f.respond(0,{ok:true});await old;assert.match(f.call("aiConnectionDeleteButtonState('shared /?')"),/disabled/);f.respond(1,{ok:true});await fresh;assert.equal(f.call('state.aiClients.length'),1);
 });
 managementTest(language+': current401 retains signout behavior',async()=>{
  const f=fixture(language);seedClients(f);const p=deleteClient(f);f.respond(0,{error:'expired'},401);await p;assert.equal(f.call('state.user'),null);assert.equal(f.call('state.aiClients.length'),0);
 });
 managementTest(language+': cancel and missing target dispatch nothing',async()=>{
  const f=fixture(language);seedClients(f);f.ctx.confirm=()=>false;await deleteClient(f);assert.equal(f.requests.length,0);await deleteClient(f,'missing');assert.equal(f.requests.length,0);assert.equal(f.call('state.aiClients.length'),2);
 });
 managementTest(language+': committed deletion invalidates an older dashboard snapshot',async()=>{
  const f=fixture(language);seedClients(f);const read=f.call('refresh()'),del=deleteClient(f);f.respond(3,{ok:true});await del;f.respond(0,{nodes:[],billing:null});f.respond(1,{logs:[]});f.respond(2,{clients:[{client_id:'shared /?',display_name:'OLD'}]});await read;assert.deepEqual(JSON.parse(f.call('JSON.stringify(state.aiClients.map(x=>x.client_id))')),['other']);
 });

 managementTest(language+': successful same-account delete stays reconciled after navigating back',async()=>{
  const f=fixture(language);seedClients(f);const p=deleteClient(f);f.call("view('account',null)");const toastBefore=f.elements.get('toast').textContent;f.respond(0,{ok:true});await p;f.call("view('ai',null)");assert.equal(f.call('state.aiClients.length'),1);assert.equal(f.call('state.aiClients[0].client_id'),'other');assert.equal(f.ctx.metricAiClients.textContent,1);assert.equal(f.elements.get('toast').textContent,toastBefore);assert.equal(f.requests.length,1);assert.equal(f.call('aiDeleteCommits.size'),0);
 });
 managementTest(language+': navigation-delete commit retires an overlapping dashboard snapshot',async()=>{
  const f=fixture(language);seedClients(f);const read=f.call('refresh()'),p=deleteClient(f);f.call("view('account',null)");f.respond(3,{ok:true});await p;f.respond(0,{nodes:[],billing:null});f.respond(1,{logs:[]});f.respond(2,{clients:[{client_id:'shared /?',display_name:'OLD'}]});await read;f.call("view('ai',null)");assert.equal(f.call('state.aiClients.length'),1);assert.equal(f.call('state.aiClients[0].client_id'),'other');
 });
}
'''
