"""Actual handler/helper AST and ASGI, explicit auth/mail/downstream fixtures."""
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import AsyncMock
import uuid

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

ROOT = Path(__file__).parents[1] / 'src/gpt_windows_connector'


def extract(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert {n.name for n in nodes} == names
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, 'exec'), namespace)


class JsonBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls = []
        def auth(request):
            self.calls.append('auth')
            if request.headers.get('x-test-auth') != 'yes':
                raise PermissionError('synthetic auth required')
            return SimpleNamespace(id='fixture-user')
        def rate(*args, **kwargs):
            self.calls.append('rate')
            return False
        def verify(*args):
            self.calls.append('verify')
            raise ValueError('synthetic missing verification fields')
        self.namespace = {'Request':Request,'JSONResponse':JSONResponse,'Any':Any,'uuid':uuid,
                          'email_verification_enabled':lambda:True,'_registration_rate_ok':rate,
                          'registration_security':SimpleNamespace(verify=verify), '_auth_user':auth}
        extract('api_inputs.py', {'read_json_object'}, self.namespace)
        extract('gateway.py', {'auth_register','auth_verify_email','auth_resend_verification'}, self.namespace)
        extract('webapp.py', {'api_request_node_access'}, self.namespace)
        names = [('register','auth_register'),('verify','auth_verify_email'),('resend','auth_resend_verification'),('access','api_request_node_access')]
        self.app = Starlette(routes=[Route('/'+path, self.namespace[name], methods=['POST']) for path,name in names])

    async def post(self, path, content):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app,raise_app_exceptions=False),base_url='http://fixture') as client:
            return await client.post('/'+path,content=content,headers={'content-type':'application/json','x-test-auth':'yes'})

    async def test_all_four_routes_reject_nonobjects_and_malformed_json(self):
        for route in ['register','verify','resend','access']:
            for body in ['[]','null','"text"','42','true','{']:
                with self.subTest(route=route,body=body):
                    self.calls.clear()
                    response = await self.post(route,body)
                    self.assertEqual(response.status_code,400,response.text)
                    self.assertIn('error',response.json())
                    self.assertEqual(self.calls,['auth'] if route=='access' else [])

    async def test_empty_objects_reach_existing_business_validation(self):
        for route,code,call in [('register',429,'rate'),('verify',400,'verify'),('resend',429,'rate'),('access',400,'auth')]:
            self.calls.clear()
            response = await self.post(route,'{}')
            self.assertEqual(response.status_code,code,response.text)
            self.assertEqual(self.calls,[call])
        self.assertEqual((await self.post('access','{}')).json()['error'],'Node ID is required')

    async def test_disabled_email_configuration_still_precedes_body_read(self):
        self.namespace['email_verification_enabled'] = lambda:False
        for route in ['verify','resend']:
            self.assertEqual((await self.post(route,'[]')).status_code,503)

    async def test_access_authentication_still_precedes_body_read(self):
        request = SimpleNamespace(headers={},json=AsyncMock(return_value=[]))
        with self.assertRaises(PermissionError):
            await self.namespace['api_request_node_access'](request)
        request.json.assert_not_awaited()


if __name__=='__main__':
    unittest.main()
