import os
import re
from dataclasses import dataclass
from typing import Callable

import requests

from douyin_video_parser import DouyinVideoParser
from services.douyin_login import DEFAULT_SAVE_DIR


def safe_filename(text: str, fallback: str) -> str:
    text = text or ""
    text = re.sub(r"[\\/:*?\"<>|]", "_", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return fallback
    return text[:60]


def choose_download_url(info: dict, quality: str | None = None) -> str | None:
    qualities = info.get("qualities") or []
    if quality:
        matched = [item for item in qualities if item.get("ratio") == quality]
        if matched:
            best = max(matched, key=lambda item: item.get("bit_rate") or 0)
            return best.get("url")

    if qualities:
        return qualities[0].get("url")

    return info.get("nwm_url")


def progress_percent(downloaded: int, total: int) -> int:
    if total <= 0:
        return 0
    return min(100, int(downloaded * 100 / total))


@dataclass
class DownloadResult:
    path: str
    filename: str
    content_type: str
    aweme_id: str | None
    desc: str | None


def serialize_video_info(info: dict) -> dict:
    qualities_by_ratio = {}
    for item in info.get("qualities") or []:
        ratio = item.get("ratio") or "default"
        payload = {
            "ratio": item.get("ratio"),
            "bit_rate": item.get("bit_rate", 0),
            "quality_label": item.get("quality_label") or item.get("ratio") or "默认清晰度",
            "gear_name": item.get("gear_name", ""),
        }
        current = qualities_by_ratio.get(ratio)
        if current is None or payload["bit_rate"] > current["bit_rate"]:
            qualities_by_ratio[ratio] = payload

    qualities = sorted(
        qualities_by_ratio.values(),
        key=lambda item: (item["bit_rate"], _ratio_rank(item["ratio"])),
        reverse=True,
    )

    return {
        "aweme_id": info.get("aweme_id"),
        "desc": info.get("desc"),
        "create_time": info.get("create_time"),
        "author_nickname": info.get("author_nickname"),
        "author_sec_uid": info.get("author_sec_uid"),
        "cover_url": info.get("cover_url"),
        "content_type": info.get("content_type"),
        "qualities": qualities,
    }


def _ratio_rank(ratio: str | None) -> int:
    if not ratio:
        return 0
    match = re.search(r"(\d+)p", ratio)
    if not match:
        return 0
    return int(match.group(1))


def parse_video_info(share_url: str, *, cookie: str) -> dict:
    parser = DouyinVideoParser()
    parser.set_cookie(cookie)
    info = parser.parse_video(share_url)
    if not info:
        raise ValueError("解析失败，请确认链接有效且 Cookie 未过期")
    if info.get("content_type") != "video":
        raise ValueError("当前页面只支持视频，不支持图集")
    return serialize_video_info(info)


def download_video(
    share_url: str,
    *,
    cookie: str,
    save_dir: str = DEFAULT_SAVE_DIR,
    quality: str | None = None,
    progress_cb: Callable[[int, int, int], None] | None = None,
) -> DownloadResult:
    parser = DouyinVideoParser()
    parser.set_cookie(cookie)
    info = parser.parse_video(share_url)
    if not info:
        raise ValueError("解析失败，请确认链接有效且 Cookie 未过期")

    if info.get("content_type") != "video":
        raise ValueError("当前接口只支持下载视频，不支持图集")

    download_url = choose_download_url(info, quality=quality)
    if not download_url:
        raise ValueError("解析成功但未找到可下载的视频地址")

    os.makedirs(save_dir, exist_ok=True)
    aweme_id = info.get("aweme_id") or "douyin"
    desc = info.get("desc") or ""
    suffix = ""
    if quality:
        suffix = f"_{quality}"
    elif info.get("qualities"):
        suffix = f"_{info['qualities'][0].get('ratio', '')}"

    filename = safe_filename(desc, aweme_id) + suffix + ".mp4"
    path = os.path.join(save_dir, filename)
    _download_file(download_url, path, progress_cb=progress_cb)

    return DownloadResult(
        path=path,
        filename=filename,
        content_type="video/mp4",
        aweme_id=info.get("aweme_id"),
        desc=desc,
    )


def _download_file(
    url: str,
    path: str,
    progress_cb: Callable[[int, int, int], None] | None = None,
) -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/90.0.4430.212 Safari/537.36"
        ),
        "Referer": "https://www.douyin.com/",
        "Origin": "https://www.douyin.com",
        "Accept": "*/*",
        "Range": "bytes=0-",
    }
    response = requests.get(url, headers=headers, stream=True, timeout=30)
    if response.status_code not in (200, 206):
        raise ValueError(f"视频下载失败，HTTP 状态码：{response.status_code}")

    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    if progress_cb:
        progress_cb(0, downloaded, total)

    with open(path, "wb") as file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(progress_percent(downloaded, total), downloaded, total)

    if progress_cb:
        progress_cb(100, downloaded, total)
