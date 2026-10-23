import sys
import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='native Windows settings UI')
def test_native_browser_install_manage_flow(tmp_path, monkeypatch, request):
    import json, time, tkinter as tk
    from tkinter import simpledialog
    from gpt_windows_connector import settings_browser_setup_ui as ui
    root=tk.Tk();root.withdraw()
    request.addfinalizer(root.destroy)
    root_path=tmp_path
    state={'running':True,'clients':[]}; calls=[]
    def fake_backend(action='status',**params):
        calls.append(action)
        if action=='pair':state['clients'][0]['paired']=True
        if action=='disconnect':state['clients'][0]['paired']=False
        return json.loads(json.dumps(state)) if action=='status' else {}
    monkeypatch.setattr(ui,"settings_request",fake_backend)
    monkeypatch.setattr(ui,'prepare_extension',lambda:{'path':str(root_path)})
    monkeypatch.setattr(ui,'store_url',lambda browser:None)
    colors={'window':'#ffffff','card':'#ffffff','line':'#e5e5e5','text':'#1f1f1f','muted':'#6b6b6b','blue':'#0f8ce9'}
    frame=ui.build_browser_setup(tk=tk,parent=root,colors=colors,font='Segoe UI',translate=lambda zh,en:en,on_change=lambda:None)
    def pump(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update();time.sleep(.02)
    def walk(widget):
        for child in widget.winfo_children():
            yield child
            yield from walk(child)
    def buttons(text):return [w for w in walk(frame) if isinstance(w,tk.Button) and w.cget('text')==text]
    pump(.6)
    assert len(buttons('Install'))==3
    buttons('Install')[0].invoke();root.update()
    guide=next(w for w in walk(root) if isinstance(w,tk.Toplevel))
    assert any(isinstance(w,tk.Label) and 'store listing is not configured' in w.cget('text') for w in walk(guide))
    guide.destroy()
    opened=[];monkeypatch.setattr(ui,'store_url',lambda browser:'https://chromewebstore.google.com/detail/'+'a'*32);monkeypatch.setattr(ui,'open_store_url',lambda browser,url: (opened.append(url) or True))
    buttons('Install')[0].invoke();assert len(opened)==1
    state['clients']=[{'browser_type':'chrome','installation_id':'test','connected':True,'paired':False}]
    pump(3.5)
    assert len(buttons('Manage'))==1
    buttons('Manage')[0].invoke();root.update()
    manager=next(w for w in walk(root) if isinstance(w,tk.Toplevel))
    monkeypatch.setattr(simpledialog,'askstring',lambda *args,**kwargs:'123456')
    next(w for w in walk(manager) if isinstance(w,tk.Button) and w.cget('text')=='Pair').invoke()
    pump(.7)
    assert 'pair' in calls
    assert any(isinstance(w,tk.Label) and w.cget('text')=='Connected' for w in walk(frame))
    manager.destroy()
    print('PASS native Tk: 3 browser cards, manual install guide, approved store link, Manage, pairing, Connected')
