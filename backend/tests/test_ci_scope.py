"""scripts/ci_scope.sh picks the widest scope a PR's files need."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ci_scope.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo, check=True, capture_output=True,
    )


def _scope(repo: Path, base: dict[str, str], change: Callable[[Path], None]) -> str:
    """Commit `base`, apply `change`, commit it, and run the script on HEAD."""
    for name, text in base.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    change(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "pr", "--allow-empty")
    out = subprocess.run(
        ["bash", str(SCRIPT)], cwd=repo, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("frontend/src/locales/en/common.json", "copy"),
        ("frontend/src/App.tsx", "frontend"),
        (".github/dependabot.yml", "ci"),
        (".github/workflows/test.yml", "full"),
        ("backend/main.py", "full"),
    ],
)
def test_scope_by_path(tmp_path: Path, path: str, expected: str) -> None:
    def change(repo: Path) -> None:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("changed")

    assert _scope(tmp_path, {"README.md": "x"}, change) == expected


def test_rename_backend_to_frontend_is_full(tmp_path: Path) -> None:
    def rename(repo: Path) -> None:
        (repo / "frontend").mkdir()
        _git(repo, "mv", "backend/x.py", "frontend/x.py")

    assert _scope(tmp_path, {"backend/x.py": "same"}, rename) == "full"


def test_empty_diff_is_full(tmp_path: Path) -> None:
    assert _scope(tmp_path, {"README.md": "x"}, lambda repo: None) == "full"
