#!/usr/bin/env python3
"""Typed Nyaa transport and parsing adapter used by the release selector."""

from __future__ import annotations

import gzip
import html
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Callable, Literal


NYAA_BASE_URL = "https://nyaa.si/"
NYAA_NS = "{https://nyaa.si/xmlns/nyaa}"
USER_AGENT = "CodexSkill/1.2 (+https://nyaa.si/)"


class NyaaClientError(RuntimeError):
    """Base class for stable Nyaa adapter failures."""

    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message)
        self.url = url


class NyaaNetworkError(NyaaClientError):
    """The Nyaa request could not complete successfully."""


class NyaaNotFoundError(NyaaNetworkError):
    """The requested Nyaa release does not exist."""


class NyaaParseError(NyaaClientError):
    """A Nyaa response completed but did not match the expected structure."""


@dataclass(frozen=True)
class NyaaSearchRequest:
    query: str = ""
    category: str = "1_0"
    nyaa_filter: str = "0"
    page: int = 1
    timeout: float = 20
    source: Literal["rss", "listing"] = "rss"
    sort: str = "id"
    order: str = "desc"


@dataclass(frozen=True)
class NyaaRelease:
    nyaa_id: str
    title: str
    category: str | None
    size: str | None
    size_bytes: int | None
    published: str | None
    published_at: int | None
    seeders: int
    leechers: int
    downloads: int
    url: str
    info_hash: str | None = None
    magnet: str | None = None


@dataclass(frozen=True)
class NyaaFileEntry:
    name: str
    size: str
    size_bytes: int | None


@dataclass(frozen=True)
class NyaaReleaseDetail:
    release: NyaaRelease
    description: str
    files: tuple[NyaaFileEntry, ...]


def as_int(value: Any) -> int:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def parse_size(value: str) -> int | None:
    if not value:
        return None
    match = re.search(r"([\d.]+)\s*([kmgt]i?b)", value, re.I)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower()
    powers = {"kb": 1, "kib": 1, "mb": 2, "mib": 2, "gb": 3, "gib": 3, "tb": 4, "tib": 4}
    base = 1024 if "i" in unit else 1000
    return int(amount * (base ** powers[unit]))


def nyaa_id_from_url(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if stripped.isdigit():
        return stripped
    match = re.search(r"nyaa\.si/(?:view|download)/(\d+)(?:\.torrent)?", stripped)
    return match.group(1) if match else None


def view_url(nyaa_id: str) -> str:
    return urllib.parse.urljoin(NYAA_BASE_URL, f"view/{nyaa_id}")


def download_url(nyaa_id: str) -> str:
    return urllib.parse.urljoin(NYAA_BASE_URL, f"download/{nyaa_id}.torrent")


def magnet_from_hash(info_hash: str | None, title: str) -> str | None:
    if not info_hash:
        return None
    return "magnet:?xt=urn:btih:{}&dn={}".format(info_hash, urllib.parse.quote(title))


def strip_html_to_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</(?:p|div|li|tr|h\d)>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(re.sub(r"[ \t]+", " ", value)).replace("\r", "")


def extract_description(page_html: str) -> str:
    """Extract title, description, and file-list text used as release evidence."""
    patterns = (
        r"<h3[^>]*class=[\"'][^\"']*panel-title[^\"']*[\"'][^>]*>(.*?)</h3>",
        r"<div[^>]+id=[\"']torrent-description[\"'][^>]*>(.*?)</div>",
        r"<div[^>]+class=[\"'][^\"']*torrent-file-list[^\"']*[\"'][^>]*>(.*?)</div>",
    )
    fragments: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, page_html, re.I | re.S)
        if match:
            fragments.append(match.group(1))
    return strip_html_to_text("\n".join(fragments) if fragments else page_html)


def decode_http_payload(payload: bytes, content_encoding: str | None = None) -> bytes:
    encoding = (content_encoding or "").casefold().strip()
    if "gzip" in encoding or payload.startswith(b"\x1f\x8b"):
        return gzip.decompress(payload)
    if "deflate" in encoding:
        try:
            return zlib.decompress(payload)
        except zlib.error:
            return zlib.decompress(payload, -zlib.MAX_WBITS)
    return payload


