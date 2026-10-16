import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
from linear_auth import LinearAuth, AuthError, PENDING, CALLBACK


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.auth=LinearAuth(Path(self.temp.name));self.auth.configure({'clientId':'app-test'})

    def test_pkce_read_scope_and_browser_binding(self):
        r,cookie=self.auth.start();query=parse_qs(urlparse(r['url']).query)
        self.assertEqual(query['scope'],['read']);self.assertEqual(query['redirect_uri'],[CALLBACK]);self.assertEqual(query['code_challenge_method'],['S256'])
        self.assertIn('HttpOnly',cookie)
        state=query['state'][0]
        with self.assertRaises(AuthError):self.auth.callback({'state':[state],'code':['not-used']},'')
        self.assertIn(state,PENDING)
        with self.assertRaises(AuthError):self.auth.callback({'state':[state],'error':['denied']},cookie)
        self.assertNotIn(state,PENDING)

    def test_secret_stays_private_and_refresh_once(self):
        self.auth.path.write_text(json.dumps({'clientId':'app-test','accessToken':'old','refreshToken':'refresh-secret','expiresAt':0,'user':{'name':'test'}}))
        with patch.object(self.auth,'_token_request',return_value={'access_token':'new','refresh_token':'rotated','expires_in':3600}) as request:
            self.assertEqual(self.auth.bearer(),'Bearer new');self.assertEqual(self.auth.bearer(),'Bearer new');self.assertEqual(request.call_count,1)
        status=json.dumps(self.auth.status())
        self.assertNotIn('rotated',status);self.assertNotIn('refresh-secret',status)
        self.assertEqual(self.auth.path.stat().st_mode&0o777,0o600)
        self.auth.logout();self.assertIsNone(self.auth.bearer());self.assertEqual(self.auth.status()['clientId'],'app-test')

    def test_expired_state_rejected_without_token_request(self):
        r,cookie=self.auth.start();state=parse_qs(urlparse(r['url']).query)['state'][0];PENDING[state]['created']=time.time()-601
        with patch.object(self.auth,'_token_request') as request:
            with self.assertRaises(AuthError):self.auth.callback({'state':[state],'code':['not-used']},cookie)
            request.assert_not_called()

    def test_refresh_failure_does_not_discard_saved_tokens(self):
        original={'clientId':'app-test','accessToken':'old','refreshToken':'keep','expiresAt':0}
        self.auth.path.write_text(json.dumps(original))
        with patch.object(self.auth,'_token_request',side_effect=AuthError('network')):
            with self.assertRaises(AuthError):self.auth.bearer()
        self.assertEqual(json.loads(self.auth.path.read_text()),original)


if __name__=='__main__':unittest.main()
