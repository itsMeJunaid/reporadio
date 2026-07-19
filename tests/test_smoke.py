from typer.testing import CliRunner

from reporadio import __version__
from reporadio.cli import app
from reporadio.config import MissingGroqKeyError, require_groq_key

runner = CliRunner()


def test_version_string():
    assert __version__


def test_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "RepoRadio" in result.output


def test_tour_shows_on_air_banner():
    result = runner.invoke(app, ["tour", "https://github.com/pallets/flask"])
    assert result.exit_code == 0
    assert "ON AIR" in result.output
    assert "pallets/flask" in result.output


def test_groq_key_is_lazy(monkeypatch):
    from reporadio import config

    monkeypatch.setenv("GROQ_API_KEY", "")
    config.get_settings.cache_clear()
    try:
        require_groq_key()
    except MissingGroqKeyError as err:
        assert "GROQ_API_KEY" in str(err)
    else:  # pragma: no cover
        raise AssertionError("expected MissingGroqKeyError")
    finally:
        config.get_settings.cache_clear()