def build_rss_url(query: str, category: str, nyaa_filter: str) -> str:
    params = {"page": "rss", "q": query, "c": category, "f": nyaa_filter}
    return NYAA_BASE_URL + "?" + urllib.parse.urlencode(params)


def build_listing_url(
    category: str,
    nyaa_filter: str,
    page: int,
    *,
    query: str = "",
    sort: str = "id",
    order: str = "desc",
) -> str:
    params = {"c": category, "f": nyaa_filter, "p": page, "s": sort, "o": order}
    if query:
        params["q"] = query
    return NYAA_BASE_URL + "?" + urllib.parse.urlencode(params)


def _text_of(parent: ET.Element, tag: str, default: str = "") -> str:
    node = parent.find(tag)
    return (node.text or "").strip() if node is not None else default


def _nyaa_text(parent: ET.Element, name: str, default: str = "") -> str:
    node = parent.find(f"{NYAA_NS}{name}")
    return (node.text or "").strip() if node is not None else default


def _published_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(parsedate_to_datetime(value).timestamp())
    except (TypeError, ValueError, OverflowError):
        return None


def release_from_rss_item(item: ET.Element) -> NyaaRelease:
    title = _text_of(item, "title")
    link = _text_of(item, "link")
    guid = _text_of(item, "guid")
    nyaa_id = nyaa_id_from_url(guid or link)
    if not title or not nyaa_id:
        raise NyaaParseError("Nyaa RSS item is missing a title or release ID.")
    published = _text_of(item, "pubDate") or None
    size = _nyaa_text(item, "size") or None
    info_hash = _nyaa_text(item, "infoHash") or None
    url = view_url(nyaa_id)
    return NyaaRelease(
        nyaa_id=nyaa_id,
        title=title,
        category=_nyaa_text(item, "category") or None,
        size=size,
        size_bytes=parse_size(size or ""),
        published=published,
        published_at=_published_timestamp(published),
        seeders=as_int(_nyaa_text(item, "seeders")),
        leechers=as_int(_nyaa_text(item, "leechers")),
        downloads=as_int(_nyaa_text(item, "downloads")),
        url=url,
        info_hash=info_hash,
        magnet=magnet_from_hash(info_hash, title),
    )


def release_from_rss_xml(value: str) -> NyaaRelease:
    try:
        item = ET.fromstring(value)
    except ET.ParseError as exc:
        raise NyaaParseError(f"Nyaa RSS item is not valid XML: {exc}") from exc
    return release_from_rss_item(item)


def parse_rss(payload: bytes) -> list[NyaaRelease]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise NyaaParseError(f"Nyaa RSS is not valid XML: {exc}") from exc
    releases: list[NyaaRelease] = []
    for item in root.findall("./channel/item"):
        try:
            releases.append(release_from_rss_item(item))
        except NyaaParseError:
            continue
    return releases


class _FileListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.panel_depth = 0
        self.li_stack: list[dict[str, object]] = []
        self.entries: list[NyaaFileEntry] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value or "" for name, value in attrs}
        classes = set(attributes.get("class", "").casefold().split())
        if tag.casefold() == "div" and "torrent-file-list" in classes:
            self.panel_depth = 1
            return
        if not self.panel_depth:
            return
        if tag.casefold() == "div":
            self.panel_depth += 1
        elif tag.casefold() == "li":
            self.li_stack.append({"text": [], "size": [], "in_size": False})
        elif tag.casefold() == "span" and self.li_stack and "file-size" in classes:
            self.li_stack[-1]["in_size"] = True

    def handle_endtag(self, tag: str) -> None:
        if not self.panel_depth:
            return
        lowered = tag.casefold()
        if lowered == "span" and self.li_stack:
            self.li_stack[-1]["in_size"] = False
        elif lowered == "li" and self.li_stack:
            node = self.li_stack.pop()
            size = " ".join(node["size"]).strip().strip("()")  # type: ignore[arg-type]
            leaf = " ".join(node["text"]).strip().strip("/\\")  # type: ignore[arg-type]
            if size and leaf:
                parents = [
                    " ".join(parent["text"]).strip().strip("/\\")  # type: ignore[arg-type]
                    for parent in self.li_stack
                ]
                name = "/".join(part for part in [*parents, leaf] if part)
                self.entries.append(NyaaFileEntry(name, size, parse_size(size)))
        elif lowered == "div":
            self.panel_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.panel_depth or not self.li_stack or not data.strip():
            return
        key = "size" if self.li_stack[-1]["in_size"] else "text"
        self.li_stack[-1][key].append(data.strip())  # type: ignore[union-attr]


