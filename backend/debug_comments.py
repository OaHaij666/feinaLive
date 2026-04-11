import asyncio, json
from bilibili_api import video
from bilibili_api.comment import get_comments, CommentResourceType, OrderType

async def test():
    v = video.Video(bvid="BV1UjxXzkEwZ")
    aid = v.get_aid()

    page = await get_comments(aid, CommentResourceType.VIDEO, 1, order=OrderType.LIKE)
    replies = page.get("replies") or []
    print(f"replies: {len(replies)}条\n")

    for i, c in enumerate(replies):
        content = c.get("content", {})
        msg = content.get("message", "") if isinstance(content, dict) else ""
        like = c.get("like", 0)
        rcount = c.get("rcount", 0)  # 子回复数
        print(f"[{i}] 赞={like} rcount={rcount} len={len(msg)}")
        print(f"     {msg[:80]}")
        print()

asyncio.run(test())