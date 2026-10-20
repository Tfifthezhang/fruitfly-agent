"""Direct public-page fetching and HTML-to-text extraction."""
import hashlib
from html.parser import HTMLParser
import re
from urllib.parse import urljoin

from ..client import WebClient, WebError, normalize_url
from ..contracts import FetchResponse
from .common import require_text


class _HtmlText(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url, self.parts, self.title = url, [], []
        self._hidden, self._in_title, self._pre = [], False, 0
        self._links = []
        self._chars, self.truncated = 0, False

    def _append(self, text):
        room = max(0, 2_000_000 - self._chars)
        self.truncated = self.truncated or len(text) > room
        text = text[:room]
        self._chars += len(text)
        if text:
            self.parts.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template", "svg"}:
            self._hidden.append(tag)
        if self._hidden:
            return
        if tag == "title":
            self._in_title = True
        if tag == "pre":
            self._pre += 1
        if tag in {"p", "div", "section", "article", "br", "li", "tr", "pre", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._append("\n")
        if tag in {"td", "th"}:
            self._append(" | ")
        if tag == "a":
            href = dict(attrs).get("href") or ""
            try:
                self._links.append(normalize_url(urljoin(self.url, href)) if href else "")
            except WebError:
                self._links.append("")

    def handle_endtag(self, tag):
        if self._hidden:
            if tag == self._hidden[-1]:
                self._hidden.pop()
            return
        if tag == "title":
            self._in_title = False
        if tag == "pre":
            self._pre = max(0, self._pre - 1)
        if tag == "a" and self._links:
            url = self._links.pop()
            if url:
                self._append(" (" + url + ")")
        if tag in {"p", "div", "section", "article", "li", "tr", "pre", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._append("\n")

    def handle_data(self, data):
        if self._hidden:
            return
        if self._in_title:
            self.title.append(data)
        else:
            self._append(data if self._pre else re.sub(r"\s+", " ", data))


def _extract(response):
    media = response.content_type.split(";", 1)[0].strip()
    if media not in {"text/html", "application/xhtml+xml", "application/json", "application/xml"} and not media.startswith("text/"):
        raise WebError("unsupported_content", "Only HTML, text, JSON and XML are supported. PDFs and other binary files need a separate reader.")
    try:
        text = response.body.decode(response.encoding, errors="replace")
    except LookupError:
        text = response.body.decode("utf-8", errors="replace")
    if "\x00" in text:
        raise WebError("unsupported_content", "The response appears to contain binary data.")
    title = ""
    truncated = False
    if media in {"text/html", "application/xhtml+xml"}:
        parser = _HtmlText(response.url)
        parser.feed(text)
        parser.close()
        title = " ".join("".join(parser.title).split())[:300]
        truncated = parser.truncated
        text = "\n".join(line.rstrip() for line in "".join(parser.parts).splitlines() if line.strip())
    require_text(text)
    return title, text, truncated


class DirectFetch:
    description = ("Fetch a known public HTTP(S) URL as untrusted source text with links and numbered lines. "
                   "Use to read a specific page, inspect documentation and verify details or quotations against the source. "
                   "Use offset/limit to continue. Supports HTML, text, JSON and XML; no JavaScript rendering, login or PDF parsing. Cite the returned final URL.")

    def __init__(self, client: WebClient, api_key: str = ""):
        self.client = client

    async def fetch(self, url: str, *, signal=None):
        url = normalize_url(url)
        response, cached = await self.client.request("GET", url, signal=signal, redirects=True,
            headers={"Accept": "text/html, text/plain, text/markdown, application/json, application/xml"})
        try:
            title, text, truncated = _extract(response)
        except WebError:
            self.client.discard(response)
            raise
        return FetchResponse(title, text, url, response.url, hashlib.sha256(response.body).hexdigest(),
                             response.retrieved_at, cached, truncated)
