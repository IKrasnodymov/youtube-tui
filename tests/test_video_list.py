from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult

from youtube_tui.models import Video
from youtube_tui.widgets.video_list import VideoList


def _video(index: int) -> Video:
    return Video(id=str(index), title=f"Video {index}", channel_name="Channel")


def test_video_list_virtualizes_mounted_cards() -> None:
    class TestApp(App[None]):
        CSS = "TestApp { layout: vertical; } VideoList { height: 1fr; }"

        def compose(self) -> ComposeResult:
            self.video_list = VideoList()
            yield self.video_list

        async def on_mount(self) -> None:
            self.video_list.set_videos(_video(i) for i in range(300))

            assert len(self.video_list.videos) == 300
            assert len(self.video_list._cards) <= self.video_list.MAX_WINDOW_CARDS
            assert 0 in self.video_list._cards

            self.video_list.action_cursor_end()
            assert self.video_list.current() == _video(299)
            assert 299 in self.video_list._cards
            assert len(self.video_list._cards) <= self.video_list.MAX_WINDOW_CARDS

            self.video_list.action_cursor_home()
            assert self.video_list.current() == _video(0)
            assert 0 in self.video_list._cards
            assert len(self.video_list._cards) <= self.video_list.MAX_WINDOW_CARDS
            self.exit()

    async def run() -> None:
        async with TestApp().run_test():
            pass

    asyncio.run(run())
