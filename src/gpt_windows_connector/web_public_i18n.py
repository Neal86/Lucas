"""Apply the shared browser-language catalog to static informational pages."""
from .web_i18n_runtime import I18N_SCRIPT

PUBLIC_I18N_SCRIPT = I18N_SCRIPT + r'''<script>
localizeWeb();
if(WEB_LANG==='zh'){
  document.title=wt(document.title.replace(/ · Lucas$/, ''))+(document.title.endsWith(' · Lucas')?' · Lucas':'');
  for(const selector of ['meta[name="description"]','meta[property="og:title"]','meta[property="og:description"]']){
    const element=document.querySelector(selector);if(element)element.content=wt(element.content);
  }
}
</script>'''
