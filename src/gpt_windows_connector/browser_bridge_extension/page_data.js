(() => {
  const limit = (value, fallback=100, max=1000) => Math.min(max,Math.max(1,Number(value || fallback)));
  const text = el => String(el.innerText || el.textContent || '').replace(/\s+/g,' ').trim().slice(0,5000);
  globalThis.LucasPageData = {
    run(action,p) {
      if(action==='page.selection')return{url:location.href,title:document.title,selection:String(window.getSelection() || '').slice(0,20000)};
      if(action==='page.assets')return{url:location.href,images:[...document.images].slice(0,limit(p.limit)).map(el=>({url:el.currentSrc || el.src,alt:el.alt,width:el.naturalWidth,height:el.naturalHeight})),
        media:[...document.querySelectorAll('video,audio,source')].slice(0,limit(p.limit)).map(el=>({tag:el.tagName.toLowerCase(),url:el.currentSrc || el.src}))};
      if(action==='page.extract') {
        const rows=[...document.querySelectorAll(p.selector || 'table tr')].slice(0,limit(p.limit));
        const fields=p.fields && typeof p.fields === 'object' ? Object.entries(p.fields).slice(0,30) : null;
        return{url:location.href,rows:rows.map(row=>fields?Object.fromEntries(fields.map(([key,selector])=>[key,[...row.querySelectorAll(String(selector))].map(text).join(' ')])):
          (row.matches('tr')?[...row.querySelectorAll('th,td')].map(text):{text:text(row)}))};
      }
      throw new Error('Unsupported page data command');
    }
  };
})();
