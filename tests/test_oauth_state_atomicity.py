"""Actual consume method with real SQLite; no Google, tokens, accounts or Node."""
import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

SOURCE=Path(__file__).parents[1]/'src/gpt_windows_connector/auth.py'
TREE=ast.parse(SOURCE.read_text(encoding='utf-8'))
CLASS=next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=='AuthStore')
METHOD=next(n for n in CLASS.body if isinstance(n,ast.FunctionDef) and n.name=='consume_oauth_state')
NAMESPACE={'hashlib':hashlib,'time':time,'closing':closing}
exec(compile(ast.Module(body=[METHOD],type_ignores=[]),str(SOURCE),'exec'),NAMESPACE)
CONSUME=NAMESPACE['consume_oauth_state']


class OAuthStateAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'states.sqlite'
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE oauth_states(state_hash TEXT PRIMARY KEY,expires_at REAL)')
        self.store=SimpleNamespace(_connect=self.connect)

    def connect(self):
        db=sqlite3.connect(self.path,timeout=5)
        db.row_factory=sqlite3.Row
        return db

    def seed(self,state,expiry):
        with closing(self.connect()) as db,db:
            db.execute('INSERT INTO oauth_states VALUES(?,?)',(hashlib.sha256(state.encode()).hexdigest(),expiry))

    def count(self):
        with closing(self.connect()) as db:
            return db.execute('SELECT COUNT(*) FROM oauth_states').fetchone()[0]

    def test_same_state_has_exactly_one_concurrent_consumer(self):
        self.seed('shared',time.time()+60)
        barrier=threading.Barrier(8)
        def consume(_):
            barrier.wait(timeout=10)
            try:
                CONSUME(self.store,'shared')
                return 'accepted'
            except PermissionError:
                return 'rejected'
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(consume,range(8)))
        self.assertEqual(results.count('accepted'),1)
        self.assertEqual(results.count('rejected'),7)
        self.assertEqual(self.count(),0)

    def test_valid_then_replay_rejected(self):
        self.seed('valid',time.time()+60)
        CONSUME(self.store,'valid')
        with self.assertRaises(PermissionError):CONSUME(self.store,'valid')

    def test_expired_is_deleted_and_unknown_preserves_other_state(self):
        self.seed('expired',time.time()-60);self.seed('valid',time.time()+60)
        with self.assertRaises(PermissionError):CONSUME(self.store,'expired')
        self.assertEqual(self.count(),1)
        with self.assertRaises(PermissionError):CONSUME(self.store,'unknown')
        self.assertEqual(self.count(),1)
        CONSUME(self.store,'valid')


if __name__=='__main__':unittest.main()
