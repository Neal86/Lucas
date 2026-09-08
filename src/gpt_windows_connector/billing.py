from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import stripe

from .entitlements import ACTIVE_STATUSES, EXPANSION, PLANS, snapshot
from .referrals import ReferralService


class BillingService:
    def __init__(self, db_path: Path, base_url: str) -> None:
        self.db_path=Path(db_path); self.base_url=base_url.rstrip('/')
        self.secret=os.getenv('STRIPE_SECRET_KEY','').strip(); self.webhook_secret=os.getenv('STRIPE_WEBHOOK_SECRET','').strip()
        self.price_pro=os.getenv('STRIPE_PRICE_PRO','').strip(); self.price_pro_plus=os.getenv('STRIPE_PRICE_PRO_PLUS','').strip(); self.price_expansion=os.getenv('STRIPE_PRICE_EXPANSION','').strip()
        self._init_db()
        self.referrals=ReferralService(self.db_path,self.base_url)
        if self.secret: stripe.api_key=self.secret

    def _connect(self):
        db=sqlite3.connect(self.db_path,timeout=30); db.row_factory=sqlite3.Row; return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO subscriptions(user_id,plan,status,updated_at) SELECT id,'free','inactive',? FROM users",(time.time(),))
            cols={r[1] for r in db.execute('PRAGMA table_info(subscriptions)').fetchall()}
            additions={
                'stripe_subscription_id':'TEXT','stripe_price_id':'TEXT','expansion_quantity':'INTEGER NOT NULL DEFAULT 0',
                'current_period_start':'REAL','current_period_end':'REAL','cancel_at_period_end':'INTEGER NOT NULL DEFAULT 0',
                'scheduled_plan':'TEXT','last_synced_at':'REAL','bonus_requests':'INTEGER NOT NULL DEFAULT 0',
            }
            for name,typ in additions.items():
                if name not in cols: db.execute(f'ALTER TABLE subscriptions ADD COLUMN {name} {typ}')
            db.executescript("""
            CREATE TABLE IF NOT EXISTS billing_events(
              stripe_event_id TEXT PRIMARY KEY,event_type TEXT NOT NULL,payload_hash TEXT NOT NULL,processed_at REAL NOT NULL,result TEXT NOT NULL DEFAULT 'processed'
            );
            CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer ON subscriptions(billing_customer_id);
            CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_subscription ON subscriptions(stripe_subscription_id);
            """)

    @property
    def webhook_configured(self) -> bool:
        return bool(self.secret and self.webhook_secret)

    @property
    def checkout_configured(self) -> bool:
        return bool(self.secret and self.price_pro and self.price_pro_plus and self.price_expansion)

    @property
    def configured(self) -> bool:
        # Backward-compatible meaning for the UI: paid checkout is ready.
        return self.checkout_configured

    def summary(self,user_id: str) -> dict[str,Any]:
        ent=snapshot(self.db_path,user_id); out=ent.as_dict(); out['billing_configured']=self.checkout_configured; out['webhook_configured']=self.webhook_configured
        with self._connect() as db:
            row=db.execute('SELECT billing_customer_id,stripe_subscription_id,scheduled_plan FROM subscriptions WHERE user_id=?',(user_id,)).fetchone()
        out['has_customer']=bool(row and row['billing_customer_id']); out['has_subscription']=bool(row and row['stripe_subscription_id']); out['scheduled_plan']=row['scheduled_plan'] if row else None
        out['monthly_price']=float(PLANS[ent.plan]['price'])+ent.expansion_quantity*float(EXPANSION['price'])
        return out

    def _require_checkout_configured(self) -> None:
        if not self.checkout_configured: raise RuntimeError('Stripe checkout is not configured yet. Add the Stripe Price IDs first.')

    def _require_webhook_configured(self) -> None:
        if not self.webhook_configured: raise RuntimeError('Stripe webhook is not configured yet.')

    def _sub_row(self,user_id: str):
        with self._connect() as db: return db.execute('SELECT * FROM subscriptions WHERE user_id=?',(user_id,)).fetchone()

    def checkout(self,user,plan: str) -> str:
        self._require_checkout_configured()
        if plan not in {'pro','pro_plus'}: raise ValueError('Invalid paid plan')
        row=self._sub_row(user.id)
        if row and row['stripe_subscription_id'] and str(row['status']) in ACTIVE_STATUSES:
            current=str(row['plan'] or 'free')
            if current==plan: return self.base_url+'/billing'
            if current=='pro_plus' and plan=='pro':
                raise ValueError('Downgrades take effect next cycle. Use Manage Billing to schedule the downgrade.')
            sub=stripe.Subscription.retrieve(str(row['stripe_subscription_id']))
            base_item=next((i for i in sub['items']['data'] if i['price']['id'] in {self.price_pro,self.price_pro_plus}),None)
            if not base_item: raise RuntimeError('Stripe subscription base item was not found')
            stripe.SubscriptionItem.modify(base_item['id'],price=self.price_pro_plus,proration_behavior='create_prorations')
            return self.base_url+'/billing?updated=1'
        price=self.price_pro if plan=='pro' else self.price_pro_plus
        params={
          'mode':'subscription','line_items':[{'price':price,'quantity':1}],
          'success_url':self.base_url+'/billing/success?session_id={CHECKOUT_SESSION_ID}',
          'cancel_url':self.base_url+'/billing/cancel','client_reference_id':user.id,'customer_email':user.email,
          'metadata':{'user_id':user.id,'plan':plan},'subscription_data':{'metadata':{'user_id':user.id,'plan':plan}},
          'allow_promotion_codes':True,
        }
        session=stripe.checkout.Session.create(**params); return str(session.url)

    def add_expansion(self,user_id: str,quantity: int=1) -> str:
        self._require_checkout_configured(); quantity=max(1,min(int(quantity),100)); ent=snapshot(self.db_path,user_id)
        if not ent.can_buy_expansion: raise PermissionError('Expansion Packs are available only on Pro+. Upgrade to Pro+ first.')
        row=self._sub_row(user_id)
        if not row or not row['stripe_subscription_id']: raise RuntimeError('Active Stripe subscription not found')
        sub=stripe.Subscription.retrieve(str(row['stripe_subscription_id'])); items=list(sub['items']['data'])
        exp=next((i for i in items if i['price']['id']==self.price_expansion),None); new_qty=ent.expansion_quantity+quantity
        if exp: stripe.SubscriptionItem.modify(exp['id'],quantity=new_qty,proration_behavior='create_prorations')
        else: stripe.SubscriptionItem.create(subscription=str(row['stripe_subscription_id']),price=self.price_expansion,quantity=new_qty,proration_behavior='create_prorations')
        return self.base_url+'/billing?expansion=1'

    def portal(self,user_id: str) -> str:
        if not self.secret: raise RuntimeError('Stripe API key is not configured yet.')
        row=self._sub_row(user_id)
        if not row or not row['billing_customer_id']: raise ValueError('No Stripe customer exists for this account yet')
        s=stripe.billing_portal.Session.create(customer=str(row['billing_customer_id']),return_url=self.base_url+'/billing'); return str(s.url)

    def _value(self,obj,key,default=None):
        try: return obj[key]
        except Exception: return getattr(obj,key,default)

    def sync_subscription(self,sub: Any) -> None:
        sid=str(self._value(sub,'id','') or ''); customer=str(self._value(sub,'customer','') or ''); metadata=self._value(sub,'metadata',{}) or {}
        user_id=str(self._value(metadata,'user_id','') or '')
        with self._connect() as db:
            if not user_id and customer:
                r=db.execute('SELECT user_id FROM subscriptions WHERE billing_customer_id=?',(customer,)).fetchone(); user_id=str(r[0]) if r else ''
            if not user_id and sid:
                r=db.execute('SELECT user_id FROM subscriptions WHERE stripe_subscription_id=?',(sid,)).fetchone(); user_id=str(r[0]) if r else ''
        if not user_id: return
        items=self._value(self._value(sub,'items',{}),'data',[]) or []; plan='free'; base_price=''; expansion=0
        for item in items:
            price=self._value(self._value(item,'price',{}),'id',''); qty=int(self._value(item,'quantity',1) or 1)
            if price==self.price_pro: plan='pro'; base_price=price
            elif price==self.price_pro_plus: plan='pro_plus'; base_price=price
            elif price==self.price_expansion: expansion=qty
        if plan!='pro_plus': expansion=0
        status=str(self._value(sub,'status','inactive')); start=float(self._value(sub,'current_period_start',0) or 0); end=float(self._value(sub,'current_period_end',0) or 0); cancel=1 if self._value(sub,'cancel_at_period_end',False) else 0
        with self._connect() as db:
            db.execute("UPDATE subscriptions SET plan=?,status=?,billing_provider='stripe',billing_customer_id=?,stripe_subscription_id=?,stripe_price_id=?,expansion_quantity=?,current_period_start=?,current_period_end=?,cancel_at_period_end=?,started_at=COALESCE(started_at,?),ends_at=?,updated_at=?,last_synced_at=? WHERE user_id=?",(plan,status,customer,sid,base_price,expansion,start,end,cancel,start or time.time(),end or None,time.time(),time.time(),user_id))

    def handle_webhook(self,payload: bytes,signature: str) -> str:
        self._require_webhook_configured(); event=stripe.Webhook.construct_event(payload,signature,self.webhook_secret); eid=str(event['id']); etype=str(event['type']); digest=hashlib.sha256(payload).hexdigest()
        with self._connect() as db:
            if db.execute('SELECT 1 FROM billing_events WHERE stripe_event_id=?',(eid,)).fetchone(): return 'duplicate'
        obj=event['data']['object']
        if etype=='checkout.session.completed':
            uid=str(obj.get('client_reference_id') or (obj.get('metadata') or {}).get('user_id') or ''); customer=str(obj.get('customer') or ''); sid=str(obj.get('subscription') or '')
            if uid:
                with self._connect() as db: db.execute("UPDATE subscriptions SET billing_provider='stripe',billing_customer_id=?,stripe_subscription_id=?,updated_at=? WHERE user_id=?",(customer,sid,time.time(),uid))
            if sid: self.sync_subscription(stripe.Subscription.retrieve(sid))
        elif etype.startswith('customer.subscription.'):
            self.sync_subscription(obj)
            if etype=='customer.subscription.deleted':
                sid=str(obj.get('id') or '')
                with self._connect() as db: db.execute("UPDATE subscriptions SET plan='free',status='inactive',expansion_quantity=0,cancel_at_period_end=0,scheduled_plan=NULL,updated_at=? WHERE stripe_subscription_id=?",(time.time(),sid))
        elif etype in {'invoice.paid','invoice.payment_failed'}:
            sid=str(obj.get('subscription') or '')
            if sid:
                self.sync_subscription(stripe.Subscription.retrieve(sid))
                if etype=='invoice.payment_failed':
                    with self._connect() as db: db.execute("UPDATE subscriptions SET status='past_due',updated_at=? WHERE stripe_subscription_id=?",(time.time(),sid))
                elif etype=='invoice.paid':
                    uid=self.referrals.resolve_user_from_invoice(obj)
                    if uid: self.referrals.qualify_paid_user(uid,eid)
        with self._connect() as db: db.execute('INSERT INTO billing_events(stripe_event_id,event_type,payload_hash,processed_at,result) VALUES(?,?,?,?,?)',(eid,etype,digest,time.time(),'processed'))
        return 'processed'
