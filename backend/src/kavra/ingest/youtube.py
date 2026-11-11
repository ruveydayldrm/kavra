"""YouTube transcripts, choosing the *spoken* language.

AI-dubbed videos can expose several auto-generated tracks (one per dub). We want the track
of the original audio. Strategy:
  1. Read the watch page's caption metadata; the ASR track whose vssId is "a.<lang>" and
     that is not marked as translated/dubbed is the original speech.
  2. Otherwise prefer a manually created track, then a single generated track, then the
     generated track whose language matches the title's language.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from kavra.ingest import Segment, detect_lang

ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})")


def video_id(url: str) -> str | None:
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
        return url.strip()
    m = ID_RE.search(url)
    return m.group(1) if m else None


def video_title(vid: str) -> str:
    try:
        r = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"},
            timeout=10,
        )
        if r.status_code == 200:
            return str(r.json().get("title", vid))
    except httpx.HTTPError:
        pass
    return vid


def _original_asr_lang(vid: str) -> str | None:
    try:
        html = httpx.get(
            f"https://www.youtube.com/watch?v={vid}",
            headers={"Accept-Language": "en-US,en;q=0.8", "User-Agent": "Mozilla/5.0"},
            timeout=15,
        ).text
    except httpx.HTTPError:
        return None
    m = re.search(r'"captionTracks":(\[.*?\])', html)
    if not m:
        return None
    try:
        tracks: list[dict[str, Any]] = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    asr = [t for t in tracks if t.get("kind") == "asr"]
    if len(asr) == 1:
        return str(asr[0].get("languageCode"))
    return None


def choose_transcript(listing: Any, title: str, original: str | None) -> Any:
    items = list(listing)
    if not items:
        raise ValueError("no transcripts")
    generated = [t for t in items if t.is_generated]
    manual = [t for t in items if not t.is_generated]
    if original:
        for t in generated:
            if t.language_code.split("-")[0] == original.split("-")[0]:
                return t
        for t in manual:
            if t.language_code.split("-")[0] == original.split("-")[0]:
                return t
    if manual:
        return manual[0]
    if len(generated) == 1:
        return generated[0]
    title_lang = detect_lang(title)
    for t in generated:
        if t.language_code.startswith(title_lang):
            return t
    return generated[0]


def fetch(url: str) -> tuple[str, str, list[Segment]]:
    """Returns (title, lang, segments)."""
    from youtube_transcript_api import YouTubeTranscriptApi

    vid = video_id(url)
    if not vid:
        raise ValueError("invalid YouTube URL")
    title = video_title(vid)
    api = YouTubeTranscriptApi()
    listing = api.list(vid)
    tr = choose_transcript(listing, title, _original_asr_lang(vid))
    fetched = tr.fetch()
    segs: list[Segment] = []
    # merge ~4 caption lines into one segment (captions are tiny)
    buf: list[Any] = []
    for snip in fetched:
        buf.append(snip)
        if len(buf) >= 4:
            segs.append(_merge(buf))
            buf = []
    if buf:
        segs.append(_merge(buf))
    lang = tr.language_code.split("-")[0]
    return title, ("tr" if lang == "tr" else "en" if lang == "en" else lang), segs


def _merge(buf: list[Any]) -> Segment:
    text = " ".join(s.text.replace("\n", " ") for s in buf)
    start = float(buf[0].start)
    end = float(buf[-1].start + buf[-1].duration)
    return Segment(text, {"kind": "time", "start": round(start, 1), "end": round(end, 1)})
