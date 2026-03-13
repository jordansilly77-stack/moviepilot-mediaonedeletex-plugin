import importlib.util
from pathlib import Path
import sys


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins.v2"
    / "mediaonedelete"
    / "core.py"
)
SPEC = importlib.util.spec_from_file_location("mediaonedelete_core", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

build_delete_plan = MODULE.build_delete_plan
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
