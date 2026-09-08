from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'src'/'gpt_windows_connector'

def rw(path, old, new):
    text=path.read_text(encoding='utf-8')
    if old not in text:
        raise RuntimeError(f'marker not found in {path}: {old[:120]}')
    path.write_text(text.replace(old,new,1),encoding='utf-8')

# billing backend
p=PKG/'billing.py'
rw(p,
"        self.price_pro=os.getenv('STRIPE_PRICE_PRO','').strip(); self.price_pro_plus=os.getenv('STRIPE_PRICE_PRO_PLUS','').strip(); self.price_expansion=os.getenv('STRIPE_PRICE_EXPANSION','').strip()\n",
"        self.price_pro=os.getenv('STRIPE_PRICE_PRO','').strip(); self.price_pro_plus=os.getenv('STRIPE_PRICE_PRO_PLUS','').strip(); self.price_expansion=os.getenv('STRIPE_PRICE_EXPANSION','').strip()\n        self.price_pro_annual=os.getenv('STRIPE_PRICE_PRO_ANNUAL','').strip(); self.price_pro_plus_annual=os.getenv('STRIPE_PRICE_PRO_PLUS_ANNUAL','').strip(); self.price_expansion_annual=os.getenv('STRIPE_PRICE_EXPANSION_ANNUAL','').strip()\n")
rw(p,
"    @property\n    def configured(self) -> bool:\n        # Backward-compatible meaning for the UI: paid checkout is ready.\n        return self.checkout_configured\n",
"    @property\n    def annual_checkout_configured(self) -> bool:\n        return bool(self.secret and self.price_pro_annual and self.price_pro_plus_annual and self.price_expansion_annual)\n\n    @property\n    def configured(self) -> bool:\n        # Backward-compatible meaning for the UI: paid checkout is ready.\n        return self.checkout_configured\n")
rw(p,
"        out['has_customer']=bool(row and row['billing_customer_id']); out['has_subscription']=bool(row and row['stripe_subscription_id']); out['scheduled_plan']=row['scheduled_plan'] if row else None\n        out['monthly_price']=float(PLANS[ent.plan]['price'])+ent.expansion_quantity*float(EXPANSION['price'])\n",
"        out['has_customer']=bool(row and row['billing_customer_id']); out['has_subscription']=bool(row and row['stripe_subscription_id']); out['scheduled_plan']=row['scheduled_plan'] if row else None\n        stripe_price_id=str(ent.stripe_price_id or '')\n        annual_ids={self.price_pro_annual,self.price_pro_plus_annual}\n        interval='year' if stripe_price_id and stripe_price_id in annual_ids else 'month'\n        out['billing_interval']=interval\n        out['annual_billing_configured']=self.annual_checkout_configured\n        monthly=float(PLANS[ent.plan]['price'])+ent.expansion_quantity*float(EXPANSION['price'])\n        out['monthly_price']=monthly\n        out['billing_total']=round(monthly*12*0.8,2) if interval=='year' else round(monthly,2)\n        out['monthly_equivalent']=round(monthly*0.8,2) if interval=='year' else round(monthly,2)\n")
rw(p,
"    def checkout(self,user,plan: str) -> str:\n        self._require_checkout_configured()\n        if plan not in {'pro','pro_plus'}: raise ValueError('Invalid paid plan')\n",
"    def checkout(self,user,plan: str,interval: str='month') -> str:\n        self._require_checkout_configured()\n        if plan not in {'pro','pro_plus'}: raise ValueError('Invalid paid plan')\n        interval='year' if str(interval).lower() in {'year','annual','yearly'} else 'month'\n        if interval=='year' and not self.annual_checkout_configured:\n            raise RuntimeError('Annual Stripe prices are not configured yet. Add STRIPE_PRICE_PRO_ANNUAL, STRIPE_PRICE_PRO_PLUS_ANNUAL, and STRIPE_PRICE_EXPANSION_ANNUAL.')\n        target_price=(self.price_pro_annual if plan=='pro' else self.price_pro_plus_annual) if interval=='year' else (self.price_pro if plan=='pro' else self.price_pro_plus)\n")
rw(p,
"            current=str(row['plan'] or 'free')\n            if current==plan: return self.base_url+'/billing'\n            if current=='pro_plus' and plan=='pro':\n",
"            current=str(row['plan'] or 'free')\n            current_interval='year' if str(row['stripe_price_id'] or '') in {self.price_pro_annual,self.price_pro_plus_annual} else 'month'\n            if current==plan and current_interval==interval: return self.base_url+'/billing'\n            if current=='pro_plus' and plan=='pro':\n")
rw(p,
"            base_item=next((i for i in sub['items']['data'] if i['price']['id'] in {self.price_pro,self.price_pro_plus}),None)\n            if not base_item: raise RuntimeError('Stripe subscription base item was not found')\n            stripe.SubscriptionItem.modify(base_item['id'],price=self.price_pro_plus,proration_behavior='create_prorations')\n",
"            base_ids={self.price_pro,self.price_pro_plus,self.price_pro_annual,self.price_pro_plus_annual}\n            base_item=next((i for i in sub['items']['data'] if i['price']['id'] in base_ids),None)\n            if not base_item: raise RuntimeError('Stripe subscription base item was not found')\n            stripe.SubscriptionItem.modify(base_item['id'],price=target_price,proration_behavior='create_prorations')\n")
rw(p,
"        price=self.price_pro if plan=='pro' else self.price_pro_plus\n        params={\n          'mode':'subscription','line_items':[{'price':price,'quantity':1}],\n",
"        price=target_price\n        params={\n          'mode':'subscription','line_items':[{'price':price,'quantity':1}],\n")
rw(p,
"          'metadata':{'user_id':user.id,'plan':plan},'subscription_data':{'metadata':{'user_id':user.id,'plan':plan}},\n",
"          'metadata':{'user_id':user.id,'plan':plan,'billing_interval':interval},'subscription_data':{'metadata':{'user_id':user.id,'plan':plan,'billing_interval':interval}},\n")
rw(p,
"        sub=stripe.Subscription.retrieve(str(row['stripe_subscription_id'])); items=list(sub['items']['data'])\n        exp=next((i for i in items if i['price']['id']==self.price_expansion),None); new_qty=ent.expansion_quantity+quantity\n        if exp: stripe.SubscriptionItem.modify(exp['id'],quantity=new_qty,proration_behavior='create_prorations')\n        else: stripe.SubscriptionItem.create(subscription=str(row['stripe_subscription_id']),price=self.price_expansion,quantity=new_qty,proration_behavior='create_prorations')\n",
"        sub=stripe.Subscription.retrieve(str(row['stripe_subscription_id'])); items=list(sub['items']['data'])\n        annual=str(row['stripe_price_id'] or '') in {self.price_pro_annual,self.price_pro_plus_annual}\n        expansion_price=self.price_expansion_annual if annual else self.price_expansion\n        if annual and not expansion_price: raise RuntimeError('Annual Expansion Pack Stripe price is not configured yet.')\n        exp=next((i for i in items if i['price']['id'] in {self.price_expansion,self.price_expansion_annual}),None); new_qty=ent.expansion_quantity+quantity\n        if exp: stripe.SubscriptionItem.modify(exp['id'],price=expansion_price,quantity=new_qty,proration_behavior='create_prorations')\n        else: stripe.SubscriptionItem.create(subscription=str(row['stripe_subscription_id']),price=expansion_price,quantity=new_qty,proration_behavior='create_prorations')\n")
rw(p,
"            if price==self.price_pro: plan='pro'; base_price=price\n            elif price==self.price_pro_plus: plan='pro_plus'; base_price=price\n            elif price==self.price_expansion: expansion=qty\n",
"            if price in {self.price_pro,self.price_pro_annual}: plan='pro'; base_price=price\n            elif price in {self.price_pro_plus,self.price_pro_plus_annual}: plan='pro_plus'; base_price=price\n            elif price in {self.price_expansion,self.price_expansion_annual}: expansion=qty\n")

