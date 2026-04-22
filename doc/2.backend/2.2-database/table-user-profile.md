# 用户画像表 (user_profiles)

## 表概述

用户画像表存储每个用户与 AI 主播的互动历史和个性化信息，用于 AI 回复时提供上下文，实现个性化对话体验。

## 表结构

| 字段名 | 数据类型 | 约束 | 默认值 | 说明 |
|-------|---------|------|-------|------|
| user_id | VARCHAR(50) | PRIMARY KEY | - | 用户唯一标识（B站UID） |
| username | VARCHAR(100) | NOT NULL | "" | 用户昵称 |
| danmaku_count | INTEGER | NOT NULL | 0 | 发送弹幕总数 |
| interaction_count | INTEGER | NOT NULL | 0 | 与AI互动次数 |
| key_topics | TEXT | NOT NULL | "[]" | 关键话题（JSON数组） |
| impression | TEXT | NOT NULL | "" | AI对用户的印象 |
| long_term_memory | TEXT | NOT NULL | "" | 长期记忆摘要 |
| recent_messages | TEXT | NOT NULL | "[]" | 近期对话记录（JSON数组） |
| last_danmaku | TEXT | NOT NULL | "" | 最后一条弹幕内容 |
| last_interaction | INTEGER | NOT NULL | 0 | 最后互动时间戳 |
| last_summary_count | INTEGER | NOT NULL | 0 | 上次摘要时的互动数 |
| created_at | INTEGER | NOT NULL | 0 | 创建时间戳 |

## 字段详解

### user_id

```
类型: VARCHAR(50)
约束: PRIMARY KEY
说明: 用户唯一标识，通常为B站用户UID
```

**使用示例**：
- B站用户UID: "123456789"
- 测试用户: "test_user_001"

---

### username

```
类型: VARCHAR(100)
默认值: ""
说明: 用户昵称，用于AI回复时称呼用户
```

---

### danmaku_count

```
类型: INTEGER
默认值: 0
说明: 用户发送的弹幕总数，用于统计活跃度
```

**更新时机**：每次用户发送弹幕时 +1

---

### interaction_count

```
类型: INTEGER
默认值: 0
说明: 用户与AI的有效互动次数
```

**更新时机**：AI回复用户弹幕后 +1

---

### key_topics

```
类型: TEXT
默认值: "[]"
说明: 用户常讨论的话题关键词，JSON数组格式
```

**数据结构**：

```json
["游戏", "音乐", "编程"]
```

**更新逻辑**：由 LLM 分析对话内容后提取关键词

---

### impression

```
类型: TEXT
默认值: ""
说明: AI对用户的印象描述
```

**示例内容**：

```
用户是一个喜欢二次元文化的年轻人，经常来直播间点歌，性格开朗活泼。
喜欢周杰伦和陈奕迅的歌，偶尔会聊一些游戏相关的话题。
```

**更新逻辑**：定期由 LLM 根据对话历史生成摘要

---

### long_term_memory

```
类型: TEXT
默认值: ""
说明: 用户的长期记忆摘要
```

**与 impression 的区别**：
- `impression`：AI对用户的印象评价
- `long_term_memory`：客观的事实记录

---

### recent_messages

```
类型: TEXT
默认值: "[]"
说明: 最近的对话记录，JSON数组格式
```

**数据结构**：

```json
[
  {
    "role": "user",
    "content": "主播今天心情怎么样？",
    "timestamp": 1700000000
  },
  {
    "role": "assistant",
    "content": "心情很好呢！看到你们来我很开心~",
    "timestamp": 1700000001
  }
]
```

---

### last_danmaku

```
类型: TEXT
默认值: ""
说明: 用户最后发送的一条弹幕内容
```

---

### last_interaction

```
类型: INTEGER
默认值: 0
说明: 最后一次互动的时间戳（Unix时间戳）
```

---

### last_summary_count

```
类型: INTEGER
默认值: 0
说明: 上次生成摘要时的互动次数
```

**用途**：判断是否需要重新生成摘要

```
if interaction_count - last_summary_count >= 20:
    # 触发摘要生成
    generate_summary()
    last_summary_count = interaction_count
```

---

## 数据流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                    用户画像数据流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│    用户发送弹幕                                                 │
│         │                                                       │
│         ▼                                                       │
│    ┌─────────────────┐                                         │
│    │ danmaku_count++ │                                         │
│    │ last_danmaku更新│                                         │
│    └────────┬────────┘                                         │
│             │                                                   │
│             ▼                                                   │
│    ┌─────────────────┐                                         │
│    │   AI 回复弹幕   │                                         │
│    └────────┬────────┘                                         │
│             │                                                   │
│             ▼                                                   │
│    ┌─────────────────┐                                         │
│    │interaction_count++│                                       │
│    │recent_messages更新│                                       │
│    └────────┬────────┘                                         │
│             │                                                   │
│             ▼                                                   │
│    ┌─────────────────────────────────────────────────────┐     │
│    │              检查是否需要生成摘要                    │     │
│    │                                                     │     │
│    │   if interaction_count - last_summary_count >= 20:  │     │
│    │       ┌─────────────────────────────────────────┐   │     │
│    │       │         LLM 生成摘要                   │   │     │
│    │       │  - 更新 impression                     │   │     │
│    │       │  - 更新 long_term_memory               │   │     │
│    │       │  - 更新 key_topics                     │   │     │
│    │       │  - 更新 last_summary_count             │   │     │
│    │       └─────────────────────────────────────────┘   │     │
│    └─────────────────────────────────────────────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 使用场景

### 1. AI 回复时获取上下文

```python
user_profile = get_user_profile(user)
context = user_profile.get_memory_context()
# 将 context 加入 AI prompt
```

### 2. 个性化称呼

```python
username = user_profile.username
# AI 回复时使用: "你好，{username}！"
```

### 3. 记忆持久化

```python
# 应用启动时
await init_user_profiles()

# 应用关闭时
await save_all_profiles()
```

## 相关代码

- 表定义：[backend/apps/db.py](file:///c:\my_code\feinaLive\backend\apps\db.py)
- 用户画像管理：[backend/apps/ai/memory/user_profile.py](file:///c:\my_code\feinaLive\backend\apps\ai\memory\user_profile.py)
- 摘要生成：[backend/apps/ai/memory/summarizer.py](file:///c:\my_code\feinaLive\backend\apps\ai\memory\summarizer.py)
