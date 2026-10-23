import io
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from backend import updates
from backend.app import create_app
from backend.updates import CACHE_SECONDS, UpdateChecker

CURRENT = 'a' * 40
LATEST = 'b' * 40
KEY = 'test-secret-key-with-at-least-24-characters'


def registry(latest=LATEST, status='ahead'):
    calls = []

    def fetch(url, headers=None):
        calls.append((url, headers))
        if '/token?' in url:
            return {'token': 'public-registry-token'}
        if '/manifests/latest' in url:
            return {'annotations': {'org.opencontainers.image.revision': latest}}
        return {'status': status}

    return fetch, calls


def test_newer_published_image_and_cache():
    fetch, calls = registry()
    now = [100.0]
    checker = UpdateChecker(CURRENT, fetch=fetch, clock=lambda: now[0])
    result = checker.check()
    assert result == {'status': 'available', 'current_revision': CURRENT, 'latest_revision': LATEST}
    assert len(calls) == 3
    assert calls[1][1]['Authorization'] == 'Bearer public-registry-token'
    assert 'Authorization' not in calls[2][1]
    assert f'/compare/{CURRENT}...{LATEST}' in calls[2][0]
    result['status'] = 'modified by caller'
    assert checker.check()['status'] == 'available'
    assert len(calls) == 3
    now[0] += CACHE_SECONDS
    checker.check()
    assert len(calls) == 6


def test_same_image_needs_no_compare_request():
    fetch, calls = registry(CURRENT)
    assert UpdateChecker(CURRENT, fetch=fetch).check()['status'] == 'current'
    assert len(calls) == 2


@pytest.mark.parametrize('status, expected', [
    ('behind', 'current'), ('identical', 'current'),
    ('diverged', 'unavailable'), ('unexpected', 'unavailable'),
])
def test_does_not_offer_older_or_unrelated_image(status, expected):
    fetch, _ = registry(status=status)
    assert UpdateChecker(CURRENT, fetch=fetch).check()['status'] == expected


@pytest.mark.parametrize('revision', ['', 'development', '../main', 'x' * 40])
def test_source_build_does_not_contact_network(revision):
    def unexpected(*args):
        pytest.fail('Source build contacted registry')
    assert UpdateChecker(revision, fetch=unexpected).check()['status'] == 'unmanaged'


@pytest.mark.parametrize('latest', [None, '', 'main', '../../evil', ['bad'], 'x' * 40])
def test_missing_or_invalid_published_revision(latest):
    fetch, calls = registry(latest)
    assert UpdateChecker(CURRENT, fetch=fetch).check()['status'] == 'unavailable'
    assert len(calls) == 2


@pytest.mark.parametrize('error', [TimeoutError(), OSError('DNS unavailable'),
                                  ValueError('Invalid JSON'),
                                  HTTPError('https://ghcr.io', 429, 'Rate limited', {}, None)])
def test_failed_check_is_cached_and_retried(error):
    now = [100.0]
    attempts = []
    fetch, _ = registry(CURRENT)

    def flaky(url, headers=None):
        attempts.append(url)
        if len(attempts) == 1:
            raise error
        return fetch(url, headers)

    checker = UpdateChecker(CURRENT, fetch=flaky, clock=lambda: now[0])
    assert checker.check()['status'] == 'unavailable'
    assert checker.check()['status'] == 'unavailable'
    assert len(attempts) == 1
    now[0] += CACHE_SECONDS
    assert checker.check()['status'] == 'current'


def test_concurrent_checks_share_cached_result():
    fetch, calls = registry()
    checker = UpdateChecker(CURRENT, fetch=fetch)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: checker.check(), range(8)))
    assert all(result['status'] == 'available' for result in results)
    assert len(calls) == 3


def test_api_authentication_and_safe_failure(tmp_path, monkeypatch):
    calls = []

    def check(self):
        calls.append(True)
        return {'status': 'unavailable', 'current_revision': CURRENT, 'latest_revision': None}

    monkeypatch.setattr(UpdateChecker, 'check', check)
    with TestClient(create_app(data_dir=tmp_path, api_key=KEY)) as client:
        assert client.get('/api/updates').status_code == 401
        assert not calls
        response = client.get('/api/updates', headers={'Authorization': f'Bearer {KEY}'})
        assert response.status_code == 200
        assert response.json()['status'] == 'unavailable'
        assert response.headers['cache-control'] == 'no-store'
        assert KEY not in response.text
        assert client.get('/health').status_code == 200
        assert client.get('/api/jobs', headers={'Authorization': f'Bearer {KEY}'}).status_code == 200


def test_http_timeout_and_response_limit(monkeypatch):
    seen = []

    def urlopen(request, timeout):
        seen.append((request, timeout))
        return io.BytesIO(b' ' * (updates.MAX_RESPONSE_BYTES + 1))

    monkeypatch.setattr(updates, 'urlopen', urlopen)
    with pytest.raises(ValueError, match='too large'):
        updates.read_json('https://ghcr.io/example')
    assert seen[0][1] == 5
    assert seen[0][0].get_header('Authorization') is None
