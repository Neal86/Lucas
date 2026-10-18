"""Real SQLite initializer checks; AST isolation does not exercise auth/Node."""
import ast
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).parents[1] / 'src/gpt_windows_connector/task_runs.py'
module = ast.parse(SOURCE.read_text(encoding='utf-8'))
klass = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == 'TaskRunStore')
klass.body = [node for node in klass.body if isinstance(node, ast.FunctionDef) and node.name in {'__init__', '_connect', '_init_db'}]
namespace = {'Path': Path, 'sqlite3': sqlite3, 'time': time, '_startup_clock': time, 'closing': closing}
exec(compile(ast.Module(body=[klass], type_ignores=[]), str(SOURCE), 'exec'), namespace)
TaskRunStore = namespace['TaskRunStore']


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'tasks.sqlite'

    def test_eight_simultaneous_constructors_preserve_schema_and_data(self):
        # Repeated real contention, no reduced worker count or retries of tests.
        for round_number in range(30):
            path = self.path.with_name(f'tasks-{round_number}.sqlite')
            db = sqlite3.connect(path)
            try:
                db.execute('CREATE TABLE sentinel(value TEXT)')
                db.execute("INSERT INTO sentinel VALUES('unchanged')")
                db.commit()
            finally:
                db.close()
            barrier = threading.Barrier(8)
            def initialize(_):
                barrier.wait(timeout=10)
                TaskRunStore(path)
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(initialize, range(8)))
            db = sqlite3.connect(path)
            try:
                self.assertEqual(db.execute('SELECT value FROM sentinel').fetchall(), [('unchanged',)])
                columns = [row[1] for row in db.execute('PRAGMA table_info(task_runs)')]
                self.assertEqual(columns.count('identity_version'), 1)
                self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            finally:
                db.close()

    def test_wall_clock_replacement_does_not_affect_startup_clock(self):
        # Existing history tests freeze task_runs.time for duration assertions.
        with patch.dict(namespace, {'time': SimpleNamespace(time=lambda: 1234)}):
            TaskRunStore(self.path)
        db = sqlite3.connect(self.path)
        try:
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
        finally:
            db.close()

    def connection_probe(self, failures):
        db = Mock()
        effects = iter(failures)
        def execute(sql):
            if sql == 'PRAGMA journal_mode=WAL':
                error = next(effects, None)
                if error:
                    raise error
        db.execute.side_effect = execute
        store = object.__new__(TaskRunStore)
        store.path = self.path
        return store, db

    @staticmethod
    def error(code):
        error = sqlite3.OperationalError('synthetic SQLite error')
        error.sqlite_errorcode = code
        return error

    def test_busy_transition_retries_and_returns_open_connection(self):
        store, db = self.connection_probe([self.error(sqlite3.SQLITE_BUSY), None])
        with patch.object(sqlite3, 'connect', return_value=db), patch.object(time, 'sleep') as sleep:
            self.assertIs(store._connect(), db)
        self.assertEqual(db.execute.call_count, 4)
        self.assertEqual(db.execute.call_args.args, ('PRAGMA busy_timeout=30000',))
        sleep.assert_called_once()
        db.close.assert_not_called()

    def test_expired_busy_budget_propagates_and_closes_connection(self):
        error = self.error(sqlite3.SQLITE_BUSY)
        store, db = self.connection_probe([error])
        with patch.object(sqlite3, 'connect', return_value=db), patch.object(time, 'monotonic', side_effect=[0, 31]), patch.object(time, 'sleep') as sleep:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                store._connect()
        self.assertIs(caught.exception, error)
        db.close.assert_called_once()
        sleep.assert_not_called()

    def test_non_busy_errors_propagate_without_retry_and_close(self):
        for code in [sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_READONLY, sqlite3.SQLITE_CORRUPT]:
            with self.subTest(code=code):
                error = self.error(code)
                store, db = self.connection_probe([error])
                with patch.object(sqlite3, 'connect', return_value=db), patch.object(time, 'sleep') as sleep:
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        store._connect()
                self.assertIs(caught.exception, error)
                db.close.assert_called_once()
                sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
