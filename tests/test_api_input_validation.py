"""Actual HTTP handlers with synthetic SQLite/auth; no devices/providers."""
import sqlite3
import time
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.oauth import OAuthProvider
from gpt_windows_connector.operation_admission import OperationAdmissionStore
from gpt_windows_connector.task_runs import TaskRunStore


@pytest.fixture(scope='module')
def http_fixture(tmp_path_factory):
    from gpt_windows_connector import gateway, webapp
    path = tmp_path_factory.mktemp('input-boundary') / 'fixture.db'
    auth = AuthStore(path, 'synthetic-http-input-key-not-real'*2)
    owner = auth.register('owner@example.invalid', 'Synthetic-password-only')
    foreign = auth.register('foreign@example.invalid', 'Synthetic-password-only')
    oauth = OAuthProvider(path, auth, 'http://testserver')
    tasks = TaskRunStore(path)
    OperationAdmissionStore(path, auth_store=auth, task_store=tasks)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO oauth_clients VALUES(?,?,?,?)', ('fixture-client','Original client','[]',time.time()))
        db.execute('INSERT INTO oauth_client_users VALUES(?,?,?)', ('fixture-client',owner.id,time.time()))
    class Registry:
        async def list(self,user):
            return [{'node_id':'fixture-node','name':'Original computer'}] if user.id==owner.id else []
    app = Starlette(routes=[*webapp.routes, Route('/oauth/register',oauth.register,methods=['POST'])])
    with pytest.MonkeyPatch.context() as patch:
        for name,value in {'auth':auth,'db_path':path,'task_runs':tasks,'registry':Registry()}.items():
            patch.setattr(gateway,name,value)
        with TestClient(app,raise_server_exceptions=False) as client:
            yield SimpleNamespace(client=client,path=path,auth=auth,owner=owner,
                headers={'Authorization':'Bearer '+auth.issue_token(owner)},
                foreign_headers={'Authorization':'Bearer '+auth.issue_token(foreign)})


INVALID_BODIES = ['{','[]','null','"fixture"','7','true']
METADATA_ROUTES = ['/api/nodes/fixture-node/name','/api/ai-connections/fixture-client']


def metadata_state(path):
    with sqlite3.connect(path) as db:
        from gpt_windows_connector.webapp import _ensure_dashboard_metadata_schema
        _ensure_dashboard_metadata_schema(db)
        return {table:db.execute('SELECT * FROM '+table).fetchall() for table in
                ['dashboard_node_metadata','dashboard_ai_metadata','oauth_client_users','audit_logs']}


@pytest.mark.parametrize('body', INVALID_BODIES)
@pytest.mark.parametrize('route', METADATA_ROUTES)
def test_invalid_metadata_body_returns_400_without_mutation(http_fixture,route,body):
    x=http_fixture;before=metadata_state(x.path)
    response=x.client.put(route,content=body,headers={**x.headers,'Content-Type':'application/json'})
    assert response.status_code==400 and response.json()=={'error':'invalid_request_body'}
    assert metadata_state(x.path)==before


@pytest.mark.parametrize('body', INVALID_BODIES)
def test_oauth_registration_rejects_nonobjects_without_client_creation(http_fixture,body):
    x=http_fixture
    with sqlite3.connect(x.path) as db:before=db.execute('SELECT * FROM oauth_clients').fetchall()
    response=x.client.post('/oauth/register',content=body,headers={'Content-Type':'application/json'})
    assert response.status_code==400 and response.json()=={'error':'invalid_client_metadata'}
    with sqlite3.connect(x.path) as db:assert db.execute('SELECT * FROM oauth_clients').fetchall()==before


def test_oauth_object_validation_and_valid_registration_unchanged(http_fixture):
    client=http_fixture.client
    assert client.post('/oauth/register',json={}).json()=={'error':'invalid_redirect_uri'}
    response=client.post('/oauth/register',json={'client_name':'Synthetic','redirect_uris':['https://example.invalid/callback']})
    assert response.status_code==201 and response.json()['client_name']=='Synthetic'


@pytest.mark.parametrize('route', METADATA_ROUTES)
def test_metadata_authorization_and_missing_resource_precede_body_validation(http_fixture,route):
    x=http_fixture;before=metadata_state(x.path)
    response=x.client.put(route,content='[]',headers={**x.foreign_headers,'Content-Type':'application/json'})
    assert response.status_code==404
    missing=route.replace('fixture-node','missing-node').replace('fixture-client','missing-client')
    assert x.client.put(missing,json=[],headers=x.headers).status_code==404
    assert metadata_state(x.path)==before


def test_valid_metadata_and_empty_object_keep_clear_and_default_semantics(http_fixture):
    x=http_fixture
    response=x.client.put(METADATA_ROUTES[0],json={'name':'  New computer  '},headers=x.headers)
    assert response.status_code==200 and response.json()['display_name']=='New computer'
    response=x.client.put(METADATA_ROUTES[0],json={},headers=x.headers)
    assert response.status_code==200 and response.json()['display_name']=='Original computer'
    response=x.client.put(METADATA_ROUTES[1],json={'display_name':' New client ','note':' Note '},headers=x.headers)
    assert response.status_code==200 and response.json()['note']=='Note'
    response=x.client.put(METADATA_ROUTES[1],json={},headers=x.headers)
    assert response.status_code==200 and response.json()=={'ok':True,'display_name':'Original client','note':''}


@pytest.mark.parametrize('route',['/api/task-runs','/api/logs'])
@pytest.mark.parametrize('value',['abc','','1.5','nan','1e3'])
def test_invalid_history_limit_is_client_error(http_fixture,route,value):
    x=http_fixture;before=metadata_state(x.path)
    response=x.client.get(route,params={'limit':value},headers=x.headers)
    assert response.status_code==400 and response.json()=={'error':'invalid_limit'}
    assert metadata_state(x.path)==before


@pytest.mark.parametrize('route',['/api/task-runs','/api/logs'])
@pytest.mark.parametrize('value',['0','-1','501','1',' +2 '])
def test_valid_integer_history_limits_keep_clamping(http_fixture,route,value,monkeypatch):
    from gpt_windows_connector import gateway
    x=http_fixture;limits=[]
    if route=='/api/task-runs':
        original=gateway.task_runs.list_runs
        def capture(*args,**kwargs):
            limits.append(kwargs['limit']);return original(*args,**kwargs)
        monkeypatch.setattr(gateway.task_runs,'list_runs',capture)
    response=x.client.get(route,params={'limit':value},headers=x.headers)
    assert response.status_code==200
    expected=max(1,min(int(value),500))
    if limits:assert limits==[expected]
    if route=='/api/logs':assert len(response.json()['logs'])<=expected
