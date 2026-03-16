"""Tests for filesystem tools."""

import tempfile
from pathlib import Path

import pytest

from devsper.tools.filesystem.read_file import ReadFileTool
from devsper.tools.filesystem.write_file import WriteFileTool
from devsper.tools.filesystem.append_file import AppendFileTool
from devsper.tools.filesystem.list_directory import ListDirectoryTool
from devsper.tools.filesystem.search_files import SearchFilesTool
from devsper.tools.filesystem.find_large_files import FindLargeFilesTool
from devsper.tools.filesystem.file_metadata import FileMetadataTool
from devsper.tools.filesystem.file_hash import FileHashTool
from devsper.tools.filesystem.file_line_count import FileLineCountTool
from devsper.tools.filesystem.file_preview import FilePreviewTool


def test_read_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello world")
        path = f.name
    try:
        out = ReadFileTool().run(path=path)
        assert "hello" in out
    finally:
        Path(path).unlink(missing_ok=True)


def test_read_file_not_found():
    out = ReadFileTool().run(path="/nonexistent/file/xyz")
    assert "not found" in out.lower() or "error" in out.lower()


def test_write_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "out.txt"
        out = WriteFileTool().run(path=str(path), content="written")
        assert "Wrote" in out or "written" in out
        assert path.read_text() == "written"


def test_append_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "out.txt"
        path.write_text("a")
        out = AppendFileTool().run(path=str(path), content="b")
        assert path.read_text() == "ab"


def test_list_directory():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.txt").write_text("")
        (Path(d) / "sub").mkdir()
        out = ListDirectoryTool().run(path=d)
        assert "a.txt" in out and "sub" in out


def test_search_files():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "foo.py").write_text("")
        (Path(d) / "bar.py").write_text("")
        out = SearchFilesTool().run(path=d, pattern="*.py")
        assert "foo.py" in out and "bar.py" in out


def test_find_large_files():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "big"
        p.write_bytes(b"x" * 2000)
        out = FindLargeFilesTool().run(path=d, min_size=1000)
        assert "2000" in out or "big" in out


def test_file_metadata():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        path = f.name
    try:
        out = FileMetadataTool().run(path=path)
        assert "file" in out.lower() and "size" in out.lower()
    finally:
        Path(path).unlink(missing_ok=True)


def test_file_hash():
    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
        f.write(b"hello")
        path = f.name
    try:
        out = FileHashTool().run(path=path)
        assert len(out) == 64 and all(c in "0123456789abcdef" for c in out)
    finally:
        Path(path).unlink(missing_ok=True)


def test_file_line_count():
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("a\nb\nc\n")
        path = f.name
    try:
        out = FileLineCountTool().run(path=path)
        assert out == "3"
    finally:
        Path(path).unlink(missing_ok=True)


def test_file_preview():
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("line1\nline2\nline3\n")
        path = f.name
    try:
        out = FilePreviewTool().run(path=path, lines=2)
        assert "line1" in out and "line2" in out
    finally:
        Path(path).unlink(missing_ok=True)
