from pathlib import Path

from core.scanner import ScanCancelled, fast_scan, find_duplicates, smart_output


def test_basic_scan(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("world")

    result = fast_scan(str(tmp_path), exclude_rules=[])

    assert result.file_count == 2
    assert {f.relative_path for f in result.files} == {"a.txt", "sub/b.txt"}


def test_default_excludes_are_pruned(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("js")
    (tmp_path / "real.txt").write_text("real")

    result = fast_scan(str(tmp_path), exclude_rules=[])

    assert [f.relative_path for f in result.files] == ["real.txt"]


def test_user_exclude_glob_and_directory(tmp_path):
    (tmp_path / "notes.tmp").write_text("temp")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "data.bin").write_text("x")
    (tmp_path / "doc.txt").write_text("doc")

    result = fast_scan(str(tmp_path), exclude_rules=["*.tmp", "cache/"])

    assert {f.relative_path for f in result.files} == {"doc.txt"}


def test_duplicates_ignore_empty_files(tmp_path):
    (tmp_path / "a.txt").write_text("same")
    (tmp_path / "b.txt").write_text("same")
    (tmp_path / "e1.txt").write_text("")
    (tmp_path / "e2.txt").write_text("")

    result = fast_scan(str(tmp_path), exclude_rules=[])
    duplicates = find_duplicates(result.files)

    assert len(duplicates) == 1
    assert {f.name for f in duplicates[0].files} == {"a.txt", "b.txt"}


def test_smart_output_modes(tmp_path):
    prompt = "Organize this:\n{file_list}"
    small = fast_scan(str(tmp_path), exclude_rules=[], _override_count=5)
    export = fast_scan(str(tmp_path), exclude_rules=[], _override_count=600)

    assert smart_output(small, str(tmp_path), prompt)["action"] == "copy"
    exported = smart_output(export, str(tmp_path), prompt)
    assert exported["action"] == "export"
    assert exported["export_path"].endswith(".md")


def test_smart_output_exports_when_content_is_too_large(tmp_path):
    for index in range(3):
        (tmp_path / f"{'long-name-' * 12}{index}.txt").write_text("hello")
    scan = fast_scan(str(tmp_path), exclude_rules=[])
    template = "Prompt\n{file_list}\n" + ("extra text\n" * 12000)

    result = smart_output(scan, str(tmp_path), template)

    assert result["action"] == "export"
    assert Path(result["export_path"]).exists()


def test_fast_scan_reports_progress_and_can_cancel(tmp_path):
    for index in range(150):
        (tmp_path / f"file-{index}.txt").write_text("x")
    counts = []

    def on_progress(count, current_path=None):
        counts.append(count)

    def should_cancel():
        return counts and counts[-1] >= 100

    try:
        fast_scan(str(tmp_path), [], progress_callback=on_progress, should_cancel=should_cancel)
    except ScanCancelled:
        pass
    else:
        raise AssertionError("scan should have been cancelled")

    assert counts
    assert counts[-1] >= 100