def parse_file_entries(page_html: str) -> list[NyaaFileEntry]:
    parser = _FileListParser()
    parser.feed(page_html)
    parser.close()
    return parser.entries


class _ListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_row = False
        self.current_td: dict[str, object] | None = None
        self.tds: list[dict[str, object]] = []
        self.nyaa_id: str | None = None
        self.title: str | None = None
        self.info_hash: str | None = None
        self.entries: list[NyaaRelease] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        attributes = {name.casefold(): value or "" for name, value in attrs}
        if lowered == "tr":
            self.in_row = True
            self.current_td = None
            self.tds = []
            self.nyaa_id = self.title = self.info_hash = None
            return
        if not self.in_row:
            return
        if lowered == "td":
            self.current_td = {"text": [], "timestamp": attributes.get("data-timestamp"), "category": None}
            return
        if lowered != "a" or self.current_td is None:
            return
        href = attributes.get("href", "")
        match = re.fullmatch(r"/view/(\d+)", href)
        if match:
            self.nyaa_id = match.group(1)
            self.title = html.unescape(attributes.get("title", "")).strip() or None
        elif href.casefold().startswith("magnet:?"):
            values = urllib.parse.parse_qs(urllib.parse.urlsplit(html.unescape(href)).query)
            for exact_topic in values.get("xt", []):
                hash_match = re.fullmatch(r"urn:btih:([0-9a-f]{40})", exact_topic, re.I)
                if hash_match:
                    self.info_hash = hash_match.group(1).lower()
                    break
        elif href.startswith("/?c=") and not self.current_td.get("category"):
            self.current_td["category"] = html.unescape(attributes.get("title", "")).strip() or None

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == "td" and self.in_row and self.current_td is not None:
            self.tds.append(self.current_td)
            self.current_td = None
            return
        if lowered != "tr" or not self.in_row:
            return
        self.in_row = False
        if not self.nyaa_id or not self.title or len(self.tds) < 8:
            return

        def cell_text(index: int) -> str:
            values = self.tds[index].get("text", [])
            return " ".join(values).strip() if isinstance(values, list) else ""

        timestamp = self.tds[4].get("timestamp")
        try:
            published_at = int(timestamp) if timestamp else None
        except (TypeError, ValueError):
            published_at = None
        size = cell_text(3) or None
        category = self.tds[0].get("category")
        url = view_url(self.nyaa_id)
        self.entries.append(
            NyaaRelease(
                nyaa_id=self.nyaa_id,
                title=self.title,
                category=category if isinstance(category, str) else None,
                size=size,
                size_bytes=parse_size(size or ""),
                published=None,
                published_at=published_at,
                seeders=as_int(cell_text(5)),
                leechers=as_int(cell_text(6)),
                downloads=as_int(cell_text(7)),
                url=url,
                info_hash=self.info_hash,
                magnet=magnet_from_hash(self.info_hash, self.title),
            )
        )

    def handle_data(self, data: str) -> None:
        if self.in_row and self.current_td is not None and data.strip():
            values = self.current_td.get("text")
            if isinstance(values, list):
                values.append(data.strip())


def parse_listing(page_html: str) -> list[NyaaRelease]:
    parser = _ListingParser()
    try:
        parser.feed(page_html)
        parser.close()
    except (ValueError, TypeError) as exc:
        raise NyaaParseError(f"Nyaa listing could not be parsed: {exc}") from exc
    return parser.entries


def _detail_label_value(page_html: str, label: str) -> str | None:
    match = re.search(
        rf"<div[^>]*>\s*{re.escape(label)}\s*</div>\s*<div[^>]*>(.*?)</div>",
        page_html,
        re.I | re.S,
    )
    return strip_html_to_text(match.group(1)).strip() if match else None


