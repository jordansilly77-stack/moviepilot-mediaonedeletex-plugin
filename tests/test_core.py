import importlib.util
from pathlib import Path
import sys


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins.v2"
    / "mediaonedeletex"
    / "core.py"
)
SPEC = importlib.util.spec_from_file_location("mediaonedeletex_core", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

build_delete_plan = MODULE.build_delete_plan
filter_display_items = MODULE.filter_display_items
is_stale_history_candidate = MODULE.is_stale_history_candidate
slice_page_items = MODULE.slice_page_items
iter_empty_parent_candidates = MODULE.iter_empty_parent_candidates


def test_build_delete_plan_accepts_movie_hardlink_with_dest_and_source():
    plan = build_delete_plan(
        transfer_id=1,
        title="疯狂动物城2",
        year="2025",
        media_type="电影",
        mode="link",
        src="/media/qbdownloads/电影/疯狂动物城2.mkv",
        dest="/media/电影/疯狂动物城2 (2025)/疯狂动物城2.mkv",
        download_hash="abc123",
    )

    assert plan.eligible is True
    assert plan.reasons == []


def test_build_delete_plan_rejects_tv_content():
    plan = build_delete_plan(
        transfer_id=2,
        title="示例剧集",
        year="2025",
        media_type="电视剧",
        mode="link",
        src="/media/qbdownloads/电视剧/示例剧集",
        dest="/media/电视剧/示例剧集",
        seasons="S01",
        episodes="E01",
    )

    assert plan.eligible is False
    assert "当前版本仅支持电影" in plan.reasons
    assert "当前版本不支持电视剧或分集删除" in plan.reasons


def test_iter_empty_parent_candidates_stops_at_configured_root():
    candidates = iter_empty_parent_candidates(
        "/volume1/video/电影/动画电影/疯狂动物城2 (2025)/疯狂动物城2.mkv",
        ["/volume1/video/电影"],
    )

    assert [str(item) for item in candidates] == [
        "/volume1/video/电影/动画电影/疯狂动物城2 (2025)",
        "/volume1/video/电影/动画电影",
    ]


def test_filter_display_items_keeps_movies_and_deduplicates_same_title():
    items = [
        {"title": "疯狂动物城2", "year": "2025", "media_type": "电影", "eligible": True},
        {"title": "疯狂动物城2", "year": "2025", "media_type": "电影", "eligible": False},
        {"title": "夜色正浓", "year": "2026", "media_type": "电视剧", "eligible": False},
    ]

    result = filter_display_items(
        items,
        keyword="",
        movies_only=True,
        eligible_only=False,
        dedupe_titles=True,
        limit=20,
    )

    assert result == [
        {"title": "疯狂动物城2", "year": "2025", "media_type": "电影", "eligible": True},
    ]


def test_filter_display_items_filters_by_keyword_across_paths():
    items = [
        {
            "title": "至尊马蒂",
            "year": "2025",
            "media_type": "电影",
            "src": "/media/qbdownloads/电影/外语电影/Marty.Supreme.2025.mkv",
            "dest": "/media/电影/外语电影/至尊马蒂 (2025)/至尊马蒂 (2025).mkv",
            "eligible": True,
        },
        {
            "title": "示例电影",
            "year": "2024",
            "media_type": "电影",
            "src": "/media/qbdownloads/电影/示例电影.mkv",
            "dest": "/media/电影/示例电影/示例电影.mkv",
            "eligible": True,
        },
    ]

    result = filter_display_items(
        items,
        keyword="marty",
        movies_only=True,
        eligible_only=False,
        dedupe_titles=True,
        limit=20,
    )

    assert [item["title"] for item in result] == ["至尊马蒂"]


def test_filter_display_items_can_hide_ineligible_items():
    items = [
        {"title": "可删电影", "year": "2025", "media_type": "电影", "eligible": True},
        {"title": "不可删电影", "year": "2025", "media_type": "电影", "eligible": False},
    ]

    result = filter_display_items(
        items,
        keyword="",
        movies_only=True,
        eligible_only=True,
        dedupe_titles=True,
        limit=20,
    )

    assert [item["title"] for item in result] == ["可删电影"]


def test_is_stale_history_candidate_requires_all_live_targets_gone():
    assert is_stale_history_candidate(
        src_exists=False,
        dest_exists=False,
        media_item_count=0,
    ) is True
    assert is_stale_history_candidate(
        src_exists=True,
        dest_exists=False,
        media_item_count=0,
    ) is False


def test_slice_page_items_returns_expected_window_and_total_pages():
    items = [{"index": idx} for idx in range(1, 8)]
    page_items, total_pages, current_page = slice_page_items(items, page=2, page_size=3)

    assert page_items == [{"index": 4}, {"index": 5}, {"index": 6}]
    assert total_pages == 3
    assert current_page == 2
