"""Read the public catalog linked by Divoom's Gallery web page."""

import asyncio
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

from .divoom_client import DeviceError
from .divoom_client.render import MAX_BYTES

PAGE = "https://divoom.com/pages/divoom-gallery"
CACHE_BYTES = 32 * 1024 * 1024


class GalleryError(DeviceError):
    """The public gallery could not supply usable artwork."""


class MissingArtwork(GalleryError):
    """The gallery removed a previously listed file."""


class CatalogPage(HTMLParser):
    catalog_url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "divoom-gallery-v3":
            self.catalog_url = dict(attrs).get("data-fallback") or ""


def catalog_url(html: bytes) -> str:
    page = CatalogPage()
    page.feed(html.decode())
    return public_url(page.catalog_url, PAGE)


def public_url(value: str, base: str) -> str:
    if value.startswith("asset:"):
        value = value.removeprefix("asset:")
    url = urljoin(base, value)
    parts = urlsplit(url)
    if (
        not value
        or parts.scheme != "https"
        or parts.netloc not in ("divoom.com", "cdn.shopify.com")
    ):
        raise GalleryError("Invalid gallery resource")
    return url


@dataclass(frozen=True, slots=True)
class Artwork:
    id: str
    title: str
    artist_id: str
    artist: str
    size: int
    url: str
    thumbnail: str

    @property
    def mime(self) -> str:
        return {
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(PurePosixPath(urlsplit(self.url).path).suffix.lower(), "image/gif")


def parse_catalog(data: bytes, base: str) -> dict[str, Artwork]:
    catalog = json.loads(data)
    if not isinstance(catalog, dict) or not isinstance(catalog.get("works"), list):
        raise GalleryError("Unexpected gallery catalog")
    if not isinstance(catalog.get("artists", []), list):
        raise GalleryError("Unexpected artist catalog")
    names = {
        str(a["id"]): str(a["name"])
        for a in catalog.get("artists", [])
        if isinstance(a, dict) and a.get("id") and a.get("name")
    }
    works = {}
    for row in catalog["works"]:
        if not isinstance(row, dict):
            continue
        key = str(row.get("id", ""))
        artist = str(row.get("authorId", ""))
        if not key.isdecimal() or not artist.isdecimal():
            continue
        try:
            src = public_url(
                str(row.get("gif") or row.get("webp") or row.get("image") or ""), base
            )
            thumb = public_url(str(row.get("png") or row.get("image") or src), base)
            size = int(row.get("canvas") or 0)
        except ValueError, TypeError, GalleryError:
            continue
        works[key] = Artwork(
            key,
            str(row.get("title") or "Untitled"),
            artist,
            names.get(artist, str(row.get("author") or artist)),
            size,
            src,
            thumb,
        )
    if not works:
        raise GalleryError("Gallery has no playable works")
    return works


class Gallery:
    def __init__(self, session: ClientSession) -> None:
        self.session = session
        self._works: dict[str, Artwork] = {}
        self._expires = 0.0
        self._lock = asyncio.Lock()
        self._files: OrderedDict[str, bytes] = OrderedDict()
        self._bytes = 0

    async def fetch(self, url: str, limit: int) -> bytes:
        try:
            async with self.session.get(
                url, allow_redirects=False, timeout=ClientTimeout(total=20)
            ) as response:
                if response.status in (404, 410):
                    raise MissingArtwork("Gallery file unavailable")
                if response.status != 200:
                    raise GalleryError(f"Gallery returned HTTP {response.status}")
                data = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    if len(data) + len(chunk) > limit:
                        raise GalleryError("Gallery response too large")
                    data.extend(chunk)
                return bytes(data)
        except (TimeoutError, ClientError) as exc:
            raise GalleryError("Gallery unreachable") from exc

    async def works(self) -> dict[str, Artwork]:
        async with self._lock:
            if time.monotonic() < self._expires:
                return self._works
            try:
                html = await self.fetch(PAGE, 4 * 1024 * 1024)
                url = await asyncio.to_thread(catalog_url, html)
                raw = await self.fetch(url, 32 * 1024 * 1024)
                self._works = await asyncio.to_thread(parse_catalog, raw, url)
            except (GalleryError, ValueError) as exc:
                if not self._works:
                    raise GalleryError("Cannot load Divoom gallery") from exc
                self._expires = time.monotonic() + 300
            else:
                self._expires = time.monotonic() + 3600
            return self._works

    def cached(self, art: Artwork) -> bool:
        return art.url in self._files

    async def image(self, art: Artwork) -> bytes:
        if art.url in self._files:
            self._files.move_to_end(art.url)
            return self._files[art.url]
        data = await self.fetch(art.url, MAX_BYTES)
        self._bytes -= len(self._files.pop(art.url, b""))
        self._files[art.url] = data
        self._bytes += len(data)
        while self._bytes > CACHE_BYTES:
            _, old = self._files.popitem(last=False)
            self._bytes -= len(old)
        return data
