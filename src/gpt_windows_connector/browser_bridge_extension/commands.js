(() => {
  const queues = new Map();
  const safeUrl = value => {
    const url = String(value || 'about:blank');
    if (url !== 'about:blank') LucasAccess.cleanHost(url);
    return url;
  };
  async function pageCommand(tabId, action, p) {
    const frameId = Number(p.frame_id || 0);
    let frame = await chrome.webNavigation.getFrame({tabId,frameId});
    if (action === 'page.wait' && frameId === 0) {
      // tabs.create/navigation resolves before the destination document exists.
      // Poll only for an explicit wait; never retry uncertain page mutations.
      const deadline=Date.now()+Math.min(120000,Math.max(250,Number(p.timeout_ms || 15000)));
      while (true) {
        const tab=await chrome.tabs.get(tabId);
        const pendingBlank=frame?.url==='about:blank' && tab.pendingUrl && tab.pendingUrl!=='about:blank';
        if(frame && tab.status!=='loading' && !pendingBlank)break;
        if(Date.now()>=deadline)throw new Error('Timeout waiting for the selected page to load.');
        await new Promise(resolve=>setTimeout(resolve,100));
        frame=await chrome.webNavigation.getFrame({tabId,frameId});
      }
    }
    if (!frame) throw new Error('Selected frame no longer exists. List frames again.');
    const denied = await LucasAccess.check(frame.url);
    if (denied) return denied;
    let response;
    try { response = await chrome.tabs.sendMessage(tabId,{type:'lucas_command',action,params:p},{frameId}); }
    catch (error) {
      // Tabs open before installing/reloading the extension have no receiver.
      // Only retry receiver absence, never an uncertain mutating action.
      if (!/Receiving end does not exist|Could not establish connection/.test(String(error))) throw error;
      await chrome.scripting.executeScript({target:{tabId,frameIds:[frameId]},files:['targets.js','page_data.js','content.js']});
      response = await chrome.tabs.sendMessage(tabId,{type:'lucas_command',action,params:p},{frameId});
    }
    if (!response?.ok) throw new Error(response?.error || 'Browser content runtime unavailable');
    return response.result;
  }
  async function execute(action,p) {
    const {paused=false} = await chrome.storage.local.get('paused');
    if (action === 'browser.status') return {paused,version:chrome.runtime.getManifest().version,capabilities:[...CAPABILITIES]};
    if (paused) return LucasAccess.handoff('browser_paused','Resume Lucas in the browser extension before continuing.');
    if (action === 'tabs.list') return (await chrome.tabs.query({})).map(t=>({id:t.id,window_id:t.windowId,active:!!t.active,title:t.title || '',url:t.url || '',status:t.status || '',group_id:t.groupId}));
    if (action === 'tab.open') {
      const url = safeUrl(p.url);
      if (url !== 'about:blank') { const denied=await LucasAccess.check(url); if(denied)return denied; }
      const tab = await chrome.tabs.create({url,active:false});
      return {id:tab.id,window_id:tab.windowId,url:tab.url || url};
    }
    if (action === 'history.search') {
      const denied=await LucasAccess.historyConsent();if(denied)return denied;
      return chrome.history.search({text:String(p.text || ''),startTime:Number(p.start_time || Date.now()-7*86400000),maxResults:Math.min(100,Math.max(1,Number(p.limit || 30)))});
    }
    if (action === 'bookmarks.search') {
      if (!(await chrome.permissions.contains({permissions:['bookmarks']}))) return LucasAccess.handoff('bookmark_permission','Enable bookmarks access in Lucas extension settings, then retry.');
      return (await chrome.bookmarks.search(String(p.query || ''))).slice(0,100).map(({id,title,url,parentId})=>({id,title,url,parent_id:parentId}));
    }
    if (p.tab_id == null) throw new Error('tab_id is required. Call pages/tabs.list and choose a tab.');
    const tabId=Number(p.tab_id); const tab=await chrome.tabs.get(tabId);
    const sourceUrl=tab.url || tab.pendingUrl;
    if (sourceUrl !== 'about:blank') {const denied=await LucasAccess.check(sourceUrl);if(denied)return denied;}
    if (action === 'tab.navigate') {
      const url=safeUrl(p.url);if(url !== 'about:blank'){const denied=await LucasAccess.check(url);if(denied)return denied;}
      await chrome.tabs.update(tabId,{url});return{tab_id:tabId,url};
    }
    if (action === 'tab.close') {await LucasDebugger.detach(tabId);await chrome.tabs.remove(tabId);return{closed:true,tab_id:tabId};}
    if (action === 'tab.reload') {await chrome.tabs.reload(tabId);return{tab_id:tabId,reloaded:true};}
    if (action === 'tab.back') {await chrome.tabs.goBack(tabId);return{tab_id:tabId};}
    if (action === 'tab.forward') {await chrome.tabs.goForward(tabId);return{tab_id:tabId};}
    if (action === 'tab.group') {
      const groupId=await chrome.tabs.group({tabIds:[tabId],...(p.group_id == null ? {} : {groupId:Number(p.group_id)})});
      if(p.title)await chrome.tabGroups.update(groupId,{title:String(p.title)});
      return {tab_id:tabId,group_id:groupId};
    }
    if (action === 'tab.ungroup') {await chrome.tabs.ungroup(tabId);return{tab_id:tabId};}
    if (action === 'page.frames') {
      const frames=await chrome.webNavigation.getAllFrames({tabId});
      return frames.map(({frameId,parentFrameId,url})=>({frame_id:frameId,parent_frame_id:parentFrameId,url}));
    }
    if (action === 'page.evaluate_readonly') return LucasDebugger.readonly(tabId,p);
    if (action === 'page.screenshot') return LucasDebugger.screenshot(tabId,p);
    if (action.startsWith('developer.')) return LucasDebugger.developer(tabId,action,p);
    if (['page.click','page.double_click','page.hover','page.drag','page.press'].includes(action)) {
      // Frame coordinates require a transform; use DOM interaction in subframes.
      if (Number(p.frame_id || 0) !== 0 && ['page.click','page.hover','page.press'].includes(action)) return pageCommand(tabId,action,p);
      if (Number(p.frame_id || 0) !== 0) throw new Error('Protocol drag/double-click currently requires the main frame.');
      const denied=await LucasAccess.check(sourceUrl);if(denied)return denied;
      return LucasDebugger.input(tabId,action,p,pageCommand);
    }
    if (action.startsWith('page.')) return pageCommand(tabId,action,p);
    if (action === 'download.url') {
      const url=safeUrl(p.url);const denied=await LucasAccess.check(url);if(denied)return denied;
      const id=await chrome.downloads.download({url,filename:p.filename || undefined,saveAs:false});
      // Independent keys avoid lost updates when different tabs download at once.
      await chrome.storage.session.set({['downloadOwner:'+id]:tabId});return{download_id:id};
    }
    if (action === 'download.status') {
      if(p.download_id == null)throw new Error('download_id is required');
      const ownerKey='downloadOwner:'+Number(p.download_id);
      const owners=await chrome.storage.session.get(ownerKey);
      if(owners[ownerKey]!==tabId)throw new Error('Download does not belong to this tab/task.');
      return (await chrome.downloads.search({id:Number(p.download_id)})).map(({id,state,error,bytesReceived,totalBytes,filename})=>({id,state,error,bytes_received:bytesReceived,total_bytes:totalBytes,filename}));
    }
    throw new Error('Unsupported Bridge action: '+action);
  }
  const CAPABILITIES = ['tabs.list','tab.open','tab.close','tab.navigate','tab.reload','tab.back','tab.forward','tab.group','tab.ungroup',
    'page.snapshot','page.click','page.double_click','page.type','page.select','page.upload','page.scroll','page.hover','page.press','page.drag','page.wait',
    'page.frames','page.screenshot','page.evaluate_readonly','page.extract','page.assets','page.selection','page.network','download.url','download.status',
    'history.search','bookmarks.search','developer.events','developer.evaluate','developer.cdp','browser.status'];
  async function run(action,p={}) {
    if (!CAPABILITIES.includes(action)) throw new Error('Unsupported Bridge action: '+action);
    const key=p.tab_id == null ? action : 'tab:'+p.tab_id;
    const prior=queues.get(key) || Promise.resolve();
    const next=prior.catch(()=>{}).then(()=>execute(action,p));queues.set(key,next);
    try{return await next;}finally{if(queues.get(key)===next)queues.delete(key);}
  }
  globalThis.LucasCommands={run,pageCommand};
})();
