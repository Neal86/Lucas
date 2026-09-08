from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'src'/'gpt_windows_connector'/'web_billing_runtime.py'

source=subprocess.check_output(['git','show','HEAD:src/gpt_windows_connector/web_billing_runtime.py'],cwd=ROOT,text=True,encoding='utf-8')
tree=ast.parse(source)
js=None
for node in tree.body:
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='BILLING_SCRIPT' for t in node.targets):
        js=ast.literal_eval(node.value)
        break
if js is None:
    raise RuntimeError('BILLING_SCRIPT not found')

js=js.replace("const BILLING_PLAN_RANK={free:0,pro:1,pro_plus:2};\n", """const BILLING_PLAN_RANK={free:0,pro:1,pro_plus:2};
let billingSelectedInterval='month';
function billingSetInterval(interval){billingSelectedInterval=interval==='year'?'year':'month';const y=billingSelectedInterval==='year';const m=billingEl('billingCycleMonth'),a=billingEl('billingCycleYear');if(m){m.classList.toggle('primary',!y);m.classList.toggle('secondary',y)}if(a){a.classList.toggle('primary',y);a.classList.toggle('secondary',!y)}if(billingEl('billingProPrice'))billingEl('billingProPrice').textContent=y?'$95.90':'$9.99';if(billingEl('billingProPeriod'))billingEl('billingProPeriod').textContent=y?'/ year':'/ month';if(billingEl('billingProPlusPrice'))billingEl('billingProPlusPrice').textContent=y?'$191.90':'$19.99';if(billingEl('billingProPlusPeriod'))billingEl('billingProPlusPeriod').textContent=y?'/ year':'/ month';if(billingEl('billingExpansionPrice'))billingEl('billingExpansionPrice').textContent=y?'$143.90/yr':'$14.99/mo';if(state.billing)billingRefreshPlanButtons(state.billing)}
function billingRefreshPlanButtons(s){for(const [plan,id] of [['free','billingChooseFree'],['pro','billingChoosePro'],['pro_plus','billingChooseProPlus']]){const cmp=BILLING_PLAN_RANK[plan]-BILLING_PLAN_RANK[s.plan];const sameInterval=plan==='free'||billingSelectedInterval===(s.billing_interval||'month');billingSetButton(id,cmp===0&&sameInterval?'Current':(cmp===0?'Switch billing':(cmp>0?'Upgrade':'Downgrade')),cmp===0&&sameInterval,cmp===0&&sameInterval?'secondary':'primary')}}
""",1)
js=js.replace("billingEl('billingPrice').textContent=s.monthly_price?'$'+Number(s.monthly_price).toFixed(2)+'/mo':'';", "billingEl('billingPrice').textContent=s.plan==='free'?'$0':(s.billing_interval==='year'?'$'+Number(s.billing_total||0).toFixed(2)+'/yr':'$'+Number(s.billing_total||s.monthly_price||0).toFixed(2)+'/mo');",1)
old="for(const [plan,id] of [['free','billingChooseFree'],['pro','billingChoosePro'],['pro_plus','billingChooseProPlus']]){const cmp=BILLING_PLAN_RANK[plan]-BILLING_PLAN_RANK[s.plan];billingSetButton(id,cmp===0?'Current':(cmp>0?'Upgrade':'Downgrade'),cmp===0,cmp===0?'secondary':'primary')}"
new="const requestedInterval=new URLSearchParams(location.search).get('interval');billingSetInterval(requestedInterval==='year'?'year':(s.billing_interval||'month'));billingRefreshPlanButtons(s);"
if old not in js: raise RuntimeError('plan button marker missing')
js=js.replace(old,new,1)
js=js.replace("const selected=new URLSearchParams(location.search).get('select');if(selected&&selected!==s.plan){await billingChangePlan(selected)}", "const selected=new URLSearchParams(location.search).get('select');if(selected&&(selected!==s.plan||billingSelectedInterval!==(s.billing_interval||'month'))){await billingChangePlan(selected)}",1)
js=js.replace("if(plan===s.plan)return;if(BILLING_PLAN_RANK[plan]<BILLING_PLAN_RANK[s.plan])return billingPortal();const d=await api('/api/billing/checkout',{method:'POST',body:JSON.stringify({plan})});", "if(plan===s.plan&&billingSelectedInterval===(s.billing_interval||'month'))return;if(BILLING_PLAN_RANK[plan]<BILLING_PLAN_RANK[s.plan])return billingPortal();const d=await api('/api/billing/checkout',{method:'POST',body:JSON.stringify({plan,interval:billingSelectedInterval})});",1)
js=js.replace("window.loadBillingView=loadBillingView;", "window.billingSetInterval=billingSetInterval;window.loadBillingView=loadBillingView;",1)

PATH.write_text('from __future__ import annotations\n\nBILLING_SCRIPT = '+repr(js)+'\n',encoding='utf-8')
