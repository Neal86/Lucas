"""Task and activity history rendering with request/session ownership.

History loads are read-only. Obsolete completions must not change newer UI or auth.
"""
from __future__ import annotations

HISTORY_SCRIPT = r'''
// Each history view owns its requests independently; auth changes invalidate both.
const historyRequestSequences={tasks:0,logs:0};
function beginHistoryRequest(view){
  const sequence=++historyRequestSequences[view],generation=loginGeneration,user=state.user;
  return ()=>!!user&&state.user===user&&generation===loginGeneration&&sequence===historyRequestSequences[view];
}
function durationfmt(ms){ms=Math.max(0,Number(ms)||0);const sec=Math.floor(ms/1000),h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60),ss=sec%60;return h?`${h}h ${m}m ${ss}s`:m?`${m}m ${ss}s`:`${ss}s`}
function taskStatusBadge(s){return `<span class="badge ${s==='running'?'online':s==='failed'?'offline':'coming'}">${esc(s)}</span>`}
function toggleTaskRun(card,event){if(event&&event.target.closest('button'))return;card.classList.toggle('expanded');card.setAttribute('aria-expanded',card.classList.contains('expanded')?'true':'false')}
function setAllTaskRuns(expanded){taskRunTable.querySelectorAll('.task-run-card').forEach(card=>{card.classList.toggle('expanded',expanded);card.setAttribute('aria-expanded',expanded?'true':'false')})}
function taskStepRows(x){const subs=Array.isArray(x.details?.sub_operations)?x.details.sub_operations.filter(Boolean):[];if(x.action==='shell.run'&&subs.length){const head=`<tr><td style="width:55%"><b>shell.run batch</b><div class="muted">${subs.length} parsed ${subs.length===1?'operation':'operations'} · batch duration</div></td><td>${esc(x.status)}</td><td style="text-align:right">${esc(durationfmt(x.duration_ms))}</td></tr>`;return head+subs.map(op=>`<tr><td style="width:55%;padding-left:28px"><b>${esc(op)}</b><div class="muted">shell.run · 1 operation</div></td><td>${esc(x.status)}</td><td style="text-align:right" class="muted">—</td></tr>`).join('')}return `<tr><td style="width:55%"><b>${esc(x.action)}</b></td><td>${esc(x.status)}</td><td style="text-align:right">${esc(durationfmt(x.duration_ms))}</td></tr>`}
async function loadTaskRuns(){
  const isCurrent=beginHistoryRequest('tasks');
  if(!isCurrent())return;
  const days=document.getElementById('taskRunDays')?.value||'all';
  let d;
  try{d=await api('/api/task-runs?limit=500&days='+encodeURIComponent(days),{},isCurrent)}
  catch(error){if(isCurrent())throw error;return}
  if(!isCurrent())return;
  renderTaskRuns(d);
}
function renderTaskRuns(d){const runs=d.runs||[];const total=runs.reduce((a,r)=>a+(Number(r.duration_ms)||0),0),summary=d.summary||{};taskRunSummary.innerHTML=`<div class="card"><div class="muted">Task runs</div><div class="metric">${Number(summary.task_runs||0).toLocaleString()}</div></div><div class="card"><div class="muted">Operations</div><div class="metric">${Number(summary.operations||0).toLocaleString()}</div></div><div class="card"><div class="muted">Recorded time</div><div class="metric" style="font-size:22px">${durationfmt(summary.duration_ms||0)}</div></div>`;renderTaskUnresolvedOperations(d.unresolved_operations);if(!runs.length){taskRunTable.innerHTML='<div class="card empty">No Task Runs recorded yet.</div>';return}const controls='<div class="task-run-controls"><button class="btn secondary" onclick="setAllTaskRuns(true)">Expand all</button><button class="btn secondary" onclick="setAllTaskRuns(false)">Collapse all</button></div>';taskRunTable.innerHTML=controls+runs.map(r=>{const expanded=r.status==='running',count=(r.steps||[]).reduce((n,s)=>n+(Number(s.operation_count)||1),0);return `<div class="card task-run-card ${expanded?'expanded':''}" role="button" tabindex="0" aria-expanded="${expanded?'true':'false'}" onclick="toggleTaskRun(this,event)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleTaskRun(this,event)}"><div class="task-run-head"><div class="task-run-title"><span class="task-run-chevron">⌄</span><div><b>${esc(r.title)}</b><div class="muted">${esc(r.node_id)} · ${esc(timefmt(r.started_at))}</div></div></div><div class="task-run-right"><div class="task-run-meta">${count} ${count===1?'operation':'operations'}</div><div>${taskStatusBadge(r.status)}<div class="task-run-duration">${esc(durationfmt(r.duration_ms))}</div></div></div></div><div class="task-run-details"><table class="table"><tbody>${(r.steps||[]).map(taskStepRows).join('')}</tbody></table></div></div>`}).join('')}
async function loadLogs(){
  const isCurrent=beginHistoryRequest('logs');
  if(!isCurrent())return;
  const q=new URLSearchParams({limit:'200'});
  if(logAction.value)q.set('action',logAction.value);
  if(logTarget.value)q.set('target',logTarget.value);
  let d;
  try{d=await api('/api/logs?'+q,{},isCurrent)}
  catch(error){if(isCurrent())throw error;return}
  if(!isCurrent())return;
  renderActivityLogs(d);
}
function renderActivityLogs(d){logTable.innerHTML=d.logs.length?'<table class="table"><thead><tr><th>Time</th><th>Action</th><th>Target</th><th>Details</th></tr></thead><tbody>'+d.logs.map(l=>`<tr><td>${esc(timefmt(l.created_at))}</td><td>${esc(l.action)}</td><td>${esc(l.target||'')}</td><td><pre class="details"><code>${esc(JSON.stringify(l.details||{},null,2))}</code></pre></td></tr>`).join('')+'</tbody></table>':'<div class="card empty">No matching activity.</div>'}
'''
