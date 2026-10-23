"""Execute the served dashboard runtime, including boot, without browser automation."""
import re
import subprocess

from gpt_windows_connector import server


def test_served_dashboard_login_verification_lifecycle(tmp_path):
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', server.webapp.DASHBOARD_HTML, re.S)
    runtime = next(script for script in scripts if 'const state=' in script)
    assert 'let pendingLoginChallenge=' in runtime
    assert 'pendingRegistrationMetaEventId' in runtime
    script_path = tmp_path / 'dashboard.js'
    script_path.write_text(runtime, encoding='utf-8')
    result = subprocess.run(['node', '-e', HARNESS, str(script_path)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS served dashboard login lifecycle' in result.stdout


HARNESS = r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
const stored={};let now=1000000;
const storage={getItem:k=>stored[k]??null,setItem:(k,v)=>stored[k]=v,removeItem:k=>delete stored[k]};
function page(){
  const elements={},events={},requests=[],intervals=new Map();let sequence=0,verifyError='';
  function element(id){
    if(elements[id])return elements[id];
    const classes=new Set(['registerForm','loginVerifyForm','verifyForm'].includes(id)?['hidden']:[]);
    return elements[id]={value:'',checked:true,textContent:'',disabled:false,style:{},
      classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle(c,v){if(v===undefined)v=!classes.has(c);v?classes.add(c):classes.delete(c);}},
      focus(){},remove(){},setAttribute(){},getAttribute(){return null;},addEventListener(){},querySelectorAll(){return [];}};
  }
  const document={getElementById:element,querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}};
  const ctx={document,console,URLSearchParams,WEB_LANG:'en',localStorage:storage,sessionStorage:storage,
    location:{search:'',pathname:'/dashboard'},navigator:{},history:{},
    Date:class extends Date{static now(){return now;}},
    setTimeout:()=>++sequence,clearTimeout(){},setInterval(fn){let id=++sequence;intervals.set(id,fn);return id;},clearInterval:id=>intervals.delete(id),
    addEventListener:(event,fn)=>{(events[event]??=[]).push(fn);},
    async fetch(url,opt={}){
      requests.push({url,body:opt.body?JSON.parse(opt.body):{}});
      let status=200,data={};
      if(url==='/auth/me'){status=401;data={error:'Please sign in'};}
      else if(url==='/auth/login'){status=202;data={verification_required:true,challenge_id:'challenge-123',email:'test@example.com'};}
      else if(url==='/auth/login/verify'&&verifyError){status=400;data={error:verifyError};}
      return {status,ok:status<400,json:async()=>data};
    }
  };
  for(const id of ['loginForm','registerForm','loginVerifyForm','verifyForm','loginVerifyCode','loginVerifyEmailLabel','loginResendBtn','loginEmail','loginPassword','loginRemember'])ctx[id]=element(id);
  ctx.loginEmail.value='test@example.com';ctx.loginPassword.value='password';ctx.window=ctx;
  vm.createContext(ctx);vm.runInContext(source,ctx);
  return {ctx,element,events,requests,intervals,run:code=>vm.runInContext(code,ctx),error:value=>verifyError=value};
}
const settle=()=>new Promise(setImmediate);
(async()=>{
  let p=page();await settle();
  await p.run('login()');
  assert.equal(p.element('authError').textContent,'','no undefined timer error');
  assert.equal(p.element('loginVerifyForm').classList.contains('hidden'),false);
  assert.equal(p.element('loginForm').classList.contains('hidden'),true);
  assert.equal(p.element('loginResendBtn').disabled,true);
  assert.equal(JSON.parse(stored.lucas_login_challenge).id,'challenge-123');
  assert.equal(p.requests.find(x=>x.url==='/auth/login').body.remember,true);
  now+=10000;
  // A load event may run before the asynchronous /auth/me failure. Both orders must restore.
  p=page();for(const fn of p.events.load||[])fn();await settle();
  assert.equal(p.element('loginVerifyForm').classList.contains('hidden'),false);
  assert.equal(p.element('loginResendBtn').textContent,'Resend (50s)');
  p.run('showAuth()');
  assert.equal(p.element('loginVerifyForm').classList.contains('hidden'),false,'boot cannot lose verification state');
  p.element('loginVerifyCode').value='111111';p.error('Invalid verification code');
  await p.run('verifyLogin()');
  assert.equal(p.requests.at(-1).body.challenge_id,'challenge-123');
  assert.equal(p.element('authError').textContent,'Invalid verification code');
  assert.equal(p.element('loginVerifyForm').classList.contains('hidden'),false);
  now+=51000;for(const fn of [...p.intervals.values()])fn();
  assert.equal(p.element('loginResendBtn').disabled,false);
  await p.run('resendLoginVerification()');
  assert.equal(p.requests.at(-1).url,'/auth/login/resend');
  assert.equal(p.requests.at(-1).body.challenge_id,'challenge-123');
  assert.equal(p.element('loginResendBtn').disabled,true);
  assert.equal(JSON.parse(stored.lucas_login_challenge).expiresAt,now+600000);
  p=page();await settle();for(const fn of p.events.load||[])fn();
  assert.equal(p.element('loginVerifyForm').classList.contains('hidden'),false,'load after boot also restores');
  p.run('cancelLoginVerification()');
  assert.equal(stored.lucas_login_challenge,undefined);
  assert.equal(p.element('loginVerifyForm').classList.contains('hidden'),true);
  assert.equal(p.element('loginForm').classList.contains('hidden'),false);
  let count=p.requests.length;await p.run('verifyLogin()');
  assert.equal(p.requests.length,count,'missing challenge must not be sent to server');
  assert.equal(p.element('loginForm').classList.contains('hidden'),false);
  await p.run('login()');p.run('showRegister(true)');
  assert.equal(stored.lucas_login_challenge,undefined);
  assert.equal(p.element('loginVerifyForm').classList.contains('hidden'),true);
  assert.equal(p.element('registerForm').classList.contains('hidden'),false);
  await p.run('login()');now+=600001;p=page();await settle();
  assert.equal(stored.lucas_login_challenge,undefined);
  assert.equal(p.element('loginVerifyForm').classList.contains('hidden'),true);
  await p.run('login()');p.error('Login verification session expired');await p.run('verifyLogin()');
  assert.equal(stored.lucas_login_challenge,undefined);
  assert.equal(p.element('loginForm').classList.contains('hidden'),false);
  await p.run('login()');p.error('');await p.run('verifyLogin()');await settle();
  assert.equal(stored.lucas_login_challenge,undefined);
  assert.equal(p.intervals.size,0);
  stored.lucas_login_challenge='{broken';p=page();await settle();
  assert.equal(stored.lucas_login_challenge,undefined);
  console.log('PASS served dashboard login lifecycle');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