# web API interval
p=PKG/'webapp.py'
rw(p,
"        user=_auth_user(request); body=await request.json(); url=gateway.billing.checkout(user,str(body.get(\"plan\") or \"\"))\n",
"        user=_auth_user(request); body=await request.json(); url=gateway.billing.checkout(user,str(body.get(\"plan\") or \"\"),str(body.get(\"interval\") or \"month\"))\n")

# pricing page toggle and annual values
p=PKG/'billing_ui.py'
text=p.read_text(encoding='utf-8')
text=text.replace(".plans{display:grid", ".billing-toggle{display:flex;justify-content:center;gap:4px;margin:0 auto 34px;padding:4px;width:max-content;border:1px solid rgba(255,255,255,.12);border-radius:12px;background:rgba(255,255,255,.04)}.billing-toggle button{border:0;border-radius:9px;padding:9px 16px;background:transparent;color:#9aa4bb;font-weight:750;cursor:pointer}.billing-toggle button.active{background:#fff;color:#111827}.save{font-size:11px;color:#70dfa9;margin-left:5px}.plans{display:grid",1)
text=text.replace('</section><section class="plans">','</section><div class="billing-toggle"><button id="monthlyBtn" class="active" onclick="setPricingInterval(\'month\')">Monthly</button><button id="annualBtn" onclick="setPricingInterval(\'year\')">Annual <span class="save">Save 20%</span></button></div><section class="plans">',1)
text=text.replace('<div class="price">$9.99 <small>/ month</small></div>','<div class="price"><span id="proPrice">$9.99</span> <small id="proPeriod">/ month</small></div>',1)
text=text.replace('href="/billing?select=pro"','id="proLink" href="/billing?select=pro&interval=month"',1)
text=text.replace('<div class="price">$19.99 <small>/ month</small></div>','<div class="price"><span id="proPlusPrice">$19.99</span> <small id="proPlusPeriod">/ month</small></div>',1)
text=text.replace('href="/billing?select=pro_plus"','id="proPlusLink" href="/billing?select=pro_plus&interval=month"',1)
text=text.replace('<strong>$14.99 <small>/ month</small></strong>','<strong><span id="expansionPrice">$14.99</span> <small id="expansionPeriod">/ month</small></strong>',1)
text=text.replace('</div></body></html>\'\'\'','</div><script>function setPricingInterval(i){const y=i===\'year\';document.getElementById(\'monthlyBtn\').classList.toggle(\'active\',!y);document.getElementById(\'annualBtn\').classList.toggle(\'active\',y);document.getElementById(\'proPrice\').textContent=y?\'$95.90\':\'$9.99\';document.getElementById(\'proPeriod\').textContent=y?\'/ year\':\'/ month\';document.getElementById(\'proPlusPrice\').textContent=y?\'$191.90\':\'$19.99\';document.getElementById(\'proPlusPeriod\').textContent=y?\'/ year\':\'/ month\';document.getElementById(\'expansionPrice\').textContent=y?\'$143.90\':\'$14.99\';document.getElementById(\'expansionPeriod\').textContent=y?\'/ year\':\'/ month\';document.getElementById(\'proLink\').href=\'/billing?select=pro&interval=\'+i;document.getElementById(\'proPlusLink\').href=\'/billing?select=pro_plus&interval=\'+i}const q=new URLSearchParams(location.search);if(q.get(\'interval\')===\'year\')setPricingInterval(\'year\');</script></body></html>\'\'\'',1)
# dashboard billing toggle / IDs
text=text.replace('<div class="top" style="margin-bottom:14px"><div><h3 style="margin-bottom:4px">Plans</h3><div class="muted">Change plans anytime. Expansion Packs are Pro+ only.</div></div></div>', '<div class="top" style="margin-bottom:14px"><div><h3 style="margin-bottom:4px">Plans</h3><div class="muted">Pay monthly at regular price, or annually and save 20%.</div></div><div class="billing-cycle-toggle"><button id="billingCycleMonth" class="btn secondary" onclick="billingSetInterval(\'month\')">Monthly</button><button id="billingCycleYear" class="btn secondary" onclick="billingSetInterval(\'year\')">Annual · Save 20%</button></div></div>',1)
text=text.replace('<div class="billing-plan-price">$9.99 <small>/ month</small></div>','<div class="billing-plan-price"><span id="billingProPrice">$9.99</span> <small id="billingProPeriod">/ month</small></div>',1)
text=text.replace('<div class="billing-plan-price">$19.99 <small>/ month</small></div>','<div class="billing-plan-price"><span id="billingProPlusPrice">$19.99</span> <small id="billingProPlusPeriod">/ month</small></div>',1)
text=text.replace('<h3 style="margin-bottom:5px">Expansion Pack · $14.99/mo</h3>','<h3 style="margin-bottom:5px">Expansion Pack · <span id="billingExpansionPrice">$14.99/mo</span></h3>',1)
p.write_text(text,encoding='utf-8')

