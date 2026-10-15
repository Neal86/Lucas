"""Shared presentation of completed usage and unresolved admission reservations.

Quota decisions and lifecycle transitions belong to operation_admission and
entitlements. This runtime only renders their projection; it never retries,
releases, refunds, or infers execution results from reservation counts.
"""
from __future__ import annotations

OPERATION_USAGE_SCRIPT = r'''
function operationNumber(value, fallback='—') {
  if (value === undefined || value === null || value === '') return fallback;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number.toLocaleString() : fallback;
}
function operationDate(value) {
  const date = new Date(Number(value) * 1000);
  return value && Number.isFinite(date.getTime()) ? date.toLocaleString() : '—';
}
function operationUsageHelp(admin=false) {
  const notes = [
    'Held units are reserved minimum quota, not confirmed executed Operations or a parsed shell-operation count.',
    'Pending actions become outcome unconfirmed after their deadline. A timeout does not prove execution failed.',
    'Held units are attributed by admission time within the current billing period. Beta quota resets monthly; historical records remain reviewable.',
    'There is no automatic retry or quota refund.'
  ];
  if (admin) notes.push('After review, an administrator can grant replacement capacity with the existing Extra Operations control. This does not resolve the execution outcome.');
  return `<details data-operation-help><summary>${esc(wt('How held quota works'))}</summary>${notes.map(note=>`<p class="muted">${esc(wt(note))}</p>`).join('')}</details>`;
}
function operationUsageHtml(snapshot={}) {
  const fields = [
    ['completed','Completed Operations',snapshot.requests_used],
    ['pending','Pending held units',snapshot.requests_pending ?? 0],
    ['unconfirmed','Unconfirmed held units',snapshot.requests_unconfirmed ?? 0],
    ['remaining','Remaining Operations',snapshot.request_remaining],
    ['limit','Operation limit',snapshot.request_limit]
  ];
  return `<section data-operation-usage aria-label="${esc(wt('Operation quota'))}">${fields.map(([key,label,value])=>`<div><span class="muted">${esc(wt(label))}: </span><b data-operation-count="${key}">${esc(operationNumber(value))}</b></div>`).join('')}<p class="muted" data-operation-reset>${esc(wt('Period reset'))}: ${esc(operationDate(snapshot.period_end))}</p>${operationUsageHelp()}</section>`;
}
function renderOperationUsage(id, snapshot, barId=null) {
  const target = document.getElementById(id);
  if (!target) return;
  target.classList.remove('metric');
  target.innerHTML = operationUsageHtml(snapshot || {});
  const bar = barId && document.getElementById(barId)?.querySelector('i');
  if (bar) {
    const limit = Number(snapshot?.request_limit), remaining = Number(snapshot?.request_remaining);
    const known = snapshot?.request_remaining != null && Number.isFinite(limit) && limit > 0 && Number.isFinite(remaining);
    bar.style.width = (known ? Math.min(100,Math.max(0,Math.round((1-remaining/limit)*100))) : 0) + '%';
    bar.parentNode?.setAttribute('aria-label',wt('Quota consumed or held'));
  }
}
function unresolvedOperationsHtml(rows, admin=false) {
  rows = Array.isArray(rows) ? rows.filter(row=>row && ['pending','outcome_unconfirmed'].includes(row.status)) : [];
  const records = rows.map(row=>{
    const accounting = row.status === 'outcome_unconfirmed' && row.details?.reason === 'accounting_failed';
    const status = row.status === 'pending' ? 'Pending' : (accounting ? 'Accounting unconfirmed' : 'Outcome unconfirmed');
    const held = row.currently_held === true;
    const fields = [
      ['Computer',row.node_id],['Target',row.target],
      ['Reserved minimum',operationNumber(row.reserved_operations)+' '+wt('quota units')],
      ['Started',operationDate(row.started_at)],['Confirmation deadline',operationDate(row.deadline_at)],
      ['Admission period ends',operationDate(row.period_end)]
    ];
    for (const [label,key] of [['Source','source'],['AI client','agent'],['Session','session_id'],['Task title','task_title']]) {
      const value = row.details?.[key];
      if (typeof value === 'string' && value) fields.push([label,value]);
    }
    const outcome = row.details?.confirmed_outcome;
    if (accounting && ['success','failed'].includes(outcome)) {
      fields.push(['Confirmed execution outcome',wt(outcome === 'success' ? 'Success' : 'Failure')]);
    }
    return `<article class="card field" data-operation-id="${esc(row.id)}" data-operation-status="${row.status}" data-currently-held="${held}"><h4 class="path">${esc(row.action)}</h4><p><span class="badge coming">${esc(wt(status))}</span></p>${accounting ? `<p class="muted" data-operation-review="accounting">${esc(wt('Execution result received; accounting needs review.'))}</p>` : ''}<p class="muted">${esc(wt(held?'Currently held':'Historical · not currently held'))}</p>${fields.map(([label,value])=>`<div class="path"><b>${esc(wt(label))}: </b>${esc(value || '—')}</div>`).join('')}</article>`;
  }).join('');
  return `<section data-unresolved-operations aria-label="${esc(wt('Unresolved actions'))}"><h3>${esc(wt('Unresolved actions'))}</h3><p class="muted">${esc(wt('Records shown'))}: <b data-unresolved-count>${rows.length}</b>. ${esc(wt('These records are separate from completed task-step success and failure totals.'))}</p>${operationUsageHelp(admin)}${records || `<p class="empty">${esc(wt('No unresolved actions in this view.'))}</p>`}</section>`;
}
function renderTaskUnresolvedOperations(rows) {
  let target = document.getElementById('taskRunUnresolved');
  const completed = document.getElementById('taskRunTable');
  if (!target && completed) {
    target = document.createElement('div');
    target.id = 'taskRunUnresolved';
    target.className = 'card field';
    completed.parentNode.insertBefore(target,completed);
  }
  if (target) target.innerHTML = unresolvedOperationsHtml(rows);
}
'''
