"""Actual temporary port files; synthetic process and monotonic clock, no browser."""
import ast
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).with_name('test_oauth_login_chromium.py')
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
HELPER = next(n for n in TREE.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'wait_for_debugging_port')


class PortReadinessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.port = Path(self.temp.name) / 'DevToolsActivePort'
        self.log = Path(self.temp.name) / 'stderr'
        self.log.write_text('synthetic browser error', encoding='utf-8')
        self.now = 0.0
        self.sleeps = []
        self.exit_code = None
        self.on_sleep = lambda: None
        async def sleep(delay):
            self.sleeps.append(delay)
            self.now += delay
            self.on_sleep()
        def fail(message):
            raise AssertionError(message)
        namespace = {'time': SimpleNamespace(monotonic=lambda: self.now),
                     'asyncio': SimpleNamespace(sleep=sleep), 'pytest': SimpleNamespace(fail=fail)}
        exec(compile(ast.Module(body=[HELPER], type_ignores=[]), str(SOURCE), 'exec'), namespace)
        self.wait = namespace['wait_for_debugging_port']
        self.process = SimpleNamespace(poll=lambda: self.exit_code)

    async def run_wait(self):
        return await self.wait(self.process, self.port, self.log)

    def ready(self):
        self.port.write_text('12345\n/devtools/browser/synthetic-id', encoding='utf-8')

    async def test_complete_contents_return_without_wait(self):
        self.ready()
        self.assertEqual(await self.run_wait(), '12345')
        self.assertEqual(self.sleeps, [])

    async def test_missing_then_empty_then_partial_file_waits_for_complete_port(self):
        stages = iter(['', '12', '12345\n', '12345\n/devtools/browser/', '12345\n/devtools/browser/synthetic-id'])
        self.on_sleep = lambda: self.port.write_text(next(stages), encoding='utf-8')
        self.assertEqual(await self.run_wait(), '12345')
        self.assertEqual(len(self.sleeps), 5)

    async def test_invalid_port_does_not_escape_as_ready(self):
        for invalid in ['0', '65536', '-1', 'abc', '１２３']:
            self.port.write_text(invalid + '\n/devtools/browser/synthetic-id', encoding='utf-8')
            self.on_sleep = self.ready
            before = len(self.sleeps)
            self.assertEqual(await self.run_wait(), '12345')
            self.assertEqual(len(self.sleeps), before + 1)

    async def test_process_exit_propagates_diagnostic(self):
        self.exit_code = 1
        with self.assertRaisesRegex(AssertionError, 'synthetic browser error'):
            await self.run_wait()
        self.assertEqual(self.sleeps, [])

    async def test_process_exit_after_file_read_is_not_ready(self):
        self.ready()
        values = iter([None, 1])
        self.process.poll = lambda: next(values)
        with self.assertRaisesRegex(AssertionError, 'exited before'):
            await self.run_wait()

    async def test_empty_file_times_out_with_original_fifteen_second_budget(self):
        self.port.write_text('', encoding='utf-8')
        with self.assertRaisesRegex(AssertionError, 'did not expose'):
            await self.run_wait()
        self.assertAlmostEqual(sum(self.sleeps), 15.0)
        self.assertLessEqual(self.now, 15.0)


if __name__ == '__main__':
    unittest.main()
