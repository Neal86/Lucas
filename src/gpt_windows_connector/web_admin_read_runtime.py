"""Administrative read responses owned by the current view, selection and session.

Invalidating a UI owner suppresses its response only. It never cancels or retries
an already-dispatched account mutation.
"""
from __future__ import annotations

ADMIN_READ_SCRIPT = r'''
// Context-only labels: never translate user content or change submitted values.
function adminEnumLabel(kind,value){
  if(WEB_LANG!=='zh')return value;
  const labels={
    role:{user:'用户',admin:'管理员',super_admin:'超级管理员'},
    account:{active:'正常',disabled:'已停用'},
    plan:{free:'免费',pro:'Pro',pro_plus:'Pro+'},
    operation:{success:'成功',error:'错误',failed:'失败',running:'运行中',pending:'等待中',unknown:'未知'},
    subscription:{active:'有效',inactive:'未启用',trialing:'试用中',past_due:'已逾期',canceled:'已取消',unpaid:'未付款',incomplete:'未完成',incomplete_expired:'未完成且已过期',paused:'已暂停'}
  };
  const group=labels[kind];
  return group&&Object.prototype.hasOwnProperty.call(group,value)?group[value]:value;
}
let adminViewGeneration=0,adminTabGeneration=0,adminUserGeneration=0,adminUserReadGeneration=0;
let adminSearchGeneration=0,adminFilterGeneration=0,adminCurrentTab='',adminSelectedUserId=null;
function adminReadSessionOwner(){
  const view=adminViewGeneration,generation=loginGeneration,user=state.user,root=document.getElementById('admin');
  return ()=>!!user&&state.user===user&&generation===loginGeneration&&view===adminViewGeneration&&!!root&&!root.classList.contains('hidden');
}
function invalidateAdminUserView(){
  adminUserGeneration++;adminUserReadGeneration++;adminSelectedUserId=null;
  document.getElementById('adminUserModal')?.classList.add('hidden');
  const detail=document.getElementById('adminUserDetail');if(detail)detail.innerHTML='';
}
function invalidateAdminReads(){
  adminViewGeneration++;adminTabGeneration++;adminSearchGeneration++;adminFilterGeneration++;
  adminCurrentTab='';invalidateAdminUserView();
  const content=document.getElementById('adminContent');if(content)content.innerHTML='';
}
function adminUserViewOwner(id){
  const isSessionCurrent=adminReadSessionOwner(),generation=adminUserGeneration,key=String(id);
  return ()=>isSessionCurrent()&&generation===adminUserGeneration&&key===adminSelectedUserId;
}
function adminChildReadOwner(tab,kind,table){
  const isSessionCurrent=adminReadSessionOwner(),parent=adminTabGeneration;
  const generation=kind==='users'?++adminSearchGeneration:++adminFilterGeneration;
  return ()=>isSessionCurrent()&&parent===adminTabGeneration&&adminCurrentTab===tab&&!!table&&document.getElementById(table.id)===table&&generation===(kind==='users'?adminSearchGeneration:adminFilterGeneration);
}
async function adminTab(tab,el,updateUrl=true){
  const isSessionCurrent=adminReadSessionOwner(),generation=++adminTabGeneration;
  adminSearchGeneration++;adminFilterGeneration++;adminCurrentTab=tab;invalidateAdminUserView();
  const isCurrent=()=>isSessionCurrent()&&generation===adminTabGeneration&&adminCurrentTab===tab;
  if(!isCurrent())return;
if(updateUrl){const p=adminPaths[tab]||'/admin';if(location.pathname!==p)history.pushState({adminTab:tab},'',p)}document.querySelectorAll('#adminTabs button').forEach(b=>{b.classList.remove('primary');b.classList.add('secondary')});if(el){el.classList.remove('secondary');el.classList.add('primary')}adminContent.innerHTML='<div class="card empty">Loading…</div>';try{if(tab==='dashboard'){const d=await api('/api/admin/dashboard',{},isCurrent);if(!isCurrent())return;adminContent.innerHTML=`<div class="grid">${adminMetric('Total users',d.users)}${adminMetric('Active users · 7d',d.active_users_7d)}${adminMetric('Online nodes',d.online_nodes)}${adminMetric('Operations today',d.operations_today)}${adminMetric('Operations · 30d',d.operations_30d)}${adminMetric('Paid users',d.paid_users)}</div><div class="card" style="margin-top:16px"><h3>Recent activity</h3>${d.recent.length?'<table class="table"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Target</th></tr></thead><tbody>'+d.recent.map(r=>`<tr><td>${esc(timefmt(r.created_at))}</td><td>${esc(r.email||'—')}</td><td>${esc(r.action)}</td><td>${esc(r.target||'—')}</td></tr>`).join('')+'</tbody></table>':'<div class="empty">No activity.</div>'}</div>`}else if(tab==='users'){const d=await api('/api/admin/users',{},isCurrent);if(!isCurrent())return;adminContent.innerHTML=`<div class="toolbar"><input id="adminUserSearch" class="input" placeholder="Search email or name"><button class="btn secondary" onclick="adminSearchUsers()">Search</button></div><div id="adminUsersTable">${renderAdminUsers(d.users)}</div>`}else if(tab==='usage'){const d=await api('/api/admin/usage',{},isCurrent);if(!isCurrent())return;adminContent.innerHTML=`<div class="grid">${adminMetric('Operations · 30d',d.operations_30d)}${adminMetric('Execution · 30d',Math.round(d.execution_seconds_30d)+'s')}${adminMetric('Success rate',d.success_rate+'%')}${adminMetric('Failed · 30d',d.errors_30d)}${adminMetric('Files / Shell / Git',(d.by_tool.files||0)+' / '+(d.by_tool.shell||0)+' / '+(d.by_tool.git||0))}</div><div class="card" style="margin-top:16px"><h3>Top users · 30d</h3><table class="table"><thead><tr><th>User</th><th>Operations</th></tr></thead><tbody>${d.top_users.map(r=>`<tr><td>${esc(r.email)}</td><td>${esc(r.n)}</td></tr>`).join('')}</tbody></table></div>`}else if(tab==='nodes'){const d=await api('/api/admin/nodes',{},isCurrent);if(!isCurrent())return;adminContent.innerHTML=d.nodes.length?`<table class="table"><thead><tr><th>Node</th><th>Platform</th><th>Status</th><th>Allowed folders</th><th>Last seen</th></tr></thead><tbody>${d.nodes.map(n=>`<tr><td><b>${esc(n.name)}</b><div class="muted">${esc(n.node_id)}</div></td><td>${esc(n.platform)}</td><td><span class="badge ${n.online?'online':'offline'}">${n.online?'Online':'Offline'}</span></td><td>${esc(n.allowed_folder_count)}</td><td>${esc(timefmt(n.updated_at))}</td></tr>`).join('')}</tbody></table>`:'<div class="card empty">No nodes.</div>'}else if(tab==='operations'){const d=await api('/api/admin/operations?limit=300',{},isCurrent);if(!isCurrent())return;adminContent.innerHTML=`<div class="toolbar"><input id="adminOpUser" class="input" placeholder="User"><input id="adminOpAction" class="input" placeholder="Tool / action"><button class="btn secondary" onclick="adminFilterOps()">Filter</button></div><div id="adminOpsTable">${renderAdminOps(d.operations)}</div>`}else if(tab==='subscriptions'){const d=await api('/api/admin/subscriptions',{},isCurrent);if(!isCurrent())return;adminContent.innerHTML=`<table class="table"><thead><tr><th>User</th><th>Plan</th><th>Status</th><th>Expansion</th><th>Provider</th><th>Renews</th></tr></thead><tbody>${d.subscriptions.map(s=>`<tr><td>${esc(s.email)}</td><td>${esc(adminEnumLabel("plan",s.plan))}</td><td>${esc(adminEnumLabel("subscription",s.status))}</td><td>${esc(s.expansion_quantity||0)}</td><td>${esc(s.billing_provider||'—')}</td><td>${esc(timefmt(s.current_period_end||s.ends_at))}</td></tr>`).join('')}</tbody></table>`}else if(tab==='system'){const d=await api('/api/admin/system',{},isCurrent);if(!isCurrent())return;adminContent.innerHTML=`<div class="grid">${adminMetric('Gateway',d.gateway)}${adminMetric('Database',d.database)}${adminMetric('Online nodes',d.online_nodes)}${adminMetric('Total nodes',d.total_nodes)}${adminMetric('Users',d.users)}${adminMetric('Server time',new Date(d.server_time*1000).toLocaleString())}</div>`}}catch(e){if(!isCurrent())return;adminContent.innerHTML=`<div class="error">${esc(e.message)}</div>`}}
async function adminSearchUsers(){
  const input=document.getElementById('adminUserSearch'),table=document.getElementById('adminUsersTable');
  const isCurrent=adminChildReadOwner('users','users',table);if(!isCurrent()||!input)return;
  const query=input.value;let d;
  try{d=await api('/api/admin/users?q='+encodeURIComponent(query),{},isCurrent)}
  catch(error){if(isCurrent())throw error;return}
  if(isCurrent())table.innerHTML=renderAdminUsers(d.users);
}
async function adminFilterOps(){
  const user=document.getElementById('adminOpUser'),action=document.getElementById('adminOpAction'),table=document.getElementById('adminOpsTable');
  const isCurrent=adminChildReadOwner('operations','operations',table);if(!isCurrent()||!user||!action)return;
  const q=new URLSearchParams({limit:'300'});if(user.value)q.set('user',user.value);if(action.value)q.set('action',action.value);
  let d;try{d=await api('/api/admin/operations?'+q,{},isCurrent)}
  catch(error){if(isCurrent())throw error;return}
  if(isCurrent())table.innerHTML=renderAdminOps(d.operations);
}
async function showAdminUser(id){
  const key=String(id);
  if(adminSelectedUserId!==key){
    document.getElementById('adminUserModal')?.classList.add('hidden');
    const detail=document.getElementById('adminUserDetail');if(detail)detail.innerHTML='';
  }
  adminSelectedUserId=key;adminUserGeneration++;
  return refreshAdminUser(id,adminUserViewOwner(key));
}
async function refreshAdminUser(id,selectionOwner){
  const generation=++adminUserReadGeneration;
  const isCurrent=()=>selectionOwner()&&generation===adminUserReadGeneration;
  if(!isCurrent())return;
  let d;try{d=await api('/api/admin/users/'+encodeURIComponent(id),{},isCurrent)}
  catch(error){if(isCurrent())throw error;return}
  if(!isCurrent())return;
  renderAdminUserDetail(d);
}
function renderAdminUserDetail(d){const u=d.user;adminUserDetail.innerHTML=`<h3>${esc(u.email)}</h3><div class="grid">${adminMetric('Plan',d.entitlements.admin_grant?'Pro+ · Admin':d.entitlements.plan_name)}<div class="card">${operationUsageHtml(d.entitlements)}</div>${adminMetric('Nodes',d.entitlements.nodes_used+' / '+d.entitlements.node_limit)}${adminMetric('AI accounts',d.entitlements.ai_accounts_used+' / '+d.entitlements.ai_account_limit)}${adminMetric('Expansion packs',d.entitlements.expansion_quantity)}${adminMetric('Operations · 30d',d.usage.last30||0)}</div><div class="card" style="margin-top:14px"><div class="row"><div><b>Role</b><div>${esc(adminEnumLabel("role",u.role))}</div></div><div><b>Status</b><select id="adminDetailStatus"><option value="active" ${u.status==='active'?'selected':''}>${esc(adminEnumLabel("account","active"))}</option><option value="disabled" ${u.status==='disabled'?'selected':''}>${esc(adminEnumLabel("account","disabled"))}</option></select></div><div><b>Plan</b><select id="adminDetailPlan"><option value="free" ${d.subscription.plan==='free'?'selected':''}>${esc(adminEnumLabel("plan","free"))}</option><option value="pro" ${d.subscription.plan==='pro'?'selected':''}>${esc(adminEnumLabel("plan","pro"))}</option><option value="pro_plus" ${d.subscription.plan==='pro_plus'?'selected':''}>${esc(adminEnumLabel("plan","pro_plus"))}</option></select></div><div><b>Extra Operations</b><input id="adminDetailBonus" class="input" type="number" min="0" value="${esc((d.admin_overrides||{}).bonus_requests||0)}"></div><div><b>Extra Computers</b><input id="adminDetailBonusNodes" class="input" type="number" min="0" value="${esc((d.admin_overrides||{}).bonus_nodes||0)}"></div><div><b>Extra AI accounts</b><input id="adminDetailBonusAi" class="input" type="number" min="0" value="${esc((d.admin_overrides||{}).bonus_ai_accounts||0)}"></div><div><b>Extra quota expires</b><select id="adminDetailExpiry" onchange="adminExpiryModeChange()"><option value="never">Never</option><option value="7d">7 days</option><option value="30d">30 days</option><option value="custom">Custom</option></select><input id="adminDetailExpiryCustom" class="input hidden" type="datetime-local"></div></div><div class="muted" style="margin-top:10px">${d.admin_overrides?.expired?'Extra quota expired':(d.admin_overrides?.expires_at?wt('Extra quota expires')+' '+new Date(d.admin_overrides.expires_at*1000).toLocaleString():'Extra quota does not expire')}</div><div class="actions"><button class="btn primary" onclick="saveAdminUser('${u.id}')">Save account</button></div></div><h3 style="margin-top:18px">Nodes</h3>${d.nodes.length?'<table class="table"><tbody>'+d.nodes.map(n=>`<tr><td>${esc(n.name)}</td><td>${esc(timefmt(n.updated_at))}</td></tr>`).join('')+'</tbody></table>':'<div class="empty">No nodes.</div>'}${unresolvedOperationsHtml(d.unresolved_operations,true)}<h3 style="margin-top:18px">Recent operations</h3>${renderAdminOps(d.operations.map(o=>({...o,email:u.email,status:o.status||(o.details||{}).status||'success'})))}`;adminUserModal.classList.remove('hidden');if(d.admin_overrides?.expires_at){adminDetailExpiry.value='custom';adminDetailExpiryCustom.classList.remove('hidden');const dt=new Date(d.admin_overrides.expires_at*1000);adminDetailExpiryCustom.value=new Date(dt.getTime()-dt.getTimezoneOffset()*60000).toISOString().slice(0,16)}}
'''
