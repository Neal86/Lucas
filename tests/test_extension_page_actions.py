"""Run the real background/CDP expression in an isolated page DOM boundary VM.

No browser or network is started. The DOM fixture supplies native properties;
real Chromium navigation/label behavior is covered by test_extension_chromium.
EXTENSION_ROOT can point to a frozen checkout for fail-before comparisons.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1] / 'extensions' / 'lucas-browser'
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='Node.js is required for serialized extension tests')

RUNTIME = r"""
const fs=require('fs'), path=require('path'), vm=require('vm'), crypto=require('crypto');
const root=process.argv[1], spec=JSON.parse(process.argv[2]);
const clicked=[], events=[], commands=[], sent=[], sockets=[], nodes=[];
class Element {
  constructor(data) {
    this.tagName=(data.tag||'button').toUpperCase(); this.attrs=data.attrs||{};
    this.id=this.attrs.id||''; this.innerText=data.text||''; this.textContent=this.innerText;
    this.disabled=!!data.disabled; this.visible=data.visible!==false;
    this._value=data.value||''; this.options=(data.options||[]).map(value=>({value}));
    this.isContentEditable=this.attrs.contenteditable==='true'; this.children=[];
    nodes.push(this);
    for(const child of data.children||[]) {const e=make(child); e.parentElement=this; this.children.push(e)}
  }
  getAttribute(name) {return Object.hasOwn(this.attrs,name)?this.attrs[name]:null}
  hasAttribute(name) {return Object.hasOwn(this.attrs,name)}
  get target() {return this.getAttribute('target')||''}
  get type() {
    const raw=(this.getAttribute('type')||'').toLowerCase();
    if(this.tagName==='BUTTON') return ['button','reset','submit'].includes(raw)?raw:'submit';
    if(this.tagName==='INPUT') return raw||'text';
    return raw;
  }
  get value() {return this._value}
  set value(value) {this._value=value}
  get form() {
    if(!['INPUT','BUTTON','TEXTAREA','SELECT'].includes(this.tagName)) return undefined;
    if(this.hasAttribute('form')) return nodes.find(e=>e.tagName==='FORM'&&e.id===this.attrs.form)||null;
    return this.parentElement?.closest('form')||null;
  }
  get control() {
    if(this.tagName!=='LABEL') return undefined;
    if(this.hasAttribute('for')) return nodes.find(e=>e.id===this.attrs.for)||null;
    return nodes.find(e=>['BUTTON','INPUT','TEXTAREA','SELECT'].includes(e.tagName)&&e.closest('label')===this)||null;
  }
  matches(selector) {
    return selector.split(',').some(part=>{
      part=part.trim();
      if(part.startsWith('#')) return this.id===part.slice(1);
      const match=/^([\w-]+)?(?:\[([\w-]+)(?:="([^"]*)")?\])?$/.exec(part);
      if(!match) throw Error('Fixture does not support selector '+part);
      return (!match[1]||this.tagName===match[1].toUpperCase())&&(!match[2]||(this.hasAttribute(match[2])&&(match[3]===undefined||this.getAttribute(match[2])===match[3])));
    });
  }
  closest(selector) {for(let e=this;e;e=e.parentElement) if(e.matches(selector)) return e; return null}
  getClientRects() {return this.visible?[{}]:[]}
  click() {clicked.push(this.id); events.push({id:this.id,type:'click'})}
  dispatchEvent(event) {events.push({id:this.id,type:event.type}); return true}
}
class Input extends Element {get value(){return this._value} set value(v){this._value=v}}
class Textarea extends Element {get value(){return this._value} set value(v){this._value=v}}
const make=data=>new (data.tag==='input'?Input:data.tag==='textarea'?Textarea:Element)(data);
for(const data of spec.nodes||[]) make(data);
const document={title:'Fixture',body:{innerText:spec.body||'Safe fixture'},
  querySelector(selector) {
    if(selector.includes('iframe[src*=')) return spec.human?{}:null;
    if(selector==='body') return this.body;
    return nodes.find(e=>e.matches(selector))||null;
  },
  querySelectorAll(selector) {return nodes.filter(e=>e.matches(selector))},
};
const page=vm.createContext({document,location:{href:'https://fixture.invalid/'},
  HTMLInputElement:Input,HTMLTextAreaElement:Textarea,
  Event:class {constructor(type,options){this.type=type;Object.assign(this,options)}},
  window:{scrollBy(x,y){page.scrollX+=x;page.scrollY+=y}},scrollX:0,scrollY:0,
});
const event=()=>({listeners:[],addListener(fn){this.listeners.push(fn)},removeListener(fn){this.listeners=this.listeners.filter(x=>x!==fn)}});
const chrome={
  runtime:{id:'page-action-fixture',onMessage:event()},
  storage:{local:{async get(){return {token:'synthetic-page-action-token-not-a-secret',port:8766}}}},
  alarms:{create(){},onAlarm:event()},
  tabs:{async get(id){return {id,url:'https://fixture.invalid/',title:'Fixture'}},onRemoved:event()},
  debugger:{async attach(){},async detach(){},onDetach:event(),onEvent:event(),
    async sendCommand(target,method,params) {
      commands.push({target,method});
      if(method!=='Runtime.evaluate') throw Error('Unexpected CDP method '+method);
      if(params.contextId!==undefined||target.tabId!==7) throw Error('Unexpected evaluation target');
      try {return {result:{value:vm.runInContext(params.expression,page,{timeout:1000})}}}
      catch(error) {return {exceptionDetails:{exception:{description:error.message}}}}
    },
  },
};
class WebSocket {
  static OPEN=1; static CLOSED=3;
  constructor(){this.readyState=1;sockets.push(this)}
  send(raw){sent.push(JSON.parse(raw))}
  close(){this.readyState=3;this.onclose?.()}
}
const timers=new Map(); let nextTimer=0;
const background=vm.createContext({chrome,WebSocket,crypto:crypto.webcrypto,URL,
  setInterval(){},setTimeout(fn){timers.set(++nextTimer,fn);return nextTimer},clearTimeout(id){timers.delete(id)},
});
const modules=new Map();
async function load(file) {
  if(modules.has(file)) return modules.get(file);
  const mod=new vm.SourceTextModule(fs.readFileSync(file,'utf8'),{context:background,identifier:file});
  modules.set(file,mod);
  await mod.link((specifier,ref)=>load(path.resolve(path.dirname(ref.identifier),specifier)));
  return mod;
}
const tick=()=>new Promise(setImmediate);
const popup=msg=>new Promise(resolve=>chrome.runtime.onMessage.listeners[0](msg,{id:chrome.runtime.id},resolve));
(async()=>{
  await (await load(path.join(root,'background.js'))).evaluate(); await tick();
  const socket=sockets[0]; socket.onopen();
  const message=msg=>socket.onmessage({data:JSON.stringify(msg)});
  await message({type:'ready',owners:[{user_id:'owner'}],capabilities:['grant_request_id']});
  const grantResult=await popup({type:'grant',owner_id:'owner',tab_id:7});
  if(!grantResult.ok) throw Error('Fixture grant failed '+JSON.stringify(grantResult));
  const grant=sent.find(m=>m.type==='grant');
  await message({type:'granted',session_id:'ext-fixture-session',owner_id:'owner',tab_id:7,request_id:grant.request_id});
  await message({type:'request',id:'page-rpc',session_id:'ext-fixture-session',tab_id:7,
    action:spec.action||'click',params:spec.params||{selector:'#chosen'}});
  const response=sent.find(m=>m.type==='response'&&m.id==='page-rpc');
  if(!response) throw Error('No page action response');
  const status=await popup({type:'status'});
  console.log(JSON.stringify({response,clicked,events,commands,grants:sent.filter(m=>m.type==='grant').length,
    sessions:status.sessions.length,values:Object.fromEntries(nodes.filter(e=>e.id).map(e=>[e.id,e.value])),
    content:Object.fromEntries(nodes.filter(e=>e.id).map(e=>[e.id,e.textContent]))}));
})().catch(error=>{console.error(error.stack);process.exitCode=1});
"""


def node(tag, *, attrs=None, children=None, **properties):
    return {'tag': tag, 'attrs': attrs or {}, 'children': children or [], **properties}


def link(target=None, *, href='/next', children=None, **properties):
    attrs = {'id': 'chosen'}
    if target is not None:
        attrs['target'] = target
    if href is not None:
        attrs['href'] = href
    return node('a', attrs=attrs, children=children, **properties)


def submitter(*, target=None, formtarget=None, tag='button', kind=None, nested=False, external=False):
    attrs = {'id': 'control' if nested else 'chosen'}
    if kind is not None:
        attrs['type'] = kind
    if formtarget is not None:
        attrs['formtarget'] = formtarget
    if external:
        attrs['form'] = 'form'
    children = [node('span', attrs={'id': 'chosen'}, text='Nested control')] if nested else []
    control = node(tag, attrs=attrs, children=children, text='Submit fixture')
    form_attrs = {'id': 'form'}
    if target is not None:
        form_attrs['target'] = target
    form = node('form', attrs=form_attrs, children=[] if external else [control])
    return [form, control] if external else [form]


def run_action(spec):
    root = os.environ.get('EXTENSION_ROOT', str(ROOT))
    result = subprocess.run(
        [NODE, '--experimental-vm-modules', '-e', RUNTIME, root, json.dumps(spec)],
        text=True, capture_output=True, timeout=15,
        env={**os.environ, 'NODE_NO_WARNINGS': '1'},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(result.stdout)
    assert output['commands'] == [{'target': {'tabId': 7}, 'method': 'Runtime.evaluate'}], output['response']
    assert output['grants'] == 1 and output['sessions'] == 1
    return output


def assert_click(nodes, handoff, *, action='click', params=None):
    spec = {'nodes': nodes, 'action': action}
    if params is not None:
        spec['params'] = params
    output = run_action(spec)
    assert output['response']['ok'], output['response']
    result = output['response']['result']
    if handoff:
        assert result == {
            'handoff_required': True,
            'reason': 'This control opens another tab; open and authorize it manually',
        }
        assert output['clicked'] == [] and output['events'] == []
    else:
        assert result == {'url': 'https://fixture.invalid/', 'title': 'Fixture'}
        assert output['clicked'] == ['chosen']
    return output


@pytest.mark.parametrize('target', ['_blank', '_BLANK', '_bLaNk', 'named-window', ' ', ' _self ', '\t', 'tab\n<name'])
def test_anchor_cross_context_targets_handoff_before_click(target):
    assert_click([link(target)], True)


@pytest.mark.parametrize('target', [None, '', '_self', '_SELF', '_sElF', '_parent', '_PARENT', '_top', '_TOP'])
def test_same_tab_anchor_targets_still_click(target):
    assert_click([link(target)], False)


@pytest.mark.parametrize('action', ['click', 'semantic_click'])
def test_nested_named_anchor_and_semantic_click_handoff(action):
    anchor = node('a', attrs={'href': '/next', 'target': 'existing-window'}, children=[
        node('span', attrs={'id': 'chosen', 'role': 'link', 'aria-label': 'Open report'}, text='icon'),
    ])
    params = {'selector': '#chosen'} if action == 'click' else {'target': 'Open report'}
    assert_click([anchor], True, action=action, params=params)


@pytest.mark.parametrize('tag,kind,nested,external', [
    ('button', None, False, False), ('button', 'SUBMIT', False, False),
    ('button', 'invalid', True, False), ('button', 'submit', True, True),
    ('input', 'submit', False, False), ('input', 'image', False, True),
])
@pytest.mark.parametrize('target', ['_blank', '_BLANK', 'report-window'])
def test_form_submitters_handoff_before_click(tag, kind, nested, external, target):
    assert_click(submitter(target=target, tag=tag, kind=kind, nested=nested, external=external), True)


@pytest.mark.parametrize('tag,kind', [('button', None), ('input', 'submit'), ('input', 'image')])
@pytest.mark.parametrize('target', ['_BLANK', 'report-window', ' _self '])
def test_submitter_formtarget_overrides_same_tab_form(tag, kind, target):
    assert_click(submitter(target='_self', formtarget=target, tag=tag, kind=kind), True)


@pytest.mark.parametrize('formtarget', ['', '_self', '_SeLf', '_parent', '_TOP'])
def test_present_same_tab_formtarget_overrides_cross_context_form(formtarget):
    assert_click(submitter(target='_blank', formtarget=formtarget), False)


@pytest.mark.parametrize('target', [None, '', '_self', '_PARENT', '_top'])
def test_same_tab_form_submitter_still_clicks(target):
    assert_click(submitter(target=target), False)


@pytest.mark.parametrize('element', ['anchor', 'button', 'input'])
@pytest.mark.parametrize('target', ['_blank', '_BLANK', 'base-window'])
def test_inherited_first_base_target_handoffs(element, target):
    bases = [node('base', attrs={'href': '/'}), node('base', attrs={'target': target}), node('base', attrs={'target': '_self'})]
    controls = [link()] if element == 'anchor' else submitter(tag=element, kind='submit')
    assert_click(bases + controls, True)


@pytest.mark.parametrize('element', ['anchor', 'button', 'input'])
@pytest.mark.parametrize('target', ['', '_self', '_TOP'])
def test_first_same_tab_base_target_beats_later_blank(element, target):
    bases = [node('base', attrs={'target': target}), node('base', attrs={'target': '_blank'})]
    controls = [link()] if element == 'anchor' else submitter(tag=element, kind='submit')
    assert_click(bases + controls, False)


@pytest.mark.parametrize('element', ['anchor', 'form', 'submitter'])
@pytest.mark.parametrize('target', ['', '_SeLf'])
def test_explicit_target_respects_chromium_empty_base_fallback(element, target):
    base = node('base', attrs={'target': '_blank'})
    controls = [link(target)] if element == 'anchor' else submitter(**{('target' if element == 'form' else 'formtarget'): target})
    assert_click([base] + controls, target == '')


@pytest.mark.parametrize('tag,kind', [
    ('button', 'button'), ('button', 'reset'), ('input', 'button'), ('input', 'reset'),
    ('input', 'text'), ('input', 'checkbox'), ('textarea', None), ('select', None),
])
def test_non_submit_form_controls_ignore_form_target(tag, kind):
    assert_click(submitter(target='_blank', formtarget='_blank', tag=tag, kind=kind), False)


def test_anchor_without_href_has_no_native_target_handoff():
    assert_click([node('base', attrs={'target': '_blank'}), link('_blank', href=None)], False)


def test_unassociated_submit_button_does_not_navigate():
    assert_click([node('button', attrs={'id': 'chosen', 'formtarget': '_blank'})], False)


@pytest.mark.parametrize('nested,implicit', [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize('tag,kind', [('button', 'submit'), ('input', 'submit'), ('input', 'image')])
def test_label_forwarded_submission_handoff(nested, implicit, tag, kind):
    control = node(tag, attrs={'id': 'submit-control', 'type': kind, 'form': 'form', 'formtarget': 'named-window'})
    label = node('label', attrs={'id': 'label' if nested else 'chosen', **({} if implicit else {'for': 'submit-control'})}, children=(
        ([control] if implicit else []) + ([node('span', attrs={'id': 'chosen'}, text='Submit')] if nested else [])
    ))
    assert_click([node('form', attrs={'id': 'form', 'target': '_self'}), label] + ([] if implicit else [control]), True)


@pytest.mark.parametrize('tag,kind', [('input', 'text'), ('input', 'checkbox'), ('button', 'button')])
def test_ordinary_labels_still_click(tag, kind):
    control = node(tag, attrs={'id': 'input', 'type': kind, 'form': 'form', 'formtarget': '_blank'})
    label = node('label', attrs={'id': 'chosen', 'for': 'input'})
    assert_click([node('form', attrs={'id': 'form', 'target': '_blank'}), control, label], False)


@pytest.mark.parametrize('interactive', [
    node('a', attrs={'href': '/same', 'target': '_self'}), node('button', attrs={'type': 'button'}),
    node('input', attrs={'type': 'text'}), node('select'), node('textarea'), node('details'),
    node('embed'), node('iframe'), node('audio', attrs={'controls': ''}),
    node('video', attrs={'controls': ''}), node('img', attrs={'usemap': '#map'}),
])
def test_interactive_label_descendants_do_not_forward_submission(interactive):
    interactive = {**interactive, 'children': [node('span', attrs={'id': 'chosen'})]}
    label = node('label', attrs={'for': 'submit-control'}, children=[interactive])
    control = node('button', attrs={'id': 'submit-control', 'form': 'form', 'formtarget': '_blank'})
    assert_click([node('form', attrs={'id': 'form'}), control, label], False)


@pytest.mark.parametrize('action,tag,clear', [('type', 'input', True), ('semantic_type', 'textarea', False), ('type', 'div', True)])
def test_typing_and_input_change_events_survive_extraction(action, tag, clear):
    control = node(tag, attrs={'id': 'chosen', 'aria-label': 'Notes', **({'contenteditable': 'true'} if tag == 'div' else {})}, value='old', text='old')
    params = {'selector': '#chosen', 'target': 'Notes', 'text': 'new', 'clear': clear}
    output = run_action({'nodes': [control], 'action': action, 'params': params})
    assert output['response'] == {'type': 'response', 'id': 'page-rpc', 'ok': True, 'result': {'url': 'https://fixture.invalid/', 'title': 'Fixture', 'characters': 3}}
    assert output['clicked'] == []
    assert output['events'] == [{'id': 'chosen', 'type': 'input'}, {'id': 'chosen', 'type': 'change'}]
    assert output['content' if tag == 'div' else 'values']['chosen'] == ('new' if clear else 'oldnew')


@pytest.mark.parametrize('action,params,expected', [
    ('inspect', {'max_chars': 4}, {'text': 'Safe'}),
    ('scroll', {'x': 4, 'y': 10}, {'x': 4, 'y': 10}),
    ('select', {'selector': '#chosen', 'value': 'b'}, {'selected': ['b']}),
])
def test_other_page_actions_survive_extraction(action, params, expected):
    output = run_action({'nodes': [node('select', attrs={'id': 'chosen'}, options=['a', 'b'])], 'action': action, 'params': params})
    assert output['response']['ok'], output['response']
    assert output['response']['result'] == {'url': 'https://fixture.invalid/', 'title': 'Fixture', **expected}


def test_observe_password_redaction_survives_extraction():
    output = run_action({'nodes': [node('input', attrs={'id': 'chosen', 'type': 'password'}, value='fixture-private')], 'action': 'observe', 'params': {}})
    assert output['response']['ok'], output['response']
    assert output['response']['result']['elements'][0]['text'] == ''
    assert output['clicked'] == [] and output['events'] == []


def test_human_verification_handoff_precedes_native_click():
    output = run_action({'nodes': [link()], 'human': True})
    assert output['response']['result'] == {'handoff_required': True, 'reason': 'Complete verification manually in the authorized tab'}
    assert output['clicked'] == [] and output['events'] == []


@pytest.mark.parametrize('properties', [{'disabled': True}, {'visible': False}])
def test_disabled_and_hidden_controls_still_reject(properties):
    output = run_action({'nodes': [node('button', attrs={'id': 'chosen'}, **properties)]})
    assert not output['response']['ok']
    assert output['response']['error'] == 'Control missing, hidden or disabled'
    assert output['clicked'] == [] and output['events'] == []


@pytest.mark.parametrize('tag', ['details', 'textarea', 'select', 'button', 'input'])
def test_interactive_descendant_does_not_hide_enclosing_external_anchor(tag):
    child = node(tag, attrs={'id': 'inner', 'type': 'button'}, children=[node('span', attrs={'id': 'chosen'})])
    assert_click([node('a', attrs={'href': '/next', 'target': '_blank'}, children=[child])], True)


@pytest.mark.parametrize('base_target', [None, '', '_self', '_BLANK', 'base-window'])
@pytest.mark.parametrize('form_target', [None, '', '_self', '_blank', 'form-window'])
def test_empty_formtarget_replaces_form_target_then_uses_chromium_base_fallback(base_target, form_target):
    bases = [] if base_target is None else [node('base', attrs={'target': base_target})]
    # Presence-empty supersedes form.target. Chromium then falls back to base,
    # not to the form target. Explicit _self is the unambiguous same-tab choice.
    assert_click(bases + submitter(target=form_target, formtarget=''), base_target in {'_BLANK', 'base-window'})


@pytest.mark.parametrize('tag,kind', [('button', 'submit'), ('input', 'submit'), ('input', 'image')])
def test_label_forwarded_empty_formtarget_handoffs_for_external_base(tag, kind):
    control = node(tag, attrs={'id': 'submit-control', 'type': kind, 'form': 'form', 'formtarget': ''})
    label = node('label', attrs={'id': 'chosen', 'for': 'submit-control'})
    assert_click([node('base', attrs={'target': 'base-window'}), node('form', attrs={'id': 'form', 'target': '_self'}), control, label], True)
