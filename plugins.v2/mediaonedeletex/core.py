from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class DeletePlan:
    transfer_id: int
    title: str
    year: str
    media_type: str
    src: str
    dest: str
    download_hash: str = ""
    item_id: str = ""
    eligible: bool = False
    reasons: list[str] = field(default_factory=list)


def build_delete_plan(
    *,
    transfer_id: int,
    title: str,
    year: str,
    media_type: str,
    mode: str,
    src: str,
    dest: str,
    seasons: Optional[str] = None,
    episodes: Optional[str] = None,
    download_hash: str = "",
    item_id: str = "",
) -> DeletePlan:
    plan = DeletePlan(
        transfer_id=transfer_id,
        title=title or "",
        year=str(year or ""),
        media_type=media_type or "",
        src=src or "",
        dest=dest or "",
        download_hash=download_hash or "",
        item_id=item_id or "",
    )

    if media_type != "电影":
        plan.reasons.append("当前版本仅支持电影")
    if mode != "link":
        plan.reasons.append("仅支持硬链接整理记录")
    if seasons or episodes:
        plan.reasons.append("当前版本不支持电视剧或分集删除")
    if not dest:
        plan.reasons.append("缺少媒体库目标路径")
    if not src and not download_hash:
        plan.reasons.append("缺少源文件路径和下载哈希")

    plan.eligible = not plan.reasons
    return plan


def iter_empty_parent_candidates(path: str, stop_paths: Iterable[str]) -> list[Path]:
    current = Path(path).resolve().parent
    stop_set = {Path(stop).resolve() for stop in stop_paths if stop}
    candidates: list[Path] = []
    while current not in stop_set and current != current.parent:
        candidates.append(current)
        current = current.parent
    return candidates


def filter_display_items(
    items: list[dict],
    *,
    keyword: str,
    movies_only: bool,
    eligible_only: bool,
    dedupe_titles: bool,
    limit: int,
) -> list[dict]:
    normalized_keyword = (keyword or "").strip().lower()
    filtered: list[dict] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for item in items:
        if movies_only and item.get("media_type") != "电影":
            continue
        if eligible_only and not item.get("eligible"):
            continue
        if normalized_keyword:
            haystack = " ".join(
                str(item.get(field) or "")
                for field in ("title", "src", "dest", "reason_text")
            ).lower()
            if normalized_keyword not in haystack:
                continue
        if dedupe_titles:
            dedupe_key = (
                str(item.get("title") or "").strip().lower(),
                str(item.get("year") or "").strip().lower(),
                str(item.get("media_type") or "").strip().lower(),
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
        filtered.append(item)
        if len(filtered) >= max(1, limit):
            break

    return filtered
