from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static

from ..data.thumbnails import fetch_thumbnail
from ..models import Video
from ._image import ImageWidget as Image

THUMB_WIDTH_CELLS = 32
THUMB_HEIGHT_CELLS = 9


class VideoCard(Static):
    DEFAULT_CSS = """
    VideoCard {
        height: 11;
        padding: 0 1;
        border-bottom: solid #303030;
        background: $boost;
    }
    VideoCard.-selected {
        background: #2a0a14;
        border-bottom: solid #ff0033;
    }
    VideoCard Horizontal {
        height: 100%;
    }
    VideoCard .thumb-wrap {
        width: 34;
        height: 9;
        content-align: left top;
        padding: 0;
        background: #1a1a1a;
    }
    VideoCard .thumb-wrap Image {
        width: 100%;
        height: 100%;
    }
    VideoCard .info {
        width: 1fr;
        height: 100%;
        padding: 0 1;
    }
    VideoCard .title {
        color: #f1f1f1;
        text-style: bold;
        height: 2;
    }
    VideoCard .channel {
        color: #aaaaaa;
        height: 1;
    }
    VideoCard .meta {
        color: #888888;
        height: 1;
    }
    """

    def __init__(self, video: Video, **kwargs) -> None:
        super().__init__(**kwargs)
        self.video = video

    def compose(self) -> ComposeResult:
        with Horizontal():
            self._wrap = Container(classes="thumb-wrap")
            yield self._wrap
            with Vertical(classes="info"):
                yield Static(self.video.title, classes="title", markup=False)
                yield Static(self.video.channel_name, classes="channel", markup=False)
                yield Static(self._meta_text(), classes="meta")

    def _meta_text(self) -> Text:
        v = self.video
        text = Text()
        if v.is_live:
            text.append(" LIVE ", style="bold white on #ff0033")
            text.append(" ")
        else:
            text.append(v.duration_human, style="bold #f1f1f1")
            text.append(" ")
        if v.views_human:
            text.append("· " + v.views_human + " ", style="#aaaaaa")
        if v.published_at:
            text.append("· " + v.published_at, style="#888888")
        return text

    def on_mount(self) -> None:
        self.run_worker(self._load_thumb(), exclusive=True, group=f"thumb-{self.video.id}")

    async def _load_thumb(self) -> None:
        if not self.video.thumbnail_url:
            return
        path = await fetch_thumbnail(self.video.id, self.video.thumbnail_url)
        if path is None:
            return
        try:
            await self._wrap.mount(Image(str(path)))
        except Exception:
            return


def make_card(video: Video) -> VideoCard:
    return VideoCard(video)
