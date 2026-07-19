from typer.testing import CliRunner

from reporadio import __version__
from reporadio.cli import app
from reporadio.config import MissingGroqKeyError, Settings, require_groq_key

runner = CliRunner()


def test_version_string():
    assert __version__


def test_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "RepoRadio" in result.output


def test_tour_help_wired():
    result = runner.invoke(app, ["tour", "--help"])
    assert result.exit_code == 0
    assert "--mute" in result.output


def _no_key(monkeypatch):
    from reporadio import config

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(
        config, "get_settings", lambda: Settings(groq_api_key="", _env_file=None)
    )


def test_tour_without_key_is_friendly(monkeypatch):
    _no_key(monkeypatch)
    result = runner.invoke(app, ["tour", "https://github.com/pallets/flask"])
    assert result.exit_code == 1
    assert "GROQ_API_KEY" in result.output


def test_groq_key_is_lazy(monkeypatch):
    _no_key(monkeypatch)
    try:
        require_groq_key()
    except MissingGroqKeyError as err:
        assert "GROQ_API_KEY" in str(err)
    else:  # pragma: no cover
        raise AssertionError("expected MissingGroqKeyError")
