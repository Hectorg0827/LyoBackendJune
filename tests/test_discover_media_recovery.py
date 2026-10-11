import io
from pathlib import Path
from types import SimpleNamespace

import httpx
from botocore.exceptions import ClientError
from botocore.response import StreamingBody

from scripts.discover_media_recovery import recover_object

PATH = '/api/v1/media/file/clips/' + 'a' * 32 + '.mp4'


class Cloud:
    def __init__(self, existing=False):
        self.existing = existing
        self.uploads = []
        self.body = None

    def head_object(self, **_kwargs):
        if not self.existing:
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')

    def upload_file(self, path, bucket, key, ExtraArgs):
        self.uploads.append((bucket, key, ExtraArgs, Path(path).read_bytes()))

    def get_object(self, **_kwargs):
        self.body = io.BytesIO(self.uploads[0][3])
        return {'Body': StreamingBody(self.body, len(self.uploads[0][3]))}


def test_recovery_preserves_original_key_verifies_bytes_and_never_fetches_record_host():
    requested = []
    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b'original-video', headers={'content-type': 'video/mp4'})
    cloud = Cloud()
    with httpx.Client(transport=httpx.MockTransport(handler)) as source:
        result = recover_object('https://malicious.invalid' + PATH, 'bucket', cloud, source)
    assert requested == ['https://api.lyoai.app' + PATH]
    assert result['status'] == 'recovered'
    assert cloud.uploads == [('bucket', 'media/clips/' + 'a'*32 + '.mp4', {'ContentType': 'video/mp4'}, b'original-video')]
    assert cloud.body.closed


def test_missing_original_is_reported_without_publishing_substitute_bytes():
    cloud = Cloud()
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as source:
        result = recover_object('https://api.lyoai.app' + PATH, 'bucket', cloud, source)
    assert result['status'] == 'original_missing'
    assert not cloud.uploads


def test_existing_durable_objects_are_not_overwritten_and_other_paths_are_skipped():
    cloud = Cloud(existing=True)
    def no_network(_):
        raise AssertionError('unnecessary or arbitrary source request')
    with httpx.Client(transport=httpx.MockTransport(no_network)) as source:
        assert recover_object('https://api.lyoai.app' + PATH, 'bucket', cloud, source)['status'] == 'already_durable'
        assert recover_object('https://elsewhere.invalid/private.mp4', 'bucket', cloud, source)['status'] == 'external_or_other_path'
    assert not cloud.uploads
