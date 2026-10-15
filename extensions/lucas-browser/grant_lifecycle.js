// Local tab authorization is independent of the bridge's asynchronous replies.
// Cancellation invalidates pending setup, acknowledgements and later dispatches;
// it cannot undo a command already handed to Chrome.
export class GrantLifecycle {
  constructor({getTab, attach, detach, send}) {
    this.getTab=getTab; this.attach=attach; this.detach=detach; this.send=send;
    this.connection=null; this.generation=0;
    this.pending=new Map(); this.grants=new Map();
    this.attached=new Set(); this.attachmentEpoch=new Map(); this.tabQueues=new Map();
  }

  replaceConnection(connection) {
    this.revokeAll(false);
    this.connection=connection;
  }

  current(connection) {
    return !!connection && connection===this.connection && connection.readyState===1;
  }

  pendingValid(request) {
    return this.current(request.connection) && request.generation===this.generation && this.pending.get(request.id)===request;
  }

  assertPending(request) {
    if(!this.pendingValid(request)) throw Error('Tab authorization was cancelled; authorize it again');
  }

  serial(tab, operation) {
    const previous=this.tabQueues.get(tab)||Promise.resolve();
    const next=previous.catch(()=>{}).then(operation);
    this.tabQueues.set(tab,next);
    const clear=()=>{if(this.tabQueues.get(tab)===next) this.tabQueues.delete(tab);};
    next.then(clear,clear);
    return next;
  }

  wanted(tab) {
    return [...this.pending.values()].some(r=>r.tab_id===tab) || [...this.grants.values()].some(g=>g.tab_id===tab);
  }

  cleanup(tab) {
    // A new request may arrive while an old attach/detach is awaiting Chrome.
    // All attachment changes share this queue, but remote actions have their
    // own queue and are additionally guarded at every protocol dispatch.
    return this.serial(tab,async()=>{
      if(this.wanted(tab)||!this.attached.has(tab)) return;
      this.attached.delete(tab);
      try { await this.detach(tab); } catch {}
    });
  }

  dropPending(request) {
    if(this.pending.get(request.id)!==request) return;
    this.pending.delete(request.id); clearTimeout(request.timer);
  }

  async request(connection,owner,tab) {
    const request={id:crypto.randomUUID(),connection,generation:this.generation,owner_id:owner,tab_id:tab};
    if(!this.current(connection)) throw Error('Pair the browser first');
    this.pending.set(request.id,request);
    request.timer=setTimeout(()=>{
      this.dropPending(request); void this.cleanup(tab);
    },30000);
    try {
      const page=await this.getTab(tab); this.assertPending(request);
      if(!/^https?:\/\//i.test(page.url||'')) throw Error('Only HTTP(S) tabs can be authorized');
      await this.serial(tab,async()=>{
        this.assertPending(request);
        if(!this.attached.has(tab)) {
          const epoch=this.attachmentEpoch.get(tab)||0;
          await this.attach(tab);
          // Chrome's earlier attach reply may arrive after an external detach.
          // That reply must not make a newer request reuse a phantom attachment.
          if((this.attachmentEpoch.get(tab)||0)===epoch) this.attached.add(tab);
        }
        this.assertPending(request);
      });
      this.assertPending(request);
      this.send(connection,{type:'grant',request_id:request.id,owner_id:owner,tab_id:tab,title:page.title,url:page.url});
      return {ok:true};
    } catch(error) {
      this.dropPending(request); void this.cleanup(tab); throw error;
    }
  }

  rejectAcknowledgement(connection,msg,request) {
    // Never leave a local session behind after telling its bridge to revoke it.
    if(this.grants.get(msg.session_id)?.connection===connection) this.revoke(msg.session_id,false);
    if(typeof msg.session_id==='string' && msg.session_id) this.send(connection,{type:'revoke',session_id:msg.session_id});
    if(request) { this.dropPending(request); void this.cleanup(request.tab_id); }
    return false;
  }

  async acknowledge(connection,msg) {
    const duplicate=()=>{
      const existing=this.grants.get(msg.session_id);
      return existing && existing.connection===connection && existing.request_id===msg.request_id && existing.tab_id===msg.tab_id && existing.owner_id===msg.owner_id;
    };
    if(duplicate()) return false;
    const request=this.pending.get(msg.request_id);
    if(!request || !this.pendingValid(request) || request.connection!==connection || request.tab_id!==msg.tab_id || request.owner_id!==msg.owner_id || typeof msg.session_id!=='string' || !msg.session_id.startsWith('ext-')) {
      return this.rejectAcknowledgement(connection,msg,request);
    }
    // A bridge close can arrive while the acknowledgement's tab lookup waits.
    // Bind its session before that await so revoke can cancel pending adoption.
    if(request.session_id && request.session_id!==msg.session_id) return this.rejectAcknowledgement(connection,msg);
    request.session_id=msg.session_id;
    const page=await this.getTab(request.tab_id).catch(()=>null);
    if(duplicate()) return false;
    if(!this.pendingValid(request) || !page || !/^https?:\/\//i.test(page.url||'')) return this.rejectAcknowledgement(connection,msg,request);
    this.dropPending(request);
    this.grants.set(msg.session_id,{...msg,title:page.title,connection,generation:request.generation});
    return true;
  }

  reject(connection,msg) {
    let matched=false;
    for(const request of [...this.pending.values()]) {
      if(request.connection===connection && (!msg.request_id || request.id===msg.request_id)) {
        matched=true;
        this.dropPending(request); void this.cleanup(request.tab_id);
      }
    }
    return matched;
  }

  revoke(sid,notify=true) {
    for(const request of [...this.pending.values()]) {
      if(request.session_id===sid) {
        this.dropPending(request); void this.cleanup(request.tab_id);
        if(notify) this.send(request.connection,{type:'revoke',session_id:sid});
      }
    }
    const grant=this.grants.get(sid); if(!grant) return;
    this.grants.delete(sid);
    if(notify) this.send(grant.connection,{type:'revoke',session_id:sid});
    void this.cleanup(grant.tab_id);
  }

  revokeAll(notify=true) {
    ++this.generation;
    const tabs=new Set([...this.pending.values()].map(r=>r.tab_id));
    for(const request of [...this.pending.values()]) this.dropPending(request);
    for(const [sid,grant] of [...this.grants]) { tabs.add(grant.tab_id); this.revoke(sid,notify); }
    for(const tab of tabs) void this.cleanup(tab);
  }

  removeTab(tab,detached=false) {
    this.attachmentEpoch.set(tab,(this.attachmentEpoch.get(tab)||0)+1);
    if(detached) this.attached.delete(tab);
    // Explicit debugger.detach does not emit onDetach. A real event remains a
    // cancellation even while cleanup is waiting or a new request is queued.
    for(const request of [...this.pending.values()]) if(request.tab_id===tab) this.dropPending(request);
    for(const [sid,grant] of [...this.grants]) if(grant.tab_id===tab) this.revoke(sid);
    void this.cleanup(tab);
  }

  guard(connection,sid,tab) {
    const grant=this.grants.get(sid);
    const check=()=>{
      if(!grant || !this.current(connection) || grant.connection!==connection || grant.generation!==this.generation || this.grants.get(sid)!==grant || grant.tab_id!==tab) throw Error('Tab is not authorized');
    };
    check(); return check;
  }

  sessions() {
    return [...this.grants.values()].map(({session_id,tab_id,owner_id,title})=>({session_id,tab_id,owner_id,title}));
  }
}
