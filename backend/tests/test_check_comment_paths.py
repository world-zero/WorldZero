"""Guard for scripts/check_comment_paths.py (#4101): missing paths fail, allowlisted ones pass."""

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_comment_paths as ccp  # noqa: E402


def _repo(tmp_path):
    (tmp_path / "frontend/src").mkdir(parents=True)
    (tmp_path / "frontend/src/a.ts").write_text(
        "const x = 1;\n// see frontend/src/does/not/exist.css\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return tmp_path


def test_missing_path_fails_with_file_and_line(tmp_path, capsys):
    root = _repo(tmp_path)
    assert ccp.main(root, root / "allow.txt") == 1
    err = capsys.readouterr().err
    assert "frontend/src/a.ts:2" in err and "frontend/src/does/not/exist.css" in err


def test_allowlisted_entry_passes(tmp_path):
    root = _repo(tmp_path)
    (root / "allow.txt").write_text("frontend/src/a.ts:frontend/src/does/not/exist.css\n")
    assert ccp.main(root, root / "allow.txt") == 0
