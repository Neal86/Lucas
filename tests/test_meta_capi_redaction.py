"""Synthetic-only failure logs; no external Meta request or real credential."""
import asyncio
import logging
from unittest.mock import patch

import httpx
import pytest

from gpt_windows_connector.meta_capi import MetaConversionsAPI


@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize('failure', ['http', 'transport', 'payload'])
def test_failed_event_logs_classification_without_sensitive_error_text(caplog, asynchronous, failure):
    api = MetaConversionsAPI.__new__(MetaConversionsAPI)
    api.base_url = 'https://example.invalid'; api.pixel_id = 'synthetic-pixel'
    api.access_token = 'SYNTHETIC_TOKEN_NOT_A_SECRET'; api.test_event_code = ''
    def post(url, **kwargs):
        if failure == 'transport':
            raise httpx.ConnectError('SYNTHETIC_TOKEN_NOT_A_SECRET private email@example.invalid')
        if failure == 'payload':
            raise ValueError('SYNTHETIC_TOKEN_NOT_A_SECRET private event payload')
        request = httpx.Request('POST', url, params=kwargs['params'])
        return httpx.Response(400, request=request, text='private response body')
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs): return post(url, **kwargs)
    with caplog.at_level(logging.WARNING, logger='lucas.meta_capi'):
        with patch('gpt_windows_connector.meta_capi.httpx.post', side_effect=post), patch('gpt_windows_connector.meta_capi.httpx.AsyncClient', Client):
            result = asyncio.run(api.send_async('SyntheticEvent', event_id='fixture')) if asynchronous else api.send('SyntheticEvent', event_id='fixture')
    assert result is False
    assert 'SyntheticEvent' in caplog.text and 'error_type=' in caplog.text
    for forbidden in [api.access_token, 'access_token=', 'https://', 'private', 'email@example.invalid']:
        assert forbidden not in caplog.text


def test_success_and_disabled_semantics_are_unchanged(monkeypatch, caplog):
    api = MetaConversionsAPI.__new__(MetaConversionsAPI)
    api.base_url='https://example.invalid'; api.pixel_id='synthetic'; api.access_token='synthetic'; api.test_event_code=''
    calls=[]
    def post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, request=httpx.Request('POST',url), json={'ok':True})
    monkeypatch.setattr('gpt_windows_connector.meta_capi.httpx.post', post)
    assert api.send('SyntheticEvent',event_id='fixture') is True
    assert calls[0]['params'] == {'access_token':'synthetic'}
    assert calls[0]['json']['data'][0]['event_id'] == 'fixture'
    api.access_token=''
    assert api.send('SyntheticEvent',event_id='fixture') is False
    assert len(calls)==1 and not caplog.records