# dashboard runtime replace entirely with derived string edits
p=PKG/'web_billing_runtime.py'
text=p.read_text(encoding='utf-8')
text=text.replace("const BILLING_PLAN_RANK={free:0,pro:1,pro_plus:2};\\n", "const BILLING_PLAN_RANK={free:0,pro:1,pro_plus:2};\\nlet billingSelectedInterval='month';\\nfunction billingSetInterval(interval){billingSelectedInterval=interval==='year'?'year':'month';const y=billingSelectedInterval==='year';const m=billingEl('billingCycleMonth'),a=billingEl('billingCycleYear');if(m)m.classList.toggle('primary',!y);if(a)a.classList.toggle('primary',y);if(billingEl('billingProPrice'))billingEl('billingProPrice').textContent=y?'$95.90':'$9.99';if(billingEl('billingProPeriod'))billingEl('billingProPeriod').textContent=y?'/ year':'/ month';if(billingEl('billingProPlusPrice'))billingEl('billingProPlusPrice').textContent=y?'$191.90':'$19.99';if(billingEl('billingProPlusPeriod'))billingEl('billingProPlusPeriod').textContent=y?'/ year':'/ month';if(billingEl('billingExpansionPrice'))billingEl('billingExpansionPrice').textContent=y?'$143.90/yr':'$14.99/mo';if(state.billing)billingRefreshPlanButtons(state.billing)}\\nfunction billingRefreshPlanButtons(s){for(const [plan,id] of [['free','billingChooseFree'],['pro','billingChoosePro'],['pro_plus','billingChooseProPlus']]){const cmp=BILLING_PLAN_RANK[plan]-BILLING_PLAN_RANK[s.plan];const sameInterval=plan==='free'||billingSelectedInterval===(s.billing_interval||'month');billingSetButton(id,cmp===0&&sameInterval?'Current':(cmp===0?'Switch billing':(cmp>0?'Upgrade':'Downgrade')),cmp===0&&sameInterval,cmp===0&&sameInterval?'secondary':'primary')}}\\n",1)
text=text.replace("billingEl('billingPrice').textContent=s.monthly_price?'$'+Number(s.monthly_price).toFixed(2)+'/mo':'';", "billingEl('billingPrice').textContent=s.plan==='free'?'$0':((s.billing_interval==='year'?'$'+Number(s.billing_total||0).toFixed(2)+'/yr':'$'+Number(s.billing_total||s.monthly_price||0).toFixed(2)+'/mo'));",1)
text=text.replace("for(const [plan,id] of [['free','billingChooseFree'],['pro','billingChoosePro'],['pro_plus','billingChooseProPlus']]){const cmp=BILLING_PLAN_RANK[plan]-BILLING_PLAN_RANK[s.plan];billingSetButton(id,cmp===0?'Current':(cmp>0?'Upgrade':'Downgrade'),cmp===0,cmp===0?'secondary':'primary')}", "const requestedInterval=new URLSearchParams(location.search).get('interval');billingSetInterval(requestedInterval==='year'?'year':(s.billing_interval||'month'));billingRefreshPlanButtons(s);",1)
text=text.replace("const selected=new URLSearchParams(location.search).get('select');if(selected&&selected!==s.plan){await billingChangePlan(selected)}", "const selected=new URLSearchParams(location.search).get('select');if(selected&&(selected!==s.plan||billingSelectedInterval!==(s.billing_interval||'month'))){await billingChangePlan(selected)}",1)
text=text.replace("if(plan===s.plan)return;if(BILLING_PLAN_RANK[plan]<BILLING_PLAN_RANK[s.plan])return billingPortal();const d=await api('/api/billing/checkout',{method:'POST',body:JSON.stringify({plan})});", "if(plan===s.plan&&billingSelectedInterval===(s.billing_interval||'month'))return;if(BILLING_PLAN_RANK[plan]<BILLING_PLAN_RANK[s.plan])return billingPortal();const d=await api('/api/billing/checkout',{method:'POST',body:JSON.stringify({plan,interval:billingSelectedInterval})});",1)
text=text.replace("window.loadBillingView=loadBillingView;", "window.billingSetInterval=billingSetInterval;window.loadBillingView=loadBillingView;",1)
p.write_text(text,encoding='utf-8')

