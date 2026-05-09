import os, asyncio, pytest
from youtube_tui.playback.mpv_process import is_mpv_available, supports_in_terminal_video, _build_args  # type: ignore[attr-defined]
from youtube_tui.models import PlaybackMode
from pathlib import Path

def test_supports_in_terminal_video_for_kitty(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-kitty")
    assert supports_in_terminal_video() is True

def test_supports_in_terminal_video_for_dumb(monkeypatch):
    monkeypatch.setenv("TERM", "dumb")
    assert supports_in_terminal_video() is False

def test_build_args_external_includes_url():
    args = _build_args("https://example.com/watch", PlaybackMode.EXTERNAL, Path("/tmp/x.sock"))
    assert "mpv" == args[0]
    assert "https://example.com/watch" in args
    assert any(a.startswith("--ytdl-format=") for a in args)
    assert any(a.startswith("--input-ipc-server=") for a in args)

def test_build_args_audio_has_no_video():
    args = _build_args("u", PlaybackMode.AUDIO_ONLY, Path("/tmp/x.sock"))
    assert "--no-video" in args

def test_build_args_kitty_uses_kitty_vo():
    args = _build_args("u", PlaybackMode.IN_TERMINAL, Path("/tmp/x.sock"))
    assert "--vo=kitty" in args
