import json

from mockcrowd import update


class Tty:
    def isatty(self):
        return True


def fake_pypi(version, calls):
    def http_json(url, **_):
        calls.append(url)
        return {"info": {"version": version}}
    return http_json


def test_notice_when_newer_and_checks_once_a_day(monkeypatch, isolated_home):
    calls = []
    monkeypatch.setattr(update, "http_json", fake_pypi("99.0.0", calls))
    monkeypatch.setattr(update.sys, "stderr", Tty())
    monkeypatch.delenv("MOCKCROWD_NO_UPDATE_CHECK", raising=False)
    assert "99.0.0 is available" in update.notice(now=1000)
    assert update.notice(now=1000 + 3600)  # cached, no second request
    assert len(calls) == 1
    update.notice(now=1000 + update.DAY + 1)
    assert len(calls) == 2
    assert json.loads((isolated_home / "update.json").read_text())["latest"] == "99.0.0"


def test_silent_when_current_offline_opted_out_or_not_a_terminal(monkeypatch):
    calls = []
    monkeypatch.setattr(update, "http_json", fake_pypi(update.__version__, calls))
    monkeypatch.delenv("MOCKCROWD_NO_UPDATE_CHECK", raising=False)
    assert update.notice() is None  # pytest's stderr is not a terminal
    assert calls == []

    monkeypatch.setattr(update.sys, "stderr", Tty())
    assert update.notice(now=1) is None  # same version

    def offline(*_, **__):
        raise RuntimeError("no network")
    monkeypatch.setattr(update, "http_json", offline)
    assert update.notice(now=1 + update.DAY + 1) is None

    monkeypatch.setattr(update, "http_json", fake_pypi("99.0.0", calls))
    monkeypatch.setenv("MOCKCROWD_NO_UPDATE_CHECK", "1")
    assert update.notice(now=1 + 3 * update.DAY) is None


def test_prereleases_are_ignored():
    assert update._parse("1.0.0rc1") is None
    assert update._parse("0.10.0") > update._parse("0.9.9")
