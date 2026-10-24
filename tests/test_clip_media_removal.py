"""Removing a Discover video moves its object out of the served prefix in the bucket.

/api/v1/media/file streams media/<folder>/<name>; a removed file moves to
removed/<folder>/<name>, which nothing serves, and a restore moves it back.
"""
from botocore.exceptions import ClientError

from lyo_app.routers import clip_media_storage as media


class FakeS3:
    def __init__(self, keys):
        self.objects = {key: b"bytes" for key in keys}
        self.calls = []
        self.fail_deletes = set()

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def copy_object(self, Bucket, Key, CopySource):
        self.calls.append(("copy", CopySource["Key"], Key))
        self.objects[Key] = self.objects[CopySource["Key"]]

    def delete_object(self, Bucket, Key):
        self.calls.append(("delete", Key))
        if Key in self.fail_deletes:
            self.fail_deletes.discard(Key)
            raise ClientError({"Error": {"Code": "500"}}, "DeleteObject")
        self.objects.pop(Key, None)


def use(monkeypatch, s3):
    monkeypatch.setattr(media, "_provider", lambda: ("s3", "lyo-media"))
    monkeypatch.setattr(media, "_s3_client", lambda provider: s3)


def test_remove_and_restore_move_the_object_and_repeat_safely(monkeypatch, tmp_path):
    s3 = FakeS3({"media/clips/a.mp4"})
    use(monkeypatch, s3)
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "a.mp4").write_bytes(b"left by the upload")

    assert media.set_media_removed("clips", "a.mp4", tmp_path, True)
    assert set(s3.objects) == {"removed/clips/a.mp4"}
    assert not (tmp_path / "clips" / "a.mp4").exists(), "the container's copy would still be served"
    assert media.set_media_removed("clips", "a.mp4", tmp_path, True), "removing twice is a no-op"
    assert len(s3.calls) == 2

    assert media.set_media_removed("clips", "a.mp4", tmp_path, False)
    assert set(s3.objects) == {"media/clips/a.mp4"}
    assert not media.set_media_removed("clips", "missing.mp4", tmp_path, True)


def test_delete_removes_the_object_wherever_it_is(monkeypatch, tmp_path):
    s3 = FakeS3({"removed/clips/a.mp4", "media/clip_thumbnails/p.jpg"})
    use(monkeypatch, s3)
    media.delete_media("clips", "a.mp4", tmp_path)
    media.delete_media("clip_thumbnails", "p.jpg", tmp_path)
    assert s3.objects == {}


def test_a_move_that_cannot_delete_the_original_leaves_one_copy(monkeypatch, tmp_path):
    s3 = FakeS3({"removed/clips/a.mp4"})
    use(monkeypatch, s3)
    s3.fail_deletes = {"removed/clips/a.mp4"}
    try:
        media.set_media_removed("clips", "a.mp4", tmp_path, False)
    except ClientError:
        pass
    else:
        raise AssertionError("the failed delete must surface")
    assert set(s3.objects) == {"removed/clips/a.mp4"}, "a removed video must not also be public"
