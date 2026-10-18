"""Isolated production-handler regression: real SQLite and in-process ASGI.

Only the three named admin functions are compiled from source. Authentication
is a synthetic fixture, not proof of the gateway's real authorization behavior.
No gateway/Node/security modules or external services are loaded.
"""
import ast
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


class AdminOperationsQueryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / 'operations.sqlite'
        with self.db() as db:
            db.executescript('''
                CREATE TABLE users(id TEXT PRIMARY KEY,email TEXT);
                CREATE TABLE task_steps(id TEXT PRIMARY KEY,owner_id TEXT,
                    action TEXT,target TEXT,details TEXT,operation_count INTEGER,
                    started_at REAL,status TEXT);
                INSERT INTO users VALUES('u1','first@example.test');
                INSERT INTO users VALUES('u2','second@example.test');
            ''')
        source = Path(__file__).parents[1] / 'src/gpt_windows_connector/admin.py'
        module = ast.parse(source.read_text(encoding="utf-8"))
        wanted = {'operations', '_safe_details', '_error'}
        nodes = [n for n in module.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in wanted]
        self.assertEqual({n.name for n in nodes}, wanted)
        namespace = {'Request': Request, 'JSONResponse': JSONResponse,
                     'json': json, '_db': self.db, '_admin': self.authorize}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
        self.app = Starlette(routes=[Route('/api/admin/operations', namespace['operations'])])

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def authorize(request):
        if request.headers.get('x-test-role') != 'admin':
            raise PermissionError('Admin access required')

    def add(self, id, timestamp, status='success', details='{}', owner='u1', action='files.read'):
        with self.db() as db:
            db.execute('INSERT INTO task_steps VALUES(?,?,?,?,?,?,?,?)',
                       (id, owner, action, '/fixture', details, 1, timestamp, status))

    async def get(self, params=None, role='admin'):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test') as client:
            return await client.get('/api/admin/operations', params=params, headers={'x-test-role': role})

    async def rows(self, **params):
        result = await self.get(params)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()['operations']

    async def test_recent_timestamp_wins_over_reverse_uuid(self):
        self.add('ffff', 100)
        self.add('0000', 200)
        self.assertEqual([r['id'] for r in await self.rows(limit=1)], ['0000'])

    async def test_tied_timestamps_have_stable_id_order(self):
        self.add('a', 200)
        self.add('z', 200)
        self.assertEqual([r['id'] for r in await self.rows()], ['z', 'a'])

    async def test_status_filter_precedes_limit(self):
        self.add('ffff', 200, 'success')
        self.add('0000', 100, 'error')
        self.assertEqual([r['id'] for r in await self.rows(status='error', limit=1)], ['0000'])

    async def test_multiple_matches_fill_limit_after_skips(self):
        for n in range(20):
            self.add(str(n), n, 'error' if n % 4 == 0 else 'success')
        self.assertEqual([r['created_at'] for r in await self.rows(status='error', limit=3)], [16, 12, 8])

    async def test_legacy_status_fallback(self):
        self.add('a', 1, None, '{"status":"error"}')
        self.add('b', 2, '', '{"status":"error"}')
        self.assertEqual([r['id'] for r in await self.rows(status='error')], ['b', 'a'])

    async def test_column_status_has_precedence(self):
        self.add('a', 1, 'success', '{"status":"error"}')
        self.assertEqual(await self.rows(status='error'), [])

    async def test_missing_legacy_status_defaults_success(self):
        self.add('a', 1, None)
        self.assertEqual((await self.rows(status='success'))[0]['id'], 'a')

    async def test_legacy_null_and_empty_status_not_defaulted(self):
        self.add('a', 1, None, '{"status":null}')
        self.add('b', 2, '', '{"status":""}')
        self.assertEqual(await self.rows(status='success'), [])
        self.assertEqual([r['status'] for r in await self.rows()], ['', None])

    async def test_combined_owner_action_status(self):
        self.add('a', 1, 'error')
        self.add('b', 2, 'error', owner='u2')
        self.add('c', 3, 'error', action='git.status')
        self.add('d', 4, 'success')
        self.assertEqual([r['id'] for r in await self.rows(user='u1', action='files', status='error', limit=1)], ['a'])
        self.assertEqual([r['id'] for r in await self.rows(user='first@', action='files', status='error')], ['a'])

    async def test_user_and_action_values_remain_bound(self):
        self.add('a', 1)
        self.assertEqual(await self.rows(user="' OR 1=1 --"), [])
        self.assertEqual(await self.rows(action="' OR 1=1 --"), [])

    async def test_invalid_limit_returns_400(self):
        self.assertEqual((await self.get({'limit':'bad'})).status_code, 400)

    async def test_limit_clamping(self):
        with self.db() as db:
            db.executemany('INSERT INTO task_steps VALUES(?,?,?,?,?,?,?,?)',
                [(str(n), 'u1', 'read', '', '{}', 1, n, 'error') for n in range(1005)])
        self.assertEqual(len(await self.rows(limit=-1)), 1)
        self.assertEqual(len(await self.rows(limit=2000)), 1000)
        self.assertEqual(len(await self.rows(limit=2000, status='error')), 1000)

    async def test_details_redaction_preserved(self):
        self.add('a', 1, 'error', '{"token":"synthetic","label":"visible"}')
        self.assertEqual((await self.rows(status='error'))[0]['details'], {'token':'[redacted]', 'label':'visible'})

    async def test_authorization_guard_called_before_read(self):
        self.assertEqual((await self.get(role='user')).status_code, 403)

    async def test_orphan_owner_still_visible(self):
        self.add('a', 1, owner='removed')
        self.assertIsNone((await self.rows())[0]['email'])

    async def test_non_object_legacy_details_do_not_block_filtered_rows(self):
        for index, raw in enumerate(['[]', 'null', '42', 'true', '"text"', '{bad']):
            self.add(str(index), 100 + index, 'success', raw)
        self.add('old-error', 1, 'error')
        self.assertEqual([r['id'] for r in await self.rows(status='error', limit=1)], ['old-error'])

    async def test_non_object_legacy_details_default_to_empty(self):
        for index, raw in enumerate(['[]', 'null', '42', 'true', '"text"', '{bad']):
            self.add(str(index), index, None, raw)
        result = await self.rows(status='success')
        self.assertEqual(len(result), 6)
        self.assertTrue(all(row['details'] == {} for row in result))

    async def test_unknown_filter_returns_empty(self):
        self.add('a', 1)
        self.assertEqual(await self.rows(status='unknown-fixture'), [])


if __name__ == '__main__':
    unittest.main()
