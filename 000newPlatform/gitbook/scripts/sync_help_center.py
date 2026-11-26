#!/usr/bin/env python3
"""将 DMXSmart 帮助中心同步为可直接使用 GitBook Git Sync 的 Markdown 项目。"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import os
import posixpath
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import requests
import yaml
from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter

BASE_ORIGIN = "https://help.dmxsmart.com"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = PROJECT_ROOT / "docs"
REPORT_PATH = PROJECT_ROOT / "sync-report.json"
MAX_ASSET_SIZE = 100 * 1024 * 1024
ASSET_HOSTS = {
    "help.dmxsmart.com",
    "dmxhelpdoc.oss-cn-shenzhen.aliyuncs.com",
    "cdn.nlark.com",
}
ASSET_HOSTS.update(
    host.strip().lower()
    for host in os.environ.get("HELP_CENTER_ALLOWED_ASSET_HOSTS", "").split(",")
    if host.strip()
)
ASSET_EXTENSIONS = {
    ".xls", ".xlsx", ".csv", ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".txt", ".mp4", ".mov", ".webm", ".mp3",
}
MANUALS = {
    "wms": {"title": "WMS使用手册", "entry": "/docs/wms/Introduction"},
    "tms": {"title": "TMS使用手册", "entry": "/docs/tms/Introduction"},
    "printer": {"title": "打单系统使用手册", "entry": "/docs/printer/Introduction"},
    "y2": {
        "title": "Y2使用手册",
        "entry": "/docs/y2/ManagementSettings/NeutralBarcodeSettings",
    },
}
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GitBookHelpCenterSync/1.0)",
    "Accept": "text/html,application/xhtml+xml,image/*,*/*;q=0.8",
}


@dataclass
class NavNode:
    label: str
    url: str
    is_category: bool = False
    children: list["NavNode"] = field(default_factory=list)


@dataclass
class AssetResult:
    url: str
    kind: str
    local_path: str | None
    error: str | None = None
    sha256: str | None = None
    size: int | None = None


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u200b", " ")).strip()


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def request(
    url: str,
    *,
    stream: bool = False,
    timeout: tuple[int, int] = (20, 120),
    allowed_hosts: set[str] | None = None,
):
    last_error: Exception | None = None
    for attempt in range(4):
        current_url = url
        try:
            for redirect_count in range(6):
                if allowed_hosts and urlsplit(current_url).hostname not in allowed_hosts:
                    raise RuntimeError(f"资源主机不在白名单：{current_url}")
                response = requests.get(
                    current_url,
                    headers=REQUEST_HEADERS,
                    stream=stream,
                    timeout=timeout,
                    allow_redirects=False,
                )
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    response.close()
                    if not location:
                        raise requests.HTTPError(f"重定向缺少 Location：{current_url}")
                    if redirect_count == 5:
                        raise requests.HTTPError(f"重定向次数过多：{url}")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {response.status_code}: {current_url}")
                response.raise_for_status()
                return response
        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"下载失败：{url}；{last_error}")


def source_url(path: str) -> str:
    return urljoin(BASE_ORIGIN + "/", path.lstrip("/"))


def get_source_urls() -> dict[str, list[str]]:
    response = request(BASE_ORIGIN + "/sitemap.xml")
    root = ET.fromstring(response.content)
    result = {manual: [] for manual in MANUALS}
    seen: set[str] = set()
    for loc in (element for element in root.iter() if element.tag.endswith("loc")):
        raw = (loc.text or "").strip()
        parts = urlsplit(raw)
        match = re.match(r"^/docs/(wms|tms|printer|y2)(?:/|$)", parts.path)
        if not match:
            continue
        manual = match.group(1)
        url = canonical_url(source_url(parts.path))
        if url not in seen:
            result[manual].append(url)
            seen.add(url)
    return result


def fetch_pages(urls: list[str]) -> dict[str, BeautifulSoup]:
    pages: dict[str, BeautifulSoup] = {}

    def fetch_one(url: str) -> tuple[str, BeautifulSoup]:
        response = request(url)
        soup = BeautifulSoup(response.content, "html.parser")
        if soup.select_one(".theme-doc-markdown") is None:
            raise RuntimeError(f"页面缺少正文容器：{url}")
        return canonical_url(url), soup

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_one, url): url for url in urls}
        for index, future in enumerate(as_completed(futures), 1):
            url, soup = future.result()
            pages[url] = soup
            if index % 20 == 0 or index == len(urls):
                print(f"已读取页面：{index}/{len(urls)}", flush=True)
    return pages


def nav_anchor(item: Tag) -> tuple[str, str] | None:
    anchor = item.find("a")
    if anchor is None or not anchor.get("href"):
        return None
    return clean_text(anchor.get_text(" ", strip=True)), canonical_url(
        urljoin(BASE_ORIGIN + "/", anchor["href"])
    )


def find_nav_item(sidebar: Tag, url: str, category: bool) -> Tag | None:
    class_name = "theme-doc-sidebar-item-category" if category else "theme-doc-sidebar-item-link"
    for item in sidebar.select(f"li.{class_name}"):
        anchor = nav_anchor(item)
        if anchor and anchor[1] == canonical_url(url):
            return item
    return None


def expand_nav_item(item: Tag, pages: dict[str, BeautifulSoup]) -> NavNode:
    anchor = nav_anchor(item)
    if anchor is None:
        raise RuntimeError("侧边栏存在无法识别的导航项")
    label, url = anchor
    classes = item.get("class", [])
    is_category = "theme-doc-sidebar-item-category" in classes
    node = NavNode(label=label, url=url, is_category=is_category)
    if not is_category:
        return node

    nested = item.find("ul", recursive=False)
    if nested is None:
        page = pages.get(url)
        if page is None:
            raise RuntimeError(f"侧边栏分类页面未下载：{url}")
        sidebar = page.select_one(".theme-doc-sidebar-menu")
        expanded = find_nav_item(sidebar, url, category=True) if sidebar else None
        if expanded is None:
            raise RuntimeError(f"无法展开侧边栏分类：{label}（{url}）")
        nested = expanded.find("ul", recursive=False)
        item = expanded
    if nested is None:
        raise RuntimeError(f"侧边栏分类没有子项：{label}（{url}）")
    node.children = [expand_nav_item(child, pages) for child in nested.find_all("li", recursive=False)]
    return node


def discover_navigation(manual: str, pages: dict[str, BeautifulSoup]) -> list[NavNode]:
    entry = canonical_url(source_url(MANUALS[manual]["entry"]))
    sidebar = pages[entry].select_one(".theme-doc-sidebar-menu")
    if sidebar is None:
        raise RuntimeError(f"找不到 {manual} 的侧边栏")
    return [
        expand_nav_item(item, pages)
        for item in sidebar.find_all("li", recursive=False)
    ]


def leaf_urls(nodes: list[NavNode]) -> list[str]:
    result: list[str] = []
    for node in nodes:
        if node.is_category:
            result.extend(leaf_urls(node.children))
        else:
            result.append(node.url)
    return result


def page_file(manual: str, url: str) -> str:
    path = unquote(urlsplit(url).path)
    prefix = f"/docs/{manual}/"
    if not path.startswith(prefix):
        raise ValueError(f"页面不属于 {manual}：{url}")
    relative = path[len(prefix):].strip("/")
    if not relative:
        relative = "README"
    if relative.lower().endswith((".md", ".markdown")):
        relative = relative.rsplit(".", 1)[0]
    segments = relative.split("/")
    if any(
        segment in ("", ".", "..")
        or any(character in segment for character in ("\\", ":", "\x00"))
        for segment in segments
    ):
        raise ValueError(f"页面路径包含非法片段：{url}")
    return f"{manual}/{relative}.md"


def category_file(node: NavNode, manual: str) -> str:
    parents = [
        str(PurePosixPath(page_file(manual, url)).parent)
        for url in leaf_urls([node])
    ]
    parent = posixpath.commonpath(parents) if parents else manual
    if parent == manual:
        return f"{manual}/README.md"
    return f"{parent}/README.md"


def relative_link(current_file: str, target_file: str) -> str:
    return posixpath.relpath(target_file, posixpath.dirname(current_file) or ".")


def safe_asset_name(url: str, content_type: str, kind: str) -> str:
    path = unquote(urlsplit(url).path)
    name = posixpath.basename(path) or "asset"
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")[:120] or "asset"
    if not PurePosixPath(name).suffix:
        extension = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if extension == ".jpe":
            extension = ".jpg"
        if extension:
            name += extension
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    folder = "images" if kind == "image" else "files"
    return f".gitbook/assets/{folder}/{digest}-{name}"


def source_kind(source: Tag) -> str:
    return "image" if source.parent and source.parent.name == "picture" else "file"


def collect_assets(pages: dict[str, BeautifulSoup], url_to_file: dict[str, str]) -> dict[str, str]:
    assets: dict[str, str] = {}

    def add(raw_url: str, kind: str, page_url: str) -> None:
        value = raw_url.strip()
        if not value or value.startswith(("data:", "blob:")):
            return
        absolute = canonical_url(urljoin(page_url, value))
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            return
        if parts.hostname not in ASSET_HOSTS:
            raise RuntimeError(f"资源主机不在白名单：{absolute}")
        assets.setdefault(absolute, kind)

    for url, soup in pages.items():
        markdown = soup.select_one(".theme-doc-markdown")
        for image in markdown.select("img"):
            add(image.get("src") or image.get("data-src") or "", "image", url)
        for source in markdown.select("source"):
            if source.get("src"):
                add(source["src"], source_kind(source), url)
            if source.get("srcset"):
                for candidate in source["srcset"].split(","):
                    add(candidate.strip().split()[0], "image", url)
        for media in markdown.select("video, audio"):
            if media.get("src"):
                add(media["src"], "file", url)
            if media.get("poster"):
                add(media["poster"], "image", url)
        for anchor in markdown.select("a[href]"):
            href = anchor["href"]
            if PurePosixPath(unquote(urlsplit(href).path)).suffix.lower() in ASSET_EXTENSIONS:
                add(href, "file", url)
    return assets


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(url: str, kind: str) -> AssetResult:
    local_path: str | None = None
    temp_path: Path | None = None
    try:
        with request(url, stream=True, allowed_hosts=ASSET_HOSTS) as response:
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            local_path = safe_asset_name(url, content_type, kind)
            destination = DOCS_ROOT / local_path
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_ASSET_SIZE:
                raise RuntimeError(f"文件超过 GitBook 100MB 限制：{length} bytes")
            if kind == "image" and not (
                content_type.lower().startswith("image/")
                or PurePosixPath(unquote(urlsplit(url).path)).suffix.lower()
                in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}
            ):
                raise RuntimeError(f"图片响应类型异常：{content_type}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp_path = destination.with_suffix(destination.suffix + ".part")
            size = 0
            digest = hashlib.sha256()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=128 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > MAX_ASSET_SIZE:
                        raise RuntimeError("文件超过 GitBook 100MB 限制")
                    digest.update(chunk)
                    handle.write(chunk)
            if size == 0:
                raise RuntimeError("下载内容为空")
            sha256 = digest.hexdigest()
            unchanged = (
                destination.exists()
                and destination.stat().st_size == size
                and file_sha256(destination) == sha256
            )
            if unchanged:
                temp_path.unlink()
            else:
                os.replace(temp_path, destination)
            temp_path = None
            return AssetResult(url, kind, local_path, sha256=sha256, size=size)
    except Exception as exc:
        return AssetResult(url, kind, None, str(exc))
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def download_assets(assets: dict[str, str]) -> dict[str, AssetResult]:
    results: dict[str, AssetResult] = {}
    items = list(assets.items())
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(download_asset, url, kind): url for url, kind in items}
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results[result.url] = result
            if result.error:
                print(f"资源下载失败：{result.url}；{result.error}", file=sys.stderr, flush=True)
            if index % 25 == 0 or index == len(items):
                print(f"已处理资源：{index}/{len(items)}", flush=True)
    return results


class GitBookConverter(MarkdownConverter):
    def convert_iframe(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        allowed = ("src", "title", "width", "height", "allow", "allowfullscreen", "loading")
        attrs = " ".join(
            f'{key}="{html.escape(str(el[key]), quote=True)}"'
            for key in allowed if el.get(key) is not None
        )
        return f'\n\n<iframe {attrs}></iframe>\n\n'

    def convert_video(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        return f"\n\n{el}\n\n"

    def convert_audio(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        return f"\n\n{el}\n\n"

    def convert_details(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        summary_tag = el.find("summary")
        summary = clean_text(summary_tag.get_text(" ", strip=True)) if summary_tag else "详情"
        body = text.strip()
        if body.startswith(summary):
            body = body[len(summary):].lstrip()
        return f"\n\n<details>\n<summary>{html.escape(summary)}</summary>\n\n{body}\n\n</details>\n\n"


def rewrite_internal_link(
    href: str,
    current_url: str,
    current_file: str,
    url_to_file: dict[str, str],
    asset_results: dict[str, AssetResult],
) -> str:
    value = href.strip()
    if not value or value.startswith(("#", "mailto:", "tel:", "data:", "javascript:")):
        return value
    absolute = urljoin(current_url, value)
    parts = urlsplit(absolute)
    canonical = canonical_url(absolute)
    is_help_host = (
        parts.scheme in ("http", "https")
        and parts.hostname == urlsplit(BASE_ORIGIN).hostname
    )
    path_key = (
        canonical_url(source_url(parts.path))
        if is_help_host and re.match(r"^/docs/(wms|tms|printer|y2)(?:/|$)", parts.path)
        else canonical
    )
    if canonical in url_to_file:
        target = relative_link(current_file, url_to_file[canonical])
        return urlunsplit(("", "", target, parts.query, parts.fragment))
    if path_key in url_to_file:
        target = relative_link(current_file, url_to_file[path_key])
        return urlunsplit(("", "", target, parts.query, parts.fragment))
    asset = asset_results.get(canonical)
    if asset and asset.local_path:
        target = relative_link(current_file, asset.local_path)
        return urlunsplit(("", "", target, parts.query, parts.fragment))
    return value


def convert_page(
    manual: str,
    url: str,
    soup: BeautifulSoup,
    url_to_file: dict[str, str],
    asset_results: dict[str, AssetResult],
) -> str:
    current_file = page_file(manual, url)
    markdown = soup.select_one(".theme-doc-markdown")
    for unwanted in markdown.select("script, style, button, .hash-link"):
        unwanted.decompose()

    def local_asset(raw_url: str, kind: str) -> str:
        absolute = canonical_url(urljoin(url, raw_url))
        result = asset_results.get(absolute)
        if result and result.local_path:
            return relative_link(current_file, result.local_path)
        return raw_url

    for image in markdown.select("img"):
        raw_url = image.get("src") or image.get("data-src")
        if not raw_url:
            image.decompose()
            continue
        original_attrs = dict(image.attrs)
        image.attrs = {"src": local_asset(raw_url, "image")}
        for key in ("alt", "title", "width", "height"):
            if original_attrs.get(key):
                image.attrs[key] = original_attrs[key]
    for source in markdown.select("source"):
        kind = source_kind(source)
        if source.get("src"):
            source["src"] = local_asset(source["src"], kind)
        if source.get("srcset"):
            candidates = []
            for candidate in source["srcset"].split(","):
                pieces = candidate.strip().split()
                if pieces:
                    pieces[0] = local_asset(pieces[0], "image")
                    candidates.append(" ".join(pieces))
            source["srcset"] = ", ".join(candidates)
    for media in markdown.select("video, audio"):
        if media.get("src"):
            media["src"] = local_asset(media["src"], "file")
        if media.get("poster"):
            media["poster"] = local_asset(media["poster"], "image")
    for anchor in markdown.select("a[href]"):
        anchor["href"] = rewrite_internal_link(
            anchor["href"], url, current_file, url_to_file, asset_results
        )

    converter = GitBookConverter(
        heading_style="ATX",
        bullets="-",
        strong_em_symbol="*",
        escape_asterisks=False,
        escape_underscores=False,
        autolinks=True,
        keep_inline_images_in=["td", "th"],
    )
    body = converter.convert_soup(markdown)
    body = body.replace("\u200b", "")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    source_note = f"<!-- 源页面：{url} -->"
    return f"{body}\n\n{source_note}\n"


def nav_markdown(
    nodes: list[NavNode],
    manual: str,
    indent: int = 0,
    current_file: str | None = None,
) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for node in nodes:
        target = category_file(node, manual) if node.is_category else page_file(manual, node.url)
        link = relative_link(current_file, target) if current_file else target
        lines.append(f"{prefix}* [{node.label}]({link})")
        if node.children:
            lines.extend(nav_markdown(node.children, manual, indent + 2, current_file))
    return lines


def category_index(node: NavNode, manual: str) -> str:
    lines = [f"# {node.label}", ""]
    if node.children:
        lines.extend(nav_markdown(node.children, manual, current_file=category_file(node, manual)))
    lines.extend(["", f"<!-- 由 {node.url} 的侧边栏分类生成 -->", ""])
    return "\n".join(lines)


def all_categories(nodes: list[NavNode]) -> list[NavNode]:
    result: list[NavNode] = []
    for node in nodes:
        if node.is_category:
            result.append(node)
            result.extend(all_categories(node.children))
    return result


def find_leaf_label(nodes: list[NavNode], url: str) -> str:
    for node in nodes:
        if node.is_category:
            label = find_leaf_label(node.children, url)
            if label:
                return label
        elif node.url == url:
            return node.label
    return "开始阅读"


def manual_index(manual: str, nodes: list[NavNode], page_count: int) -> str:
    config = MANUALS[manual]
    index_file = f"{manual}/README.md"
    entry_file = page_file(manual, source_url(config["entry"]))
    lines = [
        f"# {config['title']}",
        "",
        f"本手册从 [DMXSmart 帮助中心]({source_url(config['entry'])}) 同步，包含 {page_count} 个原始页面。",
        "",
        "## 开始阅读",
        "",
        f"- [{find_leaf_label(nodes, source_url(config['entry']))}]({relative_link(index_file, entry_file)})",
        "",
        "## 目录",
        "",
    ]
    for node in nodes:
        target = category_file(node, manual) if node.is_category else page_file(manual, node.url)
        lines.append(f"- [{node.label}]({relative_link(index_file, target)})")
    lines.extend(["", f"<!-- 源页面：{source_url(config['entry'])} -->", ""])
    return "\n".join(lines)


def write_text(path: Path, content: str, *, root: Path = DOCS_ROOT) -> None:
    resolved_path = path.resolve()
    resolved_path.relative_to(root.resolve())
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(content, encoding="utf-8", newline="\n")


def build_project(
    pages: dict[str, BeautifulSoup],
    navigations: dict[str, list[NavNode]],
    url_to_file: dict[str, str],
    asset_results: dict[str, AssetResult],
    source_urls: dict[str, list[str]],
) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    write_text(
        DOCS_ROOT / ".gitbook.yaml",
        "root: ./\n\nstructure:\n  readme: README.md\n  summary: SUMMARY.md\n",
    )

    summary = [
        "# Summary",
        "",
        "* [帮助中心](README.md)",
        "",
    ]
    for manual, config in MANUALS.items():
        summary.append(f"* [{config['title']}]({manual}/README.md)")
        summary.extend(nav_markdown(navigations[manual], manual, indent=2))
        summary.append("")
    write_text(DOCS_ROOT / "SUMMARY.md", "\n".join(summary).rstrip() + "\n")

    root_lines = [
        "# DMXSmart 帮助中心",
        "",
        "本帮助中心汇总 WMS、TMS、打单系统和 Y2 四套系统的使用手册。",
        "",
    ]
    for manual, config in MANUALS.items():
        count = len(source_urls[manual])
        root_lines.append(f"- [{config['title']}]({manual}/README.md)（{count} 页）")
    root_lines.extend([
        "",
        f"最近同步时间：{generated_at}",
        "",
        "<!-- 内容来源：https://help.dmxsmart.com/ -->",
        "",
    ])
    write_text(DOCS_ROOT / "README.md", "\n".join(root_lines))

    for manual, config in MANUALS.items():
        write_text(DOCS_ROOT / manual / "README.md", manual_index(manual, navigations[manual], len(source_urls[manual])))
        for category in all_categories(navigations[manual]):
            write_text(DOCS_ROOT / category_file(category, manual), category_index(category, manual))
        for url in source_urls[manual]:
            content = convert_page(manual, url, pages[url], url_to_file, asset_results)
            write_text(DOCS_ROOT / page_file(manual, url), content)

    write_text(
        PROJECT_ROOT / "gitbook-docs.yaml",
        "$schema: https://api.gitbook.com/gitbook-docs.yaml\n"
        "site:\n"
        "  title: DMXSmart 帮助中心\n"
        "  structure:\n"
        "    - type: space\n"
        "      key: help-center\n"
        "      title: 帮助中心\n"
        "      path: help-center\n"
        "      default: true\n"
        "      content:\n"
        "        directory: ./docs\n",
        root=PROJECT_ROOT,
    )


def markdown_targets(path: Path) -> list[str]:
    targets: list[str] = []
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        value = match.group(1).strip()
        if value.startswith("<") and ">" in value:
            value = value[1:value.index(">")]
        value = value.split(' "', 1)[0].strip()
        targets.append(value)
    for match in re.finditer(r"\b(?:src|href)=[\"']([^\"']+)[\"']", text):
        targets.append(html.unescape(match.group(1)))
    return targets


def valid_image_signature(path: Path) -> bool:
    with path.open("rb") as handle:
        head = handle.read(32).lstrip()
    return (
        head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM"))
        or (head.startswith(b"RIFF") and head[8:12] == b"WEBP")
        or head.startswith((b"II*\x00", b"MM\x00*", b"\x00\x00\x01\x00"))
        or head.startswith((b"<svg", b"<?xml"))
        or (len(head) >= 12 and head[4:8] == b"ftyp")
    )


def verify_project(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    summary_path = DOCS_ROOT / "SUMMARY.md"
    if not summary_path.exists():
        return ["缺少 docs/SUMMARY.md"]
    summary = summary_path.read_text(encoding="utf-8")
    summary_files = re.findall(r"\[[^\]]+\]\(([^)]+)\)", summary)
    duplicates = sorted({path for path in summary_files if summary_files.count(path) > 1})
    if duplicates:
        errors.append(f"SUMMARY.md 存在重复页面：{duplicates}")
    for target in summary_files:
        if not (DOCS_ROOT / target).exists():
            errors.append(f"SUMMARY.md 链接不存在：{target}")

    for page in report.get("source_pages", []):
        path = DOCS_ROOT / page["file"]
        if not path.exists():
            errors.append(f"缺少源页面：{page['url']}")
        elif page["url"] not in path.read_text(encoding="utf-8"):
            errors.append(f"页面缺少来源标记：{page['file']}")

    for path in DOCS_ROOT.rglob("*.md"):
        for target in markdown_targets(path):
            if target.startswith(("#", "http://", "https://", "mailto:", "tel:", "data:", "javascript:")):
                continue
            value = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not value:
                continue
            resolved = (path.parent / value).resolve()
            if not resolved.exists():
                errors.append(f"本地链接不存在：{path.relative_to(DOCS_ROOT)} -> {target}")

    for config in (PROJECT_ROOT / "gitbook-docs.yaml", DOCS_ROOT / ".gitbook.yaml"):
        try:
            yaml.safe_load(config.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"YAML 配置无效：{config.name}；{exc}")

    asset_root = (DOCS_ROOT / ".gitbook" / "assets").resolve()
    for item in report.get("assets", []):
        if item.get("error"):
            errors.append(f"资源下载失败：{item['url']}；{item['error']}")
            continue
        local_path = item.get("local_path")
        if not local_path:
            errors.append(f"资源缺少本地路径：{item['url']}")
            continue
        path = (DOCS_ROOT / local_path).resolve()
        try:
            path.relative_to(asset_root)
        except ValueError:
            errors.append(f"资源路径越界：{local_path}")
            continue
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"资源文件缺失或为空：{local_path}")
            continue
        if item.get("size") is not None and path.stat().st_size != item["size"]:
            errors.append(f"资源大小不匹配：{local_path}")
        if item.get("sha256") and file_sha256(path) != item["sha256"]:
            errors.append(f"资源哈希不匹配：{local_path}")
        if item.get("kind") == "image" and not valid_image_signature(path):
            errors.append(f"图片文件签名无效：{local_path}")
    return sorted(set(errors))


def make_report(
    source_urls: dict[str, list[str]],
    navigations: dict[str, list[NavNode]],
    url_to_file: dict[str, str],
    asset_results: dict[str, AssetResult],
) -> dict[str, Any]:
    source_pages = [
        {"manual": manual, "url": url, "file": url_to_file[url]}
        for manual, urls in source_urls.items() for url in urls
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": BASE_ORIGIN,
        "counts": {
            "source_pages": len(source_pages),
            "manuals": {manual: len(urls) for manual, urls in source_urls.items()},
            "navigation_pages": {
                manual: len(leaf_urls(nodes)) for manual, nodes in navigations.items()
            },
            "markdown_files": len(list(DOCS_ROOT.rglob("*.md"))),
            "assets": len(asset_results),
            "images": sum(1 for item in asset_results.values() if item.kind == "image"),
            "files": sum(1 for item in asset_results.values() if item.kind == "file"),
        },
        "source_pages": source_pages,
        "managed_markdown": sorted(
            path.relative_to(DOCS_ROOT).as_posix()
            for path in DOCS_ROOT.rglob("*.md")
        ),
        "assets": [
            {
                "url": item.url,
                "kind": item.kind,
                "local_path": item.local_path,
                "error": item.error,
                "sha256": item.sha256,
                "size": item.size,
            }
            for item in asset_results.values()
        ],
    }


def cleanup_stale(previous: dict[str, Any], current: dict[str, Any]) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    errors: list[str] = []
    docs_root = DOCS_ROOT.resolve()
    asset_root = (DOCS_ROOT / ".gitbook" / "assets").resolve()

    stale_markdown = set(previous.get("managed_markdown", [])) - set(current.get("managed_markdown", []))
    stale_assets = {
        item.get("local_path")
        for item in previous.get("assets", [])
        if item.get("local_path")
    } - {item.get("local_path") for item in current.get("assets", [])}
    candidates: list[tuple[str, Path, Path]] = []
    for relative in stale_markdown:
        path = (DOCS_ROOT / relative).resolve()
        try:
            path.relative_to(docs_root)
            if path.suffix.lower() != ".md":
                raise ValueError("不是 Markdown 文件")
            candidates.append((relative, path, docs_root))
        except ValueError:
            errors.append(f"拒绝清理非法 Markdown 路径：{relative}")
    for relative in stale_assets:
        if not relative:
            continue
        path = (DOCS_ROOT / relative).resolve()
        try:
            path.relative_to(asset_root)
            candidates.append((relative, path, asset_root))
        except ValueError:
            errors.append(f"拒绝清理非法资源路径：{relative}")

    if errors:
        return removed, errors
    for relative, path, _ in candidates:
        if path.is_file():
            path.unlink()
            removed.append(relative)
    return sorted(removed), []


def sync() -> int:
    previous_report: dict[str, Any] = {}
    if REPORT_PATH.exists():
        try:
            previous_report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous_report = {}
    source_urls = get_source_urls()
    print("源页面数量：", {manual: len(urls) for manual, urls in source_urls.items()}, flush=True)
    expected = [url for urls in source_urls.values() for url in urls]
    pages = fetch_pages(expected)
    url_to_file = {
        url: page_file(manual, url)
        for manual, urls in source_urls.items() for url in urls
    }
    navigations: dict[str, list[NavNode]] = {}
    for manual in MANUALS:
        nodes = discover_navigation(manual, pages)
        discovered = set(leaf_urls(nodes))
        missing = [url for url in source_urls[manual] if url not in discovered]
        if missing:
            raise RuntimeError(f"{manual} 有 {len(missing)} 个页面未出现在侧边栏：{missing}")
        navigations[manual] = nodes
        print(f"{manual} 侧边栏页面：{len(discovered)}", flush=True)

    assets = collect_assets(pages, url_to_file)
    print(f"发现图片与附件：{len(assets)}", flush=True)
    asset_results = download_assets(assets)
    build_project(pages, navigations, url_to_file, asset_results, source_urls)
    report = make_report(source_urls, navigations, url_to_file, asset_results)
    errors = verify_project(report)
    if not errors:
        removed, cleanup_errors = cleanup_stale(previous_report, report)
        report["removed_files"] = removed
        errors.extend(cleanup_errors)
    report["verification_errors"] = errors
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print(f"校验失败，共 {len(errors)} 项：", file=sys.stderr)
        for error in errors[:30]:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("同步与校验完成：", json.dumps(report["counts"], ensure_ascii=False), flush=True)
    return 0


def verify_only() -> int:
    if not REPORT_PATH.exists():
        print("找不到 sync-report.json，请先执行完整同步。", file=sys.stderr)
        return 1
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    errors = verify_project(report)
    if errors:
        print(f"校验失败，共 {len(errors)} 项：", file=sys.stderr)
        for error in errors[:50]:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("本地校验通过：", json.dumps(report.get("counts", {}), ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="仅校验本地生成结果，不访问网络")
    args = parser.parse_args()
    return verify_only() if args.verify_only else sync()


if __name__ == "__main__":
    raise SystemExit(main())
