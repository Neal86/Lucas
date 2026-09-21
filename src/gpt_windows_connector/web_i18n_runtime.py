from __future__ import annotations

from .web_i18n_catalog import WEB_ZH_JS

I18N_SCRIPT = (
    r'''<script>
const WEB_LANG=(()=>{const primary=String(navigator.language||navigator.userLanguage||((navigator.languages&&navigator.languages[0])||'en')).toLowerCase().replace('_','-');return primary.startsWith('zh')?'zh':'en'})();
document.documentElement.lang=WEB_LANG==='zh'?'zh-CN':'en';
const WEB_ZH='''
    + WEB_ZH_JS
    + r''';
function wt(s){return WEB_LANG==='zh'?(WEB_ZH[s]||s):s}
function localizeWeb(root=document.body){if(WEB_LANG!=='zh'||!root)return;const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);for(const n of nodes){const raw=n.nodeValue,trim=raw.trim();if(trim&&WEB_ZH[trim])n.nodeValue=raw.replace(trim,WEB_ZH[trim])}root.querySelectorAll?.('input[placeholder],textarea[placeholder]').forEach(e=>{if(WEB_ZH[e.placeholder])e.placeholder=WEB_ZH[e.placeholder]});root.querySelectorAll?.('[aria-label],[title]').forEach(e=>{for(const a of ['aria-label','title']){const v=e.getAttribute(a);if(v&&WEB_ZH[v])e.setAttribute(a,WEB_ZH[v])}})}
</script>'''
)
