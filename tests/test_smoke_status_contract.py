"""Execute actual smoke decision code with synthetic HTTP responses; no network."""
from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'src'))
from gpt_windows_connector.web_smoke_routes import WEB_SMOKE_ROUTES, expected_statuses
spec=importlib.util.spec_from_file_location('lucas_smoke_script',ROOT/'scripts/smoke_web_pages.py')
smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)


class SmokeStatusTests(unittest.TestCase):
    def check(self,status,expected):
        error=urllib.error.HTTPError('http://fixture.invalid/route',status,'synthetic response',{},None)
        output=io.StringIO()
        with patch.object(smoke,'WEB_SMOKE_ROUTES',(('/route',expected),)), patch.object(smoke.urllib.request,'urlopen',side_effect=error),redirect_stdout(output):
            result=smoke.check('http://fixture.invalid')
        return result,output.getvalue()

    def test_every_public_route_requires_200(self):
        for path,expected in WEB_SMOKE_ROUTES:
            if expected is not None:
                self.assertEqual(expected_statuses(expected),{200},path)
        self.assertEqual(self.check(200,200)[0],0)
        for status in [301,302,401,403,404,429,500]:
            self.assertEqual(self.check(status,200)[0],1)

    def test_auth_routes_accept_only_documented_render_redirect_or_denial(self):
        for status in [200,301,302,303,307,308,401,403]:
            self.assertEqual(self.check(status,None)[0],0)
        self.assertEqual({path for path,expected in WEB_SMOKE_ROUTES if expected is None},
            {'/billing','/billing/success','/billing/cancel','/admin','/admin/users','/admin/usage','/admin/nodes','/admin/operations','/admin/subscriptions','/admin/system'})

    def test_missing_route_and_other_bad_statuses_block_release(self):
        for status in [100,201,204,304,400,404,405,408,429,500,503]:
            result,text=self.check(status,None)
            self.assertEqual(result,1,status)
            self.assertIn('RELEASE BLOCKED',text)
            self.assertNotIn('WEB_SMOKE_OK',text)

    def test_successful_http_context_is_closed(self):
        response=MagicMock()
        response.__enter__.return_value.status=200
        with patch.object(smoke,'WEB_SMOKE_ROUTES',(('/admin',None),)),patch.object(smoke.urllib.request,'urlopen',return_value=response),redirect_stdout(io.StringIO()):
            self.assertEqual(smoke.check('http://fixture.invalid'),0)
        response.__exit__.assert_called_once()

    def test_network_errors_are_failures(self):
        output=io.StringIO()
        with patch.object(smoke,'WEB_SMOKE_ROUTES',(('/admin',None),)),patch.object(smoke.urllib.request,'urlopen',side_effect=OSError('synthetic unavailable')),redirect_stdout(output):
            self.assertEqual(smoke.check('http://fixture.invalid'),1)
        self.assertIn('request failed',output.getvalue())


if __name__=='__main__':unittest.main()
