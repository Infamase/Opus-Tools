"""Output paths and cache work dirs never collide between parallel tool calls."""

import threading

from opus.paths import cache_dir, output_path


def test_two_output_paths_in_the_same_second_differ(tmp_path):
    a = output_path("look", "axe", suffix=".jpg", near=tmp_path)
    b = output_path("look", "axe", suffix=".jpg", near=tmp_path)
    assert a != b
    assert a.exists() and b.exists()  # reserved on disk, so a third call can't take either
    assert a.parent == b.parent == tmp_path / ".opus" / "out" / "look"
    assert a.name.startswith("axe_") and a.suffix == b.suffix == ".jpg"


def test_two_cache_dirs_differ(tmp_path):
    a = cache_dir("look", near=tmp_path)
    b = cache_dir("look", near=tmp_path)
    assert a != b
    assert a.is_dir() and b.is_dir()
    assert a.parent == b.parent == tmp_path / ".opus" / "cache" / "look"
    # callers still add their own work folder under it
    assert not any(a.iterdir())


def test_parallel_output_paths_are_distinct(tmp_path):
    got, errors = [], []
    start = threading.Barrier(20)

    def call():
        try:
            start.wait()
            got.append(output_path("readability", "axe", suffix=".jpg", near=tmp_path))
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)

    threads = [threading.Thread(target=call) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(got) == 20 and len(set(got)) == 20
    assert all(p.exists() for p in got)


def test_parallel_cache_dirs_are_distinct(tmp_path):
    got = []
    start = threading.Barrier(20)

    def call():
        start.wait()
        got.append(cache_dir("blind", near=tmp_path))

    threads = [threading.Thread(target=call) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(got)) == 20
