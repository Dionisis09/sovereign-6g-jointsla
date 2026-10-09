"""MaaS UI boundary: validation, one-shot requests and honest failure accounting."""
import io
import json
from urllib.error import HTTPError
import pytest
from PIL import Image
from dashboard import maas


def test_image_body_is_valid_and_fits_existing_http_limit():
    output = io.BytesIO()
    Image.new('RGB', (32, 32)).save(output, format='PNG')
    body = maas.payload('Gold', 200, image=output.getvalue())
    assert 'seed' not in body and 'image_base64' in body
    assert len(json.dumps(body).encode()) < 1_500_000
    assert body['tier'] == 'Gold'


@pytest.mark.parametrize('image', [b'not an image', b'x' * 1_000_001], ids=['invalid', 'oversize'])
def test_bad_images_rejected_before_network(image):
    with pytest.raises((ValueError, OSError)):
        maas.payload('Gold', 200, image=image)


@pytest.mark.parametrize('args', [('Other', 200), ('Gold', 0), ('Gold', 60001)])
def test_invalid_tier_or_deadline_rejected(args):
    with pytest.raises(ValueError):
        maas.payload(*args)


def test_success_sends_exactly_one_request_and_retains_prediction(monkeypatch):
    calls = []
    class Response(io.BytesIO):
        code = 200
    def send(req, timeout):
        calls.append(req)
        return Response(json.dumps({'predictions': [{'label': 'cat', 'score': .7}], 'gateway_latency_ms': 3}).encode())
    monkeypatch.setattr(maas.request, 'urlopen', send)
    outcome = maas.infer(maas.payload('Silver', 60000, seed=1))
    assert len(calls) == 1
    assert calls[0].full_url == maas.GATEWAY + '/infer'
    assert outcome['http_status'] == 200 and not outcome['client_sla_failure']
    assert outcome['response']['predictions'][0]['label'] == 'cat'


def test_503_is_failure_and_is_not_retried(monkeypatch):
    calls = []
    def send(req, timeout):
        calls.append(req)
        raise HTTPError(req.full_url, 503, 'Unavailable', {}, io.BytesIO(b'{"error":"Queue full"}'))
    monkeypatch.setattr(maas.request, 'urlopen', send)
    outcome = maas.infer(maas.payload('Bronze', 200))
    assert len(calls) == 1 and outcome['client_sla_failure']
    assert outcome['http_status'] == 503 and outcome['response']['error'] == 'Queue full'


def test_late_completed_request_remains_sla_failure(monkeypatch):
    class Response(io.BytesIO):
        code = 200
    monkeypatch.setattr(maas.request, 'urlopen', lambda *a, **kw: Response(b'{}'))
    times = iter([1., 1.3])
    monkeypatch.setattr(maas.time, 'perf_counter', lambda: next(times))
    outcome = maas.infer(maas.payload('Gold', 200))
    assert outcome['http_status'] == 200 and outcome['client_sla_failure']


def test_non_json_http_error_is_visible(monkeypatch):
    def send(req, timeout):
        raise HTTPError(req.full_url, 400, 'Bad request', {}, io.BytesIO(b'<html>Invalid image</html>'))
    monkeypatch.setattr(maas.request, 'urlopen', send)
    outcome = maas.infer(maas.payload('Gold', 200))
    assert outcome['http_status'] == 400 and 'without a JSON' in outcome['response']['error']