def parse_detail(nyaa_id: str, page_html: str) -> NyaaReleaseDetail:
    title_match = re.search(
        r"<h3[^>]*class=[\"'][^\"']*panel-title[^\"']*[\"'][^>]*>(.*?)</h3>",
        page_html,
        re.I | re.S,
    )
    title = strip_html_to_text(title_match.group(1)).strip() if title_match else ""
    if not title:
        raise NyaaParseError("Nyaa detail page did not contain a release title.")
    timestamp_match = re.search(r"data-timestamp=[\"'](\d+)[\"']", page_html, re.I)
    hash_match = re.search(r"<kbd>\s*([0-9a-f]{40})\s*</kbd>", page_html, re.I)
    info_hash = hash_match.group(1).lower() if hash_match else None
    size = _detail_label_value(page_html, "File size:")
    release = NyaaRelease(
        nyaa_id=nyaa_id,
        title=title,
        category=_detail_label_value(page_html, "Category:"),
        size=size,
        size_bytes=parse_size(size or ""),
        published=None,
        published_at=int(timestamp_match.group(1)) if timestamp_match else None,
        seeders=as_int(_detail_label_value(page_html, "Seeders:")),
        leechers=as_int(_detail_label_value(page_html, "Leechers:")),
        downloads=as_int(_detail_label_value(page_html, "Completed:")),
        url=view_url(nyaa_id),
        info_hash=info_hash,
        magnet=magnet_from_hash(info_hash, title),
    )
    return NyaaReleaseDetail(release, extract_description(page_html), tuple(parse_file_entries(page_html)))


Opener = Callable[..., Any]


class NyaaClient:
    """Small Nyaa interface; orchestration, caching, and ranking live above it."""

    def __init__(self, *, opener: Opener | None = None) -> None:
        self._opener = opener or urllib.request.urlopen

    def _request(self, url: str, timeout: float) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self._opener(request, timeout=timeout) as response:
                payload = response.read()
                encoding = response.headers.get("Content-Encoding")
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            if code == 404:
                raise NyaaNotFoundError(f"Nyaa release was not found: {url}", url=url) from exc
            raise NyaaNetworkError(f"Nyaa returned HTTP {code}: {url}", url=url) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise NyaaNetworkError(f"Nyaa request failed for {url}: {exc}", url=url) from exc
        try:
            decoded = decode_http_payload(payload, encoding)
        except (gzip.BadGzipFile, EOFError, zlib.error) as exc:
            raise NyaaParseError(f"Nyaa response compression was invalid: {url}", url=url) from exc
        if not decoded:
            raise NyaaParseError(f"Nyaa returned an empty response: {url}", url=url)
        return decoded

    def search(self, request: NyaaSearchRequest) -> list[NyaaRelease]:
        if request.source == "rss":
            url = build_rss_url(request.query, request.category, request.nyaa_filter)
            return parse_rss(self._request(url, request.timeout))
        if request.source != "listing":
            raise ValueError(f"Unsupported Nyaa search source: {request.source}")
        url = build_listing_url(
            request.category,
            request.nyaa_filter,
            request.page,
            query=request.query,
            sort=request.sort,
            order=request.order,
        )
        return parse_listing(self._request(url, request.timeout).decode("utf-8", "replace"))

    def get(self, release_id: str, *, timeout: float = 20) -> NyaaReleaseDetail:
        nyaa_id = nyaa_id_from_url(release_id)
        if not nyaa_id:
            raise ValueError(f"Invalid Nyaa release ID: {release_id}")
        url = view_url(nyaa_id)
        page_html = self._request(url, timeout).decode("utf-8", "replace")
        return parse_detail(nyaa_id, page_html)

    def get_description(self, release_id: str, *, timeout: float = 20) -> str:
        """Return detail evidence when the caller does not need file metadata."""
        return self.get(release_id, timeout=timeout).description

    def fetch_rss(self, query: str, category: str, nyaa_filter: str, timeout: float) -> bytes:
        return self._request(build_rss_url(query, category, nyaa_filter), timeout)

    def fetch_listing(
        self,
        query: str,
        category: str,
        nyaa_filter: str,
        page: int,
        timeout: float,
        *,
        sort: str = "id",
        order: str = "desc",
    ) -> str:
        url = build_listing_url(
            category, nyaa_filter, page, query=query, sort=sort, order=order
        )
        return self._request(url, timeout).decode("utf-8", "replace")

    def fetch_detail_page(self, release_id: str, timeout: float) -> str:
        nyaa_id = nyaa_id_from_url(release_id)
        if not nyaa_id:
            raise ValueError(f"Invalid Nyaa release ID: {release_id}")
        return self._request(view_url(nyaa_id), timeout).decode("utf-8", "replace")
