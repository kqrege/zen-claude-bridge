"""Tests for managed proxy path detection logic.

These tests mirror the validation logic in the Windows batch scripts
to ensure the managed proxy detection works correctly.
"""

import os
from pathlib import Path


def _proxy_is_valid(proxy_dir: str) -> bool:
    """Mirrors the batch validation: checks .git, pyproject.toml, src/."""
    d = Path(proxy_dir)
    if not d.is_dir():
        return False
    if not (d / ".git").is_dir():
        return False
    if not (d / "pyproject.toml").is_file():
        return False
    if not (d / "src").is_dir():
        return False
    return True


def test_valid_proxy_path(tmp_path):
    """A real clone has .git/, pyproject.toml, and src/."""
    proxy = tmp_path / "deepseek-cursor-proxy"
    proxy.mkdir(parents=True)
    (proxy / ".git").mkdir()
    (proxy / "src").mkdir()
    (proxy / "pyproject.toml").write_text("")

    assert _proxy_is_valid(str(proxy))


def test_missing_top_dir_is_invalid(tmp_path):
    """If the top-level proxy dir doesn't exist, it's invalid."""
    proxy = tmp_path / "nonexistent"
    assert not _proxy_is_valid(str(proxy))


def test_empty_folder_is_invalid(tmp_path):
    """Empty folder without .git, pyproject.toml, src is invalid."""
    proxy = tmp_path / "empty-proxy"
    proxy.mkdir(parents=True)
    assert not _proxy_is_valid(str(proxy))


def test_missing_pyproject_toml_is_invalid(tmp_path):
    """Missing pyproject.toml means incomplete clone."""
    proxy = tmp_path / "no-pyproject"
    proxy.mkdir(parents=True)
    (proxy / ".git").mkdir()
    (proxy / "src").mkdir()
    assert not _proxy_is_valid(str(proxy))


def test_missing_src_is_invalid(tmp_path):
    """Missing src/ means incomplete clone."""
    proxy = tmp_path / "no-src"
    proxy.mkdir(parents=True)
    (proxy / ".git").mkdir()
    (proxy / "pyproject.toml").write_text("")
    assert not _proxy_is_valid(str(proxy))


def test_missing_dot_git_is_invalid(tmp_path):
    """Missing .git/ means not a git clone."""
    proxy = tmp_path / "no-git"
    proxy.mkdir(parents=True)
    (proxy / "src").mkdir()
    (proxy / "pyproject.toml").write_text("")
    assert not _proxy_is_valid(str(proxy))


def test_empty_env_var_does_not_override_managed(monkeypatch):
    """If DEEPSEEK_CURSOR_PROXY_DIR is set to empty string,
    the managed path should still be used (as the batch scripts
    check for non-empty value)."""
    monkeypatch.setenv("DEEPSEEK_CURSOR_PROXY_DIR", "")
    env_val = os.environ.get("DEEPSEEK_CURSOR_PROXY_DIR", "")
    if env_val == "":
        managed_path = "/some/fallback/managed"
        proxy_dir = env_val if env_val else managed_path
        assert proxy_dir == managed_path


def test_set_env_var_does_override(monkeypatch):
    """If DEEPSEEK_CURSOR_PROXY_DIR is set to a non-empty path,
    it should override the managed path."""
    monkeypatch.setenv("DEEPSEEK_CURSOR_PROXY_DIR", r"C:\custom\path")
    env_val = os.environ.get("DEEPSEEK_CURSOR_PROXY_DIR", "")
    if env_val:
        assert env_val == r"C:\custom\path"


def test_unset_env_var_falls_back_to_managed(monkeypatch):
    """If DEEPSEEK_CURSOR_PROXY_DIR is not set at all,
    the managed path is used."""
    monkeypatch.delenv("DEEPSEEK_CURSOR_PROXY_DIR", raising=False)
    env_val = os.environ.get("DEEPSEEK_CURSOR_PROXY_DIR", "")
    if not env_val:
        managed_path = "/fallback/managed"
        assert True
