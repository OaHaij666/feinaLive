"""测试LLM验证功能"""
import asyncio
import json
import logging

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.config import config

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BVID = "BV1UjxXzkEwZ"
MIN_DURATION_SECONDS = 60
MAX_DURATION_SECONDS = 8 * 60
MAX_COMMENTS = 3
MAX_COMMENT_LEN = 50


async def get_hot_comments(bvid: str) -> list[str]:
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
        logger.warning(f"  获取评论失败: {e}")
        return []


async def main():
    logger.info("=" * 50)
    logger.info(f"测试LLM验证: {BVID}")
    logger.info("=" * 50)

    ai = get_ai_client()
    logger.info(f"\n[配置检查]")
    logger.info(f"  API URL: {config.llm_api_url}")
    logger.info(f"  Model: {config.llm_model}")
    logger.info(f"  Available: {ai.available}")

    if not ai.available:
        logger.error("LLM配置不完整，请检查config.yaml")
        return

    from bilibili_api import video, Credential
    sessdata = config.bilibili_sessdata
    credential = Credential(sessdata=sessdata) if sessdata else None
    v = video.Video(bvid=BVID, credential=credential)

    logger.info(f"\n[获取视频信息]")
    info = await v.get_info()
    video_info = {
        "bvid": info.get("bvid"),
        "title": info.get("title"),
        "desc": info.get("desc", "")[:500],
        "duration_seconds": info.get("duration", 0),
    }
    logger.info(f"  标题: {video_info['title']}")
    logger.info(f"  时长: {video_info['duration_seconds']}秒 ({video_info['duration_seconds']//60}分{video_info['duration_seconds']%60}秒)")

    if video_info["duration_seconds"] > MAX_DURATION_SECONDS:
        logger.info(f"  时长超过{MAX_DURATION_SECONDS}秒，跳过LLM验证")
        return
    if video_info["duration_seconds"] < MIN_DURATION_SECONDS:
        logger.info(f"  时长不足{MIN_DURATION_SECONDS}秒，跳过LLM验证")
        return

    logger.info(f"\n[获取热门评论]")
    hot_comments = await get_hot_comments(BVID)
    logger.info(f"  热门评论: {hot_comments}")

    prompts = config.llm_prompts
    system_prompt = prompts.get(
        "music_verify",
        "判断视频是否为音乐视频，提取歌名和歌手。",
    )

    user_parts = [f"标题: {video_info['title']}"]
    if video_info.get("desc"):
        user_parts.append(f"简介: {video_info['desc']}")
    if hot_comments:
        user_parts.append(f"热门评论: {' | '.join(hot_comments)}")
    user_content = "\n".join(user_parts)

    logger.info(f"\n[发送给LLM的提示词]")
    logger.info("-" * 50)
    logger.info(f"[System]\n{system_prompt.strip()}")
    logger.info(f"\n[User]\n{user_content}")
    logger.info("-" * 50)

    logger.info(f"\n[LLM响应 - 流式]")
    request = ChatRequest(
        messages=[
            ChatMessage(role="system", content=system_prompt.strip()),
            ChatMessage(role="user", content=user_content),
        ],
        json_format=True,
        disable_thinking=True,
        stream=True,
    )

    full_content = ""
    async for chunk in ai.chat_stream(request):
        print(chunk, end="", flush=True)
        full_content += chunk
    print()

    logger.info(f"\n[解析结果]")
    try:
        start = full_content.find("{")
        end = full_content.rfind("}") + 1
        if start != -1 and end > 0:
            parsed = json.loads(full_content[start:end])
            logger.info(f"  is_music: {parsed.get('is_music')}")
            logger.info(f"  song_name: {parsed.get('song_name')}")
            logger.info(f"  artist: {parsed.get('artist')}")
    except Exception as e:
        logger.error(f"  解析失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
