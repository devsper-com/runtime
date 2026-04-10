import textwrap
from pathlib import Path
import pytest

from devsper.workspace.context import WorkspaceContext


@pytest.fixture
def git_project(tmp_path):
    """A directory with a .git folder."""
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture
def md_project(tmp_path):
    """A directory with devsper.md."""
    md = tmp_path / "devsper.md"
    md.write_text("# My Project\n\nDo things.\n")
    return tmp_path


def test_discovers_git_root(git_project):
    subdir = git_project / "src" / "pkg"
    subdir.mkdir(parents=True)
    ctx = WorkspaceContext.discover(subdir)
    assert ctx.project_root == git_project


def test_devsper_md_root_takes_priority(tmp_path):
    """If both .git and devsper.md exist, devsper.md location wins (it can be nested)."""
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "devsper.md").write_text("# Sub Project\n")
    ctx = WorkspaceContext.discover(sub)
    assert ctx.project_root == sub
    assert ctx.md_content == "# Sub Project\n"


def test_md_content_loaded(md_project):
    ctx = WorkspaceContext.discover(md_project)
    assert ctx.md_content == "# My Project\n\nDo things.\n"


def test_bare_directory_fallback(tmp_path):
    ctx = WorkspaceContext.discover(tmp_path)
    assert ctx.project_root == tmp_path


def test_project_id_is_consistent(git_project):
    ctx1 = WorkspaceContext.discover(git_project)
    ctx2 = WorkspaceContext.discover(git_project)
    assert ctx1.project_id == ctx2.project_id
    assert len(ctx1.project_id) == 16  # sha256[:16]


def test_project_name_is_dir_name(git_project):
    ctx = WorkspaceContext.discover(git_project)
    assert ctx.project_name == git_project.name


def test_storage_dir_is_under_user_data(git_project):
    ctx = WorkspaceContext.discover(git_project)
    assert ctx.storage_dir.parts[-3] == "devsper"
    assert ctx.storage_dir.parts[-2] == "projects"
    assert ctx.storage_dir.name == ctx.project_id
