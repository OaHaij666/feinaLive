"""LLM音乐验证服务"""

import json
import logging
from dataclasses import dataclass

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.config import config

logger = logging.getLogger(__name__)

MIN_DURATION_SECONDS = 60
MAX_DURATION_SECONDS = 8 * 60
MAX_COMMENTS = 3
MAX_COMMENT_LEN = 50


@dataclass
class LLMVerifyResult:
    is_music: bool
    song_name: str
    artist: str


class LLMMusicVerifier:
    def __init__(self):
        self._ai = get_ai_client()

    async def verify(self, bvid: str) -> LLMVerifyResult | None:
        if not self._ai.available:
            logger.warning("LLM配置不完整，跳过验证")
            return None
        try:
            info = await self._get_video_detail(bvid)
            if not info:
                logger.error(f"获取视频详情失败: {bvid}")
                return None
            if info["duration_seconds"] > MAX_DURATION_SECONDS:
                logger.info(f"视频时长超过{MAX_DURATION_SECONDS}秒，不交给LLM: {bvid}")
                return None
            if info["duration_seconds"] < MIN_DURATION_SECONDS:
                logger.info(f"视频时长不足{MIN_DURATION_SECONDS}秒，不交给LLM: {bvid}")
                return None
            comments = await self._get_hot_comments(bvid)
            result = await self._call_llm(info, comments, bvid)
            return result
        except Exception as e:
            logger.error(f"LLM验证失败 {bvid}: {e}")
            return None

    async def _get_video_detail(self, bvid: str) -> dict | None:
        from bilibili_api import video, Credential
        sessdata = config.bilibili_sessdata
        credential = Credential(sessdata=sessdata) if sessdata else None
        v = video.Video(bvid=bvid, credential=credential)
        info = await v.get_info()
        return {
            "bvid": info.get("bvid"),
            "title": info.get("title"),
            "desc": info.get("desc", "")[:500],
            "duration_seconds": info.get("duration", 0),
        }

    async def _get_hot_comments(self, bvid: str) -> list[str]:
        try:
            from bilibili_api import video, Credential
            from bilibili_api.comment import CommentResourceType, get_comments, OrderType
            sessdata = config.bilibili_sessdata
            credential = Credential(sessdata=sessdata) if sessdata else None
            v = video.Video(bvid=bvid, credential=credential)
            aid = v.get_aid()
            valid_comments = []
            for page_idx in range(1, 4):
                page = await get_comments(aid, CommentResourceType.VIDEO, page_idx, order=OrderType.LIKE)
                replies = page.get("replies") or []
                if not replies:
                    break
                for c in replies:
                    if len(valid_comments) >= MAX_COMMENTS:
                        break
                    content = c.get("content", {})
                    msg = content.get("message", "") if isinstance(content, dict) else str(content)
                    if msg:
                        if len(msg) > MAX_COMMENT_LEN:
                            msg = msg[:MAX_COMMENT_LEN]
                        valid_comments.append(msg)
                if len(valid_comments) >= MAX_COMMENTS:
                    break
            return valid_comments
        except Exception as e:
            logger.warning(f"获取评论失败 {bvid}: {e}")
            return []

    async def _call_llm(self, video_info: dict, comments: list[str], bvid: str) -> LLMVerifyResult | None:
        prompts = config.llm_prompts
        system_prompt = prompts.get(
            "music_verify",
            "你是一个音乐视频识别助手。判断视频是否为音乐视频，提取歌名和歌手。返回JSON格式：{\"is_music\": true/false, \"song_name\": \"歌名\", \"artist\": \"歌手\"}",
        )
        user_parts = [f"标题: {video_info['title']}"]
        if video_info.get("desc"):
            user_parts.append(f"简介: {video_info['desc']}")
        if comments:
            user_parts.append(f"热门评论: {' | '.join(comments)}")
        user_content = "\n".join(user_parts)
        request = ChatRequest(
            messages=[
                ChatMessage(role="system", content=system_prompt.strip()),
                ChatMessage(role="user", content=user_content),
            ],
            json_format=True,
        )
        resp = await self._ai.chat(request)
        if not resp or not resp.content:
            logger.warning(f"LLM返回为空")
            return None
        try:
            start = resp.content.find("{")
            end = resp.content.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("未找到JSON")
            parsed = json.loads(resp.content[start:end])
            return LLMVerifyResult(
                is_music=parsed.get("is_music", False),
                song_name=parsed.get("song_name", video_info["title"]),
                artist=parsed.get("artist", "未知"),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"解析LLM响应失败: {e}, raw: {resp.content}")
            return None


_verifier: LLMMusicVerifier | None = None


def get_llm_verifier() -> LLMMusicVerifier:
    global _verifier
    if _verifier is None:
        _verifier = LLMMusicVerifier()
    return _verifier
