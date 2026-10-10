// Protocol input/capture never activates a window or sends OS mouse/keyboard events.
(() => {
  const attached = new Set();
  const events = new Map();
  async function attach(tabId) {
    if (attached.has(tabId)) return;
    await chrome.debugger.attach({tabId}, '1.3');
    attached.add(tabId);
  }
  async function send(tabId, method, params = {}) {
    await attach(tabId);
    return chrome.debugger.sendCommand({tabId}, method, params);
  }
  async function detach(tabId) {
    if (attached.has(tabId)) await chrome.debugger.detach({tabId});
    attached.delete(tabId); events.delete(tabId);
  }
  async function detachAll() { await Promise.allSettled([...attached].map(detach)); }
  chrome.debugger.onDetach.addListener(source => {attached.delete(source.tabId); events.delete(source.tabId);});
  chrome.debugger.onEvent.addListener((source, method, params) => {
    if (!events.has(source.tabId)) return;
    const list = events.get(source.tabId);
    // No request headers, cookies, response bodies or console argument values.
    if (method === 'Network.responseReceived') list.push({type:'response',url:params.response?.url,status:params.response?.status,mime_type:params.response?.mimeType});
    if (method === 'Log.entryAdded') list.push({type:'console',level:params.entry?.level,text:String(params.entry?.text || '').slice(0,2000)});
    if (list.length > 200) list.splice(0,list.length - 200);
  });
  async function screenshot(tabId, p) {
    const params = {format:p.format === 'jpeg' ? 'jpeg' : 'png',captureBeyondViewport:!!p.full_page};
    if (params.format === 'jpeg') params.quality = Math.min(100,Math.max(1,Number(p.quality || 85)));
    if (p.full_page) {
      const metrics = await send(tabId,'Page.getLayoutMetrics');
      const size = metrics.cssContentSize || metrics.contentSize;
      if (size.width * size.height > 32_000_000) throw new Error('Page too large for one screenshot. Capture a viewport instead.');
      params.clip = {x:0,y:0,width:size.width,height:size.height,scale:1};
    }
    const result = await send(tabId,'Page.captureScreenshot',params);
    return {tab_id:tabId,mime_type:params.format === 'jpeg' ? 'image/jpeg' : 'image/png',base64:result.data};
  }
  async function input(tabId, action, p, pageCommand) {
    if (action === 'page.press') {
      if (p.target) {const focused=await pageCommand(tabId,'page.focus',p);if(focused.requires_user_action)return focused;}
      const keys = {Enter:[13,'\r'],Tab:[9,'\t'],Escape:[27,''],Backspace:[8,''],Delete:[46,''],ArrowLeft:[37,''],ArrowUp:[38,''],ArrowRight:[39,''],ArrowDown:[40,''],Space:[32,' ']};
      const parts = String(p.key || '').split('+'); const key = parts.pop();
      const modifiers = parts.reduce((m,k)=>m | ({Alt:1,Control:2,Ctrl:2,Meta:4,Shift:8}[k] || 0),0);
      const spec = keys[key] || (key.length === 1 ? [key.toUpperCase().charCodeAt(0),key] : null);
      if (!spec) throw new Error('Unsupported key: ' + key);
      await send(tabId,'Input.dispatchKeyEvent',{type:'keyDown',key,windowsVirtualKeyCode:spec[0],modifiers,...(!modifiers && spec[1] ? {text:spec[1]} : {})});
      await send(tabId,'Input.dispatchKeyEvent',{type:'keyUp',key,windowsVirtualKeyCode:spec[0],modifiers});
      return {tab_id:tabId,key:p.key};
    }
    const target = await pageCommand(tabId,'page.target',p);
    if(target.requires_user_action)return target;
    const point = {x:target.x,y:target.y};
    if (action === 'page.hover') await send(tabId,'Input.dispatchMouseEvent',{type:'mouseMoved',...point});
    else if (action === 'page.drag') {
      const end = await pageCommand(tabId,'page.target',{...p,target:p.destination});
      if(end.requires_user_action)return end;
      await send(tabId,'Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
      try {
        for (let step=1;step<=10;step++) await send(tabId,'Input.dispatchMouseEvent',{type:'mouseMoved',buttons:1,x:point.x+(end.x-point.x)*step/10,y:point.y+(end.y-point.y)*step/10});
      } finally { await send(tabId,'Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,x:end.x,y:end.y}); }
    } else {
      const button = p.button === 'right' ? 'right' : 'left';
      const count = action === 'page.double_click' ? 2 : 1;
      for (let clickCount=1;clickCount<=count;clickCount++) {
        await send(tabId,'Input.dispatchMouseEvent',{type:'mousePressed',button,clickCount,...point});
        await send(tabId,'Input.dispatchMouseEvent',{type:'mouseReleased',button,clickCount,...point});
      }
    }
    return {tab_id:tabId,target:p.target || p.selector};
  }
  async function readonly(tabId,p) {
    const result=await send(tabId,'Runtime.evaluate',{expression:String(p.expression || ''),returnByValue:true,
      throwOnSideEffect:true,timeout:Math.min(5000,Math.max(100,Number(p.timeout_ms || 3000)))});
    if(result.exceptionDetails)throw new Error('Read-only evaluation failed or could have side effects.');
    return {tab_id:tabId,value:result.result?.value};
  }
  async function developer(tabId, action, p) {
    const {developerMode=false} = await chrome.storage.local.get('developerMode');
    if (!developerMode) return LucasAccess.handoff('developer_permission','Enable developer mode in Lucas extension settings, then retry.');
    if (action === 'developer.events') {
      if (!events.has(tabId)) {
        events.set(tabId,[]);
        await send(tabId,'Network.enable'); await send(tabId,'Log.enable');
      }
      return {tab_id:tabId,events:events.get(tabId).slice(-Math.min(200,Math.max(1,Number(p.limit || 100))))};
    }
    if (action === 'developer.evaluate') {
      const result = await send(tabId,'Runtime.evaluate',{expression:String(p.expression || ''),returnByValue:true,awaitPromise:true,timeout:Math.min(30000,Math.max(100,Number(p.timeout_ms || 5000)))});
      if (result.exceptionDetails) throw new Error('Page JavaScript evaluation failed');
      return {tab_id:tabId,value:result.result?.value};
    }
    if (action === 'developer.cdp') {
      const method = String(p.method || '');
      if (!/^(Accessibility|Audits|CSS|DOM|DOMSnapshot|Emulation|Input|Log|Network|Page|Performance|Runtime|Tracing)\.[A-Za-z]+$/.test(method))
        throw new Error('CDP command must address the selected page; target/browser management domains are unavailable.');
      return {tab_id:tabId,result:await send(tabId,method,p.command_params || {})};
    }
    throw new Error('Unsupported developer action');
  }
  globalThis.LucasDebugger = {screenshot,input,readonly,developer,detach,detachAll};
})();
