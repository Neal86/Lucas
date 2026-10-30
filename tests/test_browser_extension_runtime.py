from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_connection_status_updates_do_not_disconnect_extension_and_popup_expires():
    result = subprocess.run(['node', '-e', r'''
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const storage={}, listeners=[], sockets=[];
let closed=0;
const chrome={
  runtime:{id:'a'.repeat(32),onInstalled:{addListener(){}},onStartup:{addListener(){}},onMessage:{addListener(){}},openOptionsPage(){}},
  storage:{local:{async get(keys){const names=Array.isArray(keys)?keys:[keys];return Object.fromEntries(names.filter(k=>k in storage).map(k=>[k,storage[k]]));},async set(values){const changes={};for(const [k,v] of Object.entries(values)){if(storage[k]!==v)changes[k]={oldValue:storage[k],newValue:v};storage[k]=v;}for(const listener of listeners)listener(changes,'local');}},onChanged:{addListener(fn){listeners.push(fn);}}},
  action:{async setBadgeText(){},async setBadgeBackgroundColor(){}},
  tabs:{onRemoved:{addListener(){}},async query(){return[];}},
};
class Socket{constructor(){this.readyState=0;sockets.push(this);}send(value){this.sent=value;}close(){closed++;this.readyState=3;this.onclose?.();}}
const elements={};for(const id of ['status','profile','code','options'])elements[id]={textContent:'',className:''};
const ctx=vm.createContext({chrome,WebSocket:Socket,crypto:{randomUUID:()=> 'test-installation'},navigator:{userAgent:'Chrome'},setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,clearInterval(){},Date,console,document:{getElementById:id=>elements[id]}});
vm.runInContext(fs.readFileSync('src/gpt_windows_connector/browser_bridge_extension/background.js','utf8'),ctx);
(async()=>{
  await new Promise(setImmediate);
  const socket=sockets[0];socket.readyState=1;await socket.onopen();
  assert.equal(JSON.parse(socket.sent).browser_type,'chrome');
  await socket.onmessage({data:JSON.stringify({type:'hello_ack',paired:false,pairing_code:'123456'})});
  assert.equal(closed,0,'hello_ack must not disconnect its own socket');
  assert.equal(storage.connected,true);
  await socket.onmessage({data:JSON.stringify({type:'paired'})});
  await socket.onmessage({data:JSON.stringify({type:'heartbeat_ack'})});
  assert.equal(closed,0,'status storage changes must not cause reconnect loops');
  vm.runInContext(fs.readFileSync('src/gpt_windows_connector/browser_bridge_extension/popup.js','utf8'),ctx);
  await new Promise(setImmediate);
  assert.equal(elements.status.textContent,'Connected to Lucas');
  await chrome.storage.local.set({lastSeen:Date.now()-50000});await new Promise(setImmediate);
  assert.match(elements.status.textContent,/disconnected/,'stale pairing is not live connection');
  await chrome.storage.local.set({profileName:'New profile'});await new Promise(setImmediate);
  assert.equal(closed,1,'changing real profile settings reconnects once');
  assert.equal(storage.connected,false);
  assert.equal(elements.code.textContent,'');
  console.log('PASS real service worker/popup lifecycle');
})().catch(e=>{console.error(e);process.exit(1);});
'''], cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
