import json
from pathlib import Path
import shutil
import subprocess

import pytest

EXT = Path(__file__).resolve().parents[1] / 'src/gpt_windows_connector/browser_bridge_extension'


def test_bridge_content_refs_ambiguity_staleness_and_password_redaction():
    if not shutil.which('node'):
        pytest.skip('Node.js unavailable')
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const ext = process.argv[1];
let handler, nodes = [];
function element(text, attrs={}) {
  return {tagName: attrs.type ? 'INPUT' : 'BUTTON', innerText: text, value: attrs.value || '',
    id: '', isConnected: true, disabled: false, getAttribute: k => attrs[k] || null,
    getBoundingClientRect: () => ({width:10,height:10}), clicked: false,
    scrollIntoView(){}, click(){this.clicked = true;}};
}
const ctx = vm.createContext({crypto:require('crypto').webcrypto,
  location:{href:'https://example.com'},
  document:{title:'Test',body:{innerText:'Save'},querySelector:()=>null,
    querySelectorAll:q => { if(q === 'Save') throw new Error('invalid selector'); return nodes; }},
  getComputedStyle:()=>({display:'block',visibility:'visible'}),
  chrome:{runtime:{onMessage:{addListener:fn=>handler=fn}}}});
for (const file of ['targets.js','content.js']) vm.runInContext(fs.readFileSync(ext+'/'+file,'utf8'),ctx);
function call(action,params={}) {return new Promise(resolve=>handler({type:'lucas_command',action,params},null,resolve));}
(async()=>{
  const first=element('Save'), second=element('Save'), password=element('',{type:'password',value:'TOP_SECRET'});
  nodes=[first,second,password];
  let snap=await call('page.snapshot');
  assert(snap.ok); assert(!JSON.stringify(snap).includes('TOP_SECRET'));
  let result=await call('page.click',{target:'Save'});
  assert(!result.ok && result.error.includes('Ambiguous'));
  assert(!first.clicked && !second.clicked);
  const ref=snap.result.elements[1].ref;
  nodes.unshift(element('New'));
  result=await call('page.click',{target:ref});
  assert(result.ok && second.clicked && !first.clicked);
  second.innerText='Delete';
  result=await call('page.click',{target:ref});
  assert(!result.ok && result.error.includes('changed'));
  await call('page.snapshot');
  result=await call('page.click',{target:ref});
  assert(!result.ok && result.error.includes('expired'));
  console.log('bridge runtime assertions passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', script, str(EXT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((EXT / 'manifest.json').read_text())
    assert manifest['content_scripts'][0]['js'] == ['targets.js', 'content.js']
