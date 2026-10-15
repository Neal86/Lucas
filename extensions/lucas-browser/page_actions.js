// This fixed function is serialized into the authorized tab's main frame.
// Keep every helper inside it: module bindings do not survive Function.toString().
// Native target checks are not a sandbox for arbitrary site event handlers.
export function pageAction(action,p) {
  const info=()=>({url:location.href,title:document.title});
  const norm=x=>String(x||'').replace(/\s+/g,' ').trim().toLowerCase();
  const all='button,a,input,textarea,select,[role="button"],[role="link"],[contenteditable="true"]';
  const visible=e=>!!e.getClientRects().length;
  const human=!!document.querySelector('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="challenges.cloudflare.com"],input[autocomplete="one-time-code"]') || /verify (your identity|you are human)|security key|passkey/i.test(document.body?.innerText||'');
  if(human && !['inspect','observe'].includes(action)) return {handoff_required:true,reason:'Complete verification manually in the authorized tab'};
  if(action==='inspect') return {...info(),text:(document.querySelector(p.selector||'body')?.innerText||'').slice(0,Math.min(Math.max(Number(p.max_chars)||30000,1),100000))};
  if(action==='observe') return {...info(),handoff_required:human,elements:[...document.querySelectorAll(all)].filter(visible).slice(0,Math.min(Number(p.limit)||300,1000)).map((e,index)=>({index,tag:e.tagName.toLowerCase(),id:e.id,role:e.getAttribute('role')||'',text:(e.type==='password'?'':e.innerText||e.value||'').slice(0,300),aria_label:e.getAttribute('aria-label')||'',placeholder:e.getAttribute('placeholder')||'',disabled:!!e.disabled}))};
  if(action==='scroll'){window.scrollBy(Number(p.x)||0,Number(p.y)||0);return {...info(),x:scrollX,y:scrollY};}
  let element;
  if(action.startsWith('semantic_')){
    const target=norm(p.target); if(!target) throw Error('target is required');
    const editable=action==='semantic_type';
    const candidates=[...document.querySelectorAll(editable?'input,textarea,[contenteditable="true"]':all)].filter(visible);
    const score=e=>{
      const labels=[e.getAttribute('aria-label'),e.getAttribute('placeholder'),e.innerText,...(e.labels||[])].map(x=>norm(x?.textContent||x)).filter(Boolean);
      return labels.some(x=>x===target)?2:labels.some(x=>x.includes(target))?1:0;
    };
    const ranked=candidates.map(e=>({e,score:score(e)})).filter(x=>x.score).sort((a,b)=>b.score-a.score);
    if(!ranked.length) throw Error('No matching control');
    if(ranked.length>1&&ranked[0].score===ranked[1].score) throw Error('Ambiguous control; use a precise selector');
    element=ranked[0].e;
  }else element=document.querySelector(p.selector);
  if(!element||!visible(element)||element.disabled) throw Error('Control missing, hidden or disabled');
  if(action==='click'||action==='semantic_click'){
    // Presence-empty formtarget overrides the form target. Chromium then
    // falls back to base[target] when that effective target is empty (unlike
    // the spec's presence-only fallback). Guard this native behavior too;
    // only the first base[target] participates, even when its value is empty.
    const targetFor=(control,override=null)=>{
      const target=override??control.getAttribute('target');
      return target||document.querySelector('base[target]')?.getAttribute('target')||'';
    };
    // These keywords stay in this tab because evaluation uses the main frame.
    // Never trim: " _self " and whitespace-only strings are named targets.
    // Named targets may reuse an unapproved tab, so hand them off conservatively.
    const outsideTab=target=>!['','_self','_parent','_top'].includes(target.toLowerCase());
    // A label forwards native activation to its associated control, except
    // when the click is inside interactive content. .control also resolves
    // explicit associations and submitters outside their form.
    const anchor=element.closest('a[href],area[href]');
    // Keep enclosing link checks independent of label exclusions. Interactive
    // descendants (e.g. details) do not all have their own activation behavior.
    let leavesTab=!!anchor&&outsideTab(targetFor(anchor));
    let control=element.closest('button,input,select,textarea,details,embed,iframe,audio[controls],video[controls],img[usemap],label,a[href],area[href]');
    if(control?.tagName==='LABEL') control=control.control;
    if(control?.form && ((control.tagName==='BUTTON'&&control.type==='submit') || (control.tagName==='INPUT'&&['submit','image'].includes(control.type)))) {
      leavesTab ||= outsideTab(targetFor(control.form,control.getAttribute('formtarget')));
    }
    if(leavesTab) return {handoff_required:true,reason:'This control opens another tab; open and authorize it manually'};
    element.click();return info();
  }
  if(action==='type'||action==='semantic_type'){
    const text=String(p.text||'');
    if(element.isContentEditable) element.textContent=(p.clear===false?element.textContent:'')+text;
    else {
      if(!['INPUT','TEXTAREA'].includes(element.tagName)||element.type==='file') throw Error('Not a text input');
      const setter=Object.getOwnPropertyDescriptor(element.tagName==='INPUT'?HTMLInputElement.prototype:HTMLTextAreaElement.prototype,'value').set;
      setter.call(element,(p.clear===false?element.value:'')+text);
    }
    element.dispatchEvent(new Event('input',{bubbles:true})); element.dispatchEvent(new Event('change',{bubbles:true})); return {...info(),characters:text.length};
  }
  if(action==='select'){
    if(element.tagName!=='SELECT'||![...element.options].some(o=>o.value===p.value)) throw Error('Unknown option');
    element.value=p.value; element.dispatchEvent(new Event('change',{bubbles:true})); return {...info(),selected:[p.value]};
  }
  throw Error('Unsupported page action');
}
