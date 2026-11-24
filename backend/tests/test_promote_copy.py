"""The copy bake refuses a key the catalog does not hold (#3165)."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import promote_copy  # noqa: E402  (needs the sys.path line above)


def test_script_self_check_passes() -> None:
    promote_copy._check()


def _file_with(monkeypatch, lines: list[dict], answer: dict) -> dict:
    import io
    import json

    sent: dict = {}

    def fake_urlopen(request, timeout):
        sent.update(json.loads(request.data))
        return io.BytesIO(json.dumps(answer).encode())

    monkeypatch.setenv("COPY_PROPOSAL_TOKEN", "t")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.setenv("PR_URL", "https://github.com/o/r/pull/7")
    monkeypatch.setattr(promote_copy.urllib.request, "urlopen", fake_urlopen)
    promote_copy._file_proposal(lines)
    return sent


def test_no_hits_withdraws_the_proposal(monkeypatch, capsys) -> None:
    sent = _file_with(monkeypatch, [], {"pushed": False})
    assert sent["lines"] == []
    assert "withdrew" in capsys.readouterr().out


def test_pushed_is_claimed_only_when_the_server_says_so(monkeypatch, capsys) -> None:
    line = {"ns": "x", "key": "a", "owner_value": "o", "proposed_value": "p"}
    _file_with(monkeypatch, [line], {"pushed": False})
    assert "pushed" not in capsys.readouterr().out
    _file_with(monkeypatch, [line], {"pushed": True})
    assert "the owner has been pushed" in capsys.readouterr().out
