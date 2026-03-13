from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from app import schemas
from app.core.config import settings
from app.db import SessionFactory
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.db.mediaserver_oper import MediaServerOper
from app.db.models.mediaserver import MediaServerItem
from app.db.transferhistory_oper import TransferHistoryOper
from app.helper.downloader import DownloaderHelper
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import NotificationType

from .core import build_delete_plan, iter_empty_parent_candidates


class MediaOneDelete(_PluginBase):
    plugin_name = "联动一键删除"
    plugin_desc = "在 MoviePilot 内联动删除 qBittorrent 任务、源文件、媒体库文件和媒体映射。"
    plugin_icon = "delete.jpg"
    plugin_version = "0.1.1"
    plugin_author = "Codex"
    author_url = "https://github.com"
    plugin_config_prefix = "mediaonedelete_"
    plugin_order = 66
    auth_level = 1

    _enabled = False
    _notify = True
    _search_keyword = ""
    _result_limit = 20
    _delete_transfer_history = True
    _delete_download_history = True

    def init_plugin(self, config: dict = None):
        self._transferhis = TransferHistoryOper()
        self._downloadhis = DownloadHistoryOper()
        self._mediaserver_oper = MediaServerOper()
        self._downloader_helper = DownloaderHelper()
        self._mediaserver_helper = MediaServerHelper()

        if config:
            self._enabled = bool(config.get("enabled"))
            self._notify = bool(config.get("notify", True))
            self._search_keyword = (config.get("search_keyword") or "").strip()
            self._result_limit = int(config.get("result_limit") or 20)
            self._delete_transfer_history = bool(config.get("delete_transfer_history", True))
            self._delete_download_history = bool(config.get("delete_download_history", True))

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/remove",
                "endpoint": self.remove_media,
                "methods": ["POST"],
                "summary": "联动删除媒体",
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用插件"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "notify", "label": "发送通知"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "delete_transfer_history",
                                            "label": "清理整理历史",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "delete_download_history",
                                            "label": "清理下载历史",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 8},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "search_keyword",
                                            "label": "搜索关键词",
                                            "placeholder": "留空显示最近整理的电影",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "result_limit",
                                            "label": "结果数量",
                                            "placeholder": "20",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "warning",
                                            "variant": "tonal",
                                            "text": "当前版本仅支持电影。保存配置后，进入插件详情页查看候选项并点击“彻底删除”。删除会同时处理 qBittorrent、源文件、媒体库文件和 MoviePilot 残留映射。",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "notify": True,
            "search_keyword": "",
            "result_limit": 20,
            "delete_transfer_history": True,
            "delete_download_history": True,
        }

    def get_page(self) -> List[dict]:
        if not self._enabled:
            return [self._empty_page("插件未启用，先到配置页开启后再使用。")]

        items = self._collect_candidates()
        if not items:
            return [self._empty_page("没有找到可展示的电影整理记录。")]

        cards: List[dict] = []
        for item in items:
            delete_button = {
                "component": "VBtn",
                "props": {
                    "color": "error",
                    "variant": "tonal",
                    "disabled": not item["eligible"],
                },
                "text": "彻底删除",
            }
            if item["eligible"]:
                delete_button["events"] = {
                    "click": {
                        "api": f"plugin/{self.__class__.__name__}/remove",
                        "method": "post",
                        "params": {
                            "transfer_id": item["transfer_id"],
                            "apikey": settings.API_TOKEN,
                        },
                    }
                }

            cards.append(
                {
                    "component": "VCard",
                    "props": {"class": "mb-3"},
                    "content": [
                        {
                            "component": "VCardTitle",
                            "text": f"{item['title']} ({item['year']})",
                        },
                        {
                            "component": "VCardText",
                            "text": f"类型：{item['media_type']} | 整理方式：{item['mode']}",
                        },
                        {
                            "component": "VCardText",
                            "text": f"库路径：{item['dest']}",
                        },
                        {
                            "component": "VCardText",
                            "text": f"源路径：{item['src'] or '未记录'}",
                        },
                        {
                            "component": "VCardText",
                            "text": f"下载哈希：{item['download_hash'] or '未记录'}",
                        },
                        {
                            "component": "VCardText",
                            "text": f"删除资格：{'可删除' if item['eligible'] else '不可删除'}",
                        },
                        {
                            "component": "VCardText",
                            "text": f"说明：{item['reason_text']}",
                        },
                        {
                            "component": "VCardActions",
                            "content": [delete_button],
                        },
                    ],
                }
            )
        return cards

    def remove_media(self, transfer_id: int, apikey: str):
        if apikey != settings.API_TOKEN:
            return schemas.Response(success=False, message="API密钥错误")

        transfer = self._transferhis.get(int(transfer_id))
        if not transfer:
            return schemas.Response(success=False, message="未找到整理记录")

        item = self._build_candidate(transfer)
        if not item["eligible"]:
            return schemas.Response(success=False, message=item["reason_text"])

        errors: List[str] = []
        download_hash = item["download_hash"]
        downloader_name = item["downloader"]
        if download_hash and downloader_name:
            if not self._delete_torrent(download_hash, downloader_name):
                errors.append("qBittorrent任务删除失败")

        src_deleted = self._delete_path(item["src"]) if item["src"] else True
        if not src_deleted and item["src"] and Path(item["src"]).exists():
            errors.append("源文件删除失败")

        dest_deleted = self._delete_path(item["dest"])
        if not dest_deleted and Path(item["dest"]).exists():
            errors.append("媒体库文件删除失败")

        if Path(item["src"]).exists():
            errors.append("源文件仍存在")
        if Path(item["dest"]).exists():
            errors.append("媒体库文件仍存在")

        if errors:
            return schemas.Response(success=False, message="；".join(dict.fromkeys(errors)))

        self._cleanup_empty_dirs(item["src"])
        self._cleanup_empty_dirs(item["dest"])
        self._cleanup_media_rows(item["dest"], item["title"], item["year"], item["media_type"])

        if self._delete_transfer_history:
            self._transferhis.delete(transfer.id)

        download_history = item.get("download_history")
        if self._delete_download_history and download_history:
            self._downloadhis.delete_history(download_history.id)

        self._refresh_emby()

        if self._notify:
            self.post_message(
                mtype=NotificationType.Plugin,
                title="【联动一键删除】",
                text=f"{item['title']} ({item['year']}) 已完成联动删除",
            )
        return schemas.Response(success=True, message="联动删除完成")

    def stop_service(self):
        return

    def _collect_candidates(self) -> List[dict]:
        limit = max(1, min(self._result_limit, 50))
        if self._search_keyword:
            records = self._transferhis.get_by_title(self._search_keyword)[:limit]
        else:
            records = self._transferhis.list_by_date("1970-01-01 00:00:00")[:limit]
        candidates = []
        for transfer in records:
            candidates.append(self._build_candidate(transfer))
        return candidates

    def _build_candidate(self, transfer) -> dict:
        media_items = self._find_media_items(transfer.dest, transfer.title, transfer.year, transfer.type)
        download_history = None
        if transfer.download_hash:
            download_history = self._downloadhis.get_by_hash(transfer.download_hash)
        elif transfer.src:
            download_history = self._downloadhis.get_by_path(transfer.src)

        plan = build_delete_plan(
            transfer_id=transfer.id,
            title=transfer.title,
            year=transfer.year,
            media_type=transfer.type,
            mode=transfer.mode,
            src=transfer.src,
            dest=transfer.dest,
            seasons=transfer.seasons,
            episodes=transfer.episodes,
            download_hash=transfer.download_hash or (download_history.download_hash if download_history else ""),
            item_id=media_items[0].item_id if len(media_items) == 1 else "",
        )

        if len(media_items) > 1:
            plan.eligible = False
            plan.reasons.append("媒体映射存在多条记录")

        return {
            "transfer_id": transfer.id,
            "title": transfer.title,
            "year": transfer.year or "",
            "media_type": transfer.type,
            "mode": transfer.mode,
            "src": transfer.src or "",
            "dest": transfer.dest or "",
            "download_hash": plan.download_hash,
            "item_id": plan.item_id,
            "eligible": plan.eligible,
            "reasons": plan.reasons,
            "reason_text": "；".join(plan.reasons) if plan.reasons else "记录完整，可执行联动删除",
            "downloader": transfer.downloader or (download_history.downloader if download_history else ""),
            "download_history": download_history,
        }

    def _find_media_items(self, dest: str, title: str, year: str, media_type: str) -> List[MediaServerItem]:
        session = SessionFactory()
        try:
            query = session.query(MediaServerItem)
            exact = query.filter(MediaServerItem.path == dest).all()
            if exact:
                return exact
            return query.filter(
                MediaServerItem.title == title,
                MediaServerItem.year == str(year),
                MediaServerItem.item_type == media_type,
            ).all()
        finally:
            session.close()

    def _delete_torrent(self, download_hash: str, downloader_name: str) -> bool:
        try:
            service = self._downloader_helper.get_service(name=downloader_name)
            if not service or not service.instance:
                logger.error("未找到下载器服务：%s", downloader_name)
                return False
            result = service.instance.remove_torrents(
                hashs=download_hash,
                delete_file=True,
                downloader=downloader_name,
            )
            return bool(result)
        except Exception as err:
            logger.error("删除下载任务失败：%s", err, exc_info=True)
            return False

    @staticmethod
    def _delete_path(path_str: str) -> bool:
        if not path_str:
            return True
        path = Path(path_str)
        if not path.exists():
            return True
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
        except Exception as err:
            logger.error("删除路径失败 %s: %s", path, err, exc_info=True)
            return False

    @staticmethod
    def _cleanup_empty_dirs(path_str: str):
        if not path_str:
            return
        stop_paths = ["/media", "/media/电影", "/media/电视剧", "/media/动漫", "/media/qbdownloads"]
        for candidate in iter_empty_parent_candidates(path_str, stop_paths):
            try:
                if candidate.exists() and candidate.is_dir() and not any(candidate.iterdir()):
                    candidate.rmdir()
            except Exception:
                break

    def _cleanup_media_rows(self, dest: str, title: str, year: str, media_type: str):
        session = SessionFactory()
        try:
            deleted = session.query(MediaServerItem).filter(MediaServerItem.path == dest).delete()
            if not deleted:
                session.query(MediaServerItem).filter(
                    MediaServerItem.title == title,
                    MediaServerItem.year == str(year),
                    MediaServerItem.item_type == media_type,
                ).delete()
            session.commit()
        except Exception as err:
            session.rollback()
            logger.error("清理媒体映射失败：%s", err, exc_info=True)
        finally:
            session.close()

    def _refresh_emby(self):
        services = self._mediaserver_helper.get_services(name_filters=["Emby"])
        if not services:
            return
        for _, service in services.items():
            try:
                if hasattr(service.instance, "refresh_root_library"):
                    service.instance.refresh_root_library()
            except Exception as err:
                logger.error("刷新Emby失败：%s", err, exc_info=True)

    @staticmethod
    def _empty_page(text: str) -> dict:
        return {
            "component": "div",
            "text": text,
            "props": {"class": "text-center"},
        }
