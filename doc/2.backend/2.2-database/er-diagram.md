# 数据库 ER 图与表结构

## 数据库概述

飞娜直播间使用 MySQL 作为数据库，通过 SQLAlchemy ORM 进行数据访问。数据库连接信息由配置文件指定。

## ER 图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              飞娜直播间 ER 图                                        │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   ┌─────────────────────────────┐                                                  │
│   │        user_profiles        │                                                  │
│   │        (用户画像表)          │                                                  │
│   ├─────────────────────────────┤                                                  │
│   │ PK  user_id       VARCHAR(50) │                                                │
│   │     username      VARCHAR(100)│                                                │
│   │     danmaku_count  INTEGER    │                                                │
│   │     interaction_count INTEGER │                                                │
│   │     key_topics     TEXT       │                                                │
│   │     impression     TEXT       │                                                │
│   │     long_term_memory TEXT     │                                                │
│   │     recent_messages TEXT      │                                                │
│   │     last_danmaku   TEXT       │                                                │
│   │     last_interaction INTEGER  │                                                │
│   │     last_summary_count INTEGER│                                                │
│   │     created_at     INTEGER    │                                                │
│   └─────────────────────────────┘                                                  │
│                                                                                     │
│                                                                                     │
│   ┌─────────────────────────────┐       ┌─────────────────────────────┐            │
│   │         up_videos           │       │         playlist            │            │
│   │       (UP主视频表)          │       │       (播放列表表)          │            │
│   ├─────────────────────────────┤       ├─────────────────────────────┤            │
│   │ PK  id           INTEGER    │       │ PK  id           INTEGER    │            │
│   │ UNI bvid         VARCHAR(20)│       │ UNI bvid         VARCHAR(20)│            │
│   │     title        VARCHAR(255)│      │     title        VARCHAR(255)│           │
│   │     up_name      VARCHAR(100)│      │     artist       VARCHAR(100)│           │
│   │ IDX up_uid       BIGINT     │       │     enabled      BOOLEAN    │            │
│   │     duration     INTEGER    │       │     created_at   DATETIME   │            │
│   │     cover_url    VARCHAR(500)│      └─────────────────────────────┘            │
│   │     fetched_at   DATETIME   │                                                    │
│   └─────────────────────────────┘                                                    │
│                                                                                     │
│                                                                                     │
│   图例说明:                                                                         │
│   PK  = 主键 (Primary Key)                                                         │
│   UNI = 唯一索引 (Unique)                                                          │
│   IDX = 普通索引 (Index)                                                           │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## 表关系说明

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              表关系说明                                              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   user_profiles (用户画像)                                                          │
│   │                                                                                 │
│   │ 存储每个用户与 AI 主播的互动历史和画像信息                                       │
│   │ 用于 AI 回复时提供个性化上下文                                                  │
│   │                                                                                 │
│   └── 独立表，无外键关联                                                            │
│                                                                                     │
│                                                                                     │
│   up_videos (UP主视频)                                                              │
│   │                                                                                 │
│   │ 存储信任 UP主发布的视频信息                                                     │
│   │ 用于点歌时快速搜索匹配                                                          │
│   │                                                                                 │
│   └── 独立表，无外键关联                                                            │
│                                                                                     │
│                                                                                     │
│   playlist (播放列表)                                                               │
│   │                                                                                 │
│   │ 存储预备歌单，即预先审核过的歌曲列表                                            │
│   │ 点歌时优先从此表匹配                                                            │
│   │                                                                                 │
│   └── 独立表，无外键关联                                                            │
│                                                                                     │
│   注意：当前设计为无关联的独立表，未来可考虑添加关联                                 │
│   - up_videos.up_uid 可关联到 user_profiles.user_id                               │
│   - playlist.bvid 可关联到 up_videos.bvid                                          │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## 索引设计

| 表名 | 索引名 | 字段 | 类型 | 说明 |
|-----|-------|------|------|------|
| user_profiles | pk_user_profiles | user_id | 主键 | 用户唯一标识 |
| up_videos | pk_up_videos | id | 主键 | 自增主键 |
| up_videos | uq_bvid | bvid | 唯一 | BV号唯一 |
| up_videos | idx_up_uid | up_uid | 普通 | 按UP主查询 |
| playlist | pk_playlist | id | 主键 | 自增主键 |
| playlist | uq_bvid | bvid | 唯一 | BV号唯一 |

## 数据库连接配置

```yaml
# config.yaml
database:
  url: "sqlite+aiosqlite:///./feinalive.db"
```

**连接字符串格式**：

```
sqlite+aiosqlite:///./数据库文件路径
```

**异步驱动**：使用 `aiosqlite` 作为 SQLite 的异步驱动。

## SQLAlchemy 模型定义

```python
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class UserProfileDB(Base):
    __tablename__ = "user_profiles"
    
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), default="")
    danmaku_count: Mapped[int] = mapped_column(Integer, default=0)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0)
    key_topics: Mapped[str] = mapped_column(Text, default="[]")
    impression: Mapped[str] = mapped_column(Text, default="")
    long_term_memory: Mapped[str] = mapped_column(Text, default="")
    recent_messages: Mapped[str] = mapped_column(Text, default="[]")
    last_danmaku: Mapped[str] = mapped_column(Text, default="")
    last_interaction: Mapped[float] = mapped_column(Integer, default=0)
    last_summary_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Integer, default=0)
```

## 数据库初始化

```python
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

应用启动时会自动创建所有表。

## 相关文档

- [用户画像表详解](./table-user-profile.md)
- [UP主视频表详解](./table-up-video.md)
- [播放列表表详解](./table-playlist.md)
