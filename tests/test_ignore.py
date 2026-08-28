"""Exclusions: .gandalfignore, --exclude, and the matching they share.

Run: pytest tests/test_ignore.py
"""

from __future__ import annotations

import subprocess

import pytest

from gandalf import plugins, scope
from gandalf.base import GateContext
from gandalf.gates._toolchain import named
from gandalf.plugins import _scan_targets, ignore_patterns, is_ignored, scannable_files


@pytest.fixture(autouse=True)
def _clean_process_state():
    """--exclude is process state and the lookups are cached per workdir, so a
    test must not inherit what the last one set."""
    plugins.set_extra_ignores([])
    plugins.tracked_files.cache_clear()
    yield
    plugins.set_extra_ignores([])
    plugins.tracked_files.cache_clear()


# --- matching -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        # A bare name skips that directory wherever it appears.
        ("node_modules/react/index.js", "node_modules", True),
        ("web/node_modules/react/index.js", "node_modules", True),
        ("node_modules", "node_modules", True),
        # ...but only that name, not one that merely starts with it.
        ("node_modules_old/a.js", "node_modules", False),
        ("src/node_modulesish.py", "node_modules", False),
        # A path anchors at the repo root.
        ("src/generated/api.py", "src/generated", True),
        ("lib/src/generated/api.py", "src/generated", False),
        # Globs work, on the whole path or the basename.
        ("web/static/app.min.js", "*.min.js", True),
        ("web/static/app.js", "*.min.js", False),
        ("vendor/jquery/dist/a.js", "vendor/*", True),
        # A basename anywhere.
        (".env", ".env", True),
        ("config/.env", ".env", True),
        # Trailing slashes and ./ prefixes are tolerated on both sides.
        ("data/dump.sql", "data/", True),
        ("./data/dump.sql", "data", True),
        ("data/dump.sql", "./data", True),
        # Windows separators.
        ("src\\generated\\api.py", "src/generated", True),
        # Nothing matches nothing.
        ("src/app.py", "", False),
        ("", "node_modules", False),
    ],
)
def test_is_ignored(path, pattern, expected):
    assert is_ignored(path, (pattern,)) is expected


def test_is_ignored_takes_any_matching_pattern():
    pats = ("dist", "*.min.js", "src/generated")
    assert is_ignored("src/generated/x.py", pats)
    assert is_ignored("a/dist/b.css", pats)
    assert not is_ignored("src/app.py", pats)


# --- where the patterns come from ---------------------------------------------


def _repo(tmp_path, files, gandalfignore=None):
    repo = tmp_path / "repo"
    repo.mkdir()
    for rel in files:
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x = 1\n")
    if gandalfignore is not None:
        (repo / ".gandalfignore").write_text(gandalfignore)
    git = ["git", "-c", "user.email=t@e.com", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q", "."], cwd=repo, check=True)
    subprocess.run([*git, "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [*git, "-c", "commit.gpgsign=false", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
    )
    return repo


def test_defaults_and_gandalfignore_and_exclude_all_land_in_one_list(tmp_path):
    repo = _repo(tmp_path, ["src/app.py"], gandalfignore="# comment\ndata/\n\n")
    plugins.set_extra_ignores(["*.min.js", "  "])

    pats = ignore_patterns(str(repo))
    assert "node_modules" in pats, "built-in defaults survive"
    assert "data/" in pats, "read from .gandalfignore"
    assert "*.min.js" in pats, "passed to --exclude"
    assert "  " not in pats and "" not in pats, "blank patterns are dropped"


def test_exclusions_narrow_what_every_gate_scans(tmp_path):
    """The point of the change: .gandalfignore used to reach only the handful of
    gates that translate it into their own tool's flag."""
    repo = _repo(
        tmp_path,
        ["src/app.py", "src/generated/api.py", "vendor/lib.py", "web/app.min.js"],
        gandalfignore="src/generated\n",
    )
    ctx = GateContext(repo=str(repo), workdir=str(repo), changed_files=[])

    assert sorted(_scan_targets(ctx)) == [
        ".gandalfignore",
        "src/app.py",
        "vendor/lib.py",
        "web/app.min.js",
    ]

    plugins.set_extra_ignores(["vendor", "*.min.js"])
    assert sorted(_scan_targets(ctx)) == [".gandalfignore", "src/app.py"]


def test_exclusions_apply_to_a_changed_set_too(tmp_path):
    repo = _repo(tmp_path, ["src/app.py", "src/generated/api.py"])
    plugins.set_extra_ignores(["src/generated"])
    ctx = GateContext(
        repo=str(repo),
        workdir=str(repo),
        changed_files=["src/app.py", "src/generated/api.py"],
    )
    assert _scan_targets(ctx) == ["src/app.py"]


def test_scannable_files_is_recomputed_when_the_exclusions_change(tmp_path):
    repo = _repo(tmp_path, ["src/app.py", "vendor/lib.py"])
    assert "vendor/lib.py" in scannable_files(str(repo))

    plugins.set_extra_ignores(["vendor"])
    assert "vendor/lib.py" not in scannable_files(str(repo)), "cache was stale"

    plugins.set_extra_ignores([])
    assert "vendor/lib.py" in scannable_files(str(repo))


def test_path_scope_refuses_to_widen_when_everything_under_it_is_excluded(
    tmp_path, monkeypatch
):
    """`--path` on an excluded folder must fail, not fall through to the whole
    tree: an empty changed set means "scan everything" downstream."""
    repo = _repo(tmp_path, ["src/app.py", "generated/api.py"])
    monkeypatch.chdir(repo)
    plugins.set_extra_ignores(["generated"])

    with (
        pytest.raises(SystemExit, match="every path under it is excluded"),
        scope.resolve(None, False, "generated"),
    ):
        pass

    # The same folder without the exclusion narrows normally.
    plugins.set_extra_ignores([])
    with scope.resolve(None, False, "generated") as sc:
        assert sc.changed_files == ["generated/api.py"]


def test_languages_reads_the_same_tracked_listing_every_gate_does(tmp_path):
    """`languages()` used to run its own `git ls-files` and split on whitespace.

    Plain `ls-files` quotes any path git considers unusual (core.quotePath is on
    by default), so a non-ASCII filename came back as `"src/caf\\303\\251.py"` —
    basename `.py"`, no language matched, and every python gate was skipped.
    plugins.tracked_files asks with `-z`, which quotes nothing, and is already
    cached from the run every gate is about to make.
    """
    repo = _repo(tmp_path, ["src/café.py"])
    plugins.set_extra_ignores([])
    plugins.tracked_files.cache_clear()

    assert scope.languages(str(repo), []) == {"python"}


def test_named_skips_what_git_ignores(tmp_path):
    """The gates that used to rglob the working tree (mdl, sqlfluff, squawk,
    shellcheck, yamllint, codespell, hadolint) walked straight into build output
    and everything else .gitignore hides. `named` asks git instead."""
    repo = _repo(tmp_path, ["README.md", "db/schema.sql", "Dockerfile"])
    (repo / ".gitignore").write_text("site/\n")
    (repo / "site").mkdir()
    (repo / "site" / "index.md").write_text("# built\n")
    (repo / "site" / "Dockerfile").write_text("FROM scratch\n")
    plugins.tracked_files.cache_clear()
    ctx = GateContext(repo=str(repo), workdir=str(repo), changed_files=[])

    assert named(ctx, "*.md") == ["README.md"]
    assert named(ctx, "*.sql") == ["db/schema.sql"]
    assert named(ctx, "Dockerfile", "*.dockerfile") == ["Dockerfile"]
