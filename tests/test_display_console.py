import fcntl
import os

import pytest


@pytest.fixture
def console_module(load_source):
    return load_source("display_console", "display/console.py")


@pytest.fixture
def fake_tty(tmp_path, monkeypatch, console_module):
    active = tmp_path / "active"
    active.write_text("tty7\n")
    monkeypatch.setattr(console_module, "ACTIVE_CONSOLE", active)

    dev = tmp_path / "dev"
    dev.mkdir()
    (dev / "tty7").write_text("")
    (dev / "tty1").write_text("")

    def redirect(p):
        return p.replace("/dev/", str(dev) + "/", 1) if p.startswith("/dev/") else p

    real_exists = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda p: real_exists(redirect(p)))
    real_open = os.open
    monkeypatch.setattr(console_module.os, "open", lambda p, flags: real_open(redirect(p), os.O_RDWR))

    calls = []
    monkeypatch.setattr(fcntl, "ioctl", lambda fd, req, arg: calls.append((req, arg)))
    return {"dev": dev, "calls": calls}


def test_acquire_puts_the_active_console_in_graphics_mode(console_module, fake_tty):
    c = console_module.Console()
    assert c.acquire() is True
    assert c.held
    assert fake_tty["calls"] == [(console_module.KDSETMODE, console_module.KD_GRAPHICS)]
    assert c._path.endswith("tty7")


def test_acquire_is_idempotent_and_release_restores_text_mode(console_module, fake_tty):
    c = console_module.Console()
    assert c.acquire() and c.acquire()
    c.release()
    assert not c.held
    assert fake_tty["calls"] == [
        (console_module.KDSETMODE, console_module.KD_GRAPHICS),
        (console_module.KDSETMODE, console_module.KD_TEXT),
    ]
    c.release()
    assert len(fake_tty["calls"]) == 2


def test_falls_back_to_tty1_when_the_active_console_is_unreadable(console_module, fake_tty, monkeypatch):
    monkeypatch.setattr(console_module, "ACTIVE_CONSOLE", fake_tty["dev"] / "missing")
    c = console_module.Console()
    assert c.acquire() is True
    assert c._path.endswith("tty1")


def test_acquire_reports_failure_when_no_console_device_exists(console_module, fake_tty):
    (fake_tty["dev"] / "tty7").unlink()
    (fake_tty["dev"] / "tty1").unlink()
    c = console_module.Console()
    assert c.acquire() is False
    assert not c.held
    assert fake_tty["calls"] == []