# env and compose
for rel in ['.env.example','docker-compose.yml']:
    p=ROOT/rel
    text=p.read_text(encoding='utf-8')
    marker='STRIPE_PRICE_PRO_PLUS'
    if 'STRIPE_PRICE_PRO_ANNUAL' not in text:
        lines=text.splitlines()
        out=[]
        inserted=False
        for line in lines:
            out.append(line)
            if marker in line and not inserted:
                indent=line[:len(line)-len(line.lstrip())]
                if rel=='.env.example':
                    out += ['STRIPE_PRICE_PRO_ANNUAL=','STRIPE_PRICE_PRO_PLUS_ANNUAL=','STRIPE_PRICE_EXPANSION_ANNUAL=']
                else:
                    out += [indent+'STRIPE_PRICE_PRO_ANNUAL: ${STRIPE_PRICE_PRO_ANNUAL:-}',indent+'STRIPE_PRICE_PRO_PLUS_ANNUAL: ${STRIPE_PRICE_PRO_PLUS_ANNUAL:-}',indent+'STRIPE_PRICE_EXPANSION_ANNUAL: ${STRIPE_PRICE_EXPANSION_ANNUAL:-}']
                inserted=True
        p.write_text('\n'.join(out)+'\n',encoding='utf-8')

# tests
p=ROOT/'tests'/'test_billing_contract.py'
text=p.read_text(encoding='utf-8')
text=text.replace('for text in ["$9.99","$19.99","$14.99","1,000 Requests","25,000 Requests","100,000 Requests","6 Computers","Pro+ only"]:', 'for text in ["$9.99","$19.99","$14.99","$95.90","$191.90","$143.90","Save 20%","1,000 Requests","25,000 Requests","100,000 Requests","6 Computers","Pro+ only"]:',1)
text=text.replace('for key in ["STRIPE_SECRET_KEY","STRIPE_WEBHOOK_SECRET","STRIPE_PRICE_PRO","STRIPE_PRICE_PRO_PLUS","STRIPE_PRICE_EXPANSION"]:', 'for key in ["STRIPE_SECRET_KEY","STRIPE_WEBHOOK_SECRET","STRIPE_PRICE_PRO","STRIPE_PRICE_PRO_PLUS","STRIPE_PRICE_EXPANSION","STRIPE_PRICE_PRO_ANNUAL","STRIPE_PRICE_PRO_PLUS_ANNUAL","STRIPE_PRICE_EXPANSION_ANNUAL"]:',1)
if 'test_annual_billing_discount_contract' not in text:
    text += '''\n\ndef test_annual_billing_discount_contract():\n    billing=Path("src/gpt_windows_connector/billing.py").read_text(encoding="utf-8")\n    assert "STRIPE_PRICE_PRO_ANNUAL" in billing\n    assert "STRIPE_PRICE_PRO_PLUS_ANNUAL" in billing\n    assert "STRIPE_PRICE_EXPANSION_ANNUAL" in billing\n    assert "monthly*12*0.8" in billing\n    runtime=Path("src/gpt_windows_connector/web_billing_runtime.py").read_text(encoding="utf-8")\n    assert "billingSelectedInterval" in runtime\n    assert "interval:billingSelectedInterval" in runtime\n'''
p.write_text(text,encoding='utf-8')
