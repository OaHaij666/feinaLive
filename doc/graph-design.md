# 两个 Graph 的设计

## 全景图

```
观众弹幕 ──→ HostBrain (过滤/缓冲/管理命令) ──→ enqueue 原始弹幕
                                                      │
                                                    消息队列
                                                      │
                     ┌────────────────────────────────┤
                     │                                 │
                     ▼                                 ▼
           ┌──────────────────┐            ┌──────────────────────┐
           │   SharedContext  │            │  PriorityMessageQueue │
           │                  │            │                      │
           │ _host_history ◄──┼────────────┤ HostGraph 写          │
           │ _game_history ◄──┼────────────┤ GameGraph 写          │
           │ _memory ◄────────┼────────────┤ MemorySummarizer 写  │
           └────────┬─────────┘            └──────────┬───────────┘
                    │                                 │
                    │ 读                               │ get()
                    ▼                                 ▼
           ┌──────────────────┐            ┌──────────────────────┐
           │    GameGraph      │            │     HostGraph         │
           │   (AI 的双手)     │            │   (AI 的嘴)           │
           │                  │            │                      │
           │ MCP 玩游戏        │            │ 消费队列              │
           │ 读 host_history   │            │ 主播 LLM 统一生成话术  │
           │ 决策时参考        │            │         ↓             │
           │ 主播说了什么      │            │  TTS 合成播放          │
           │                  │            │         ↓             │
           │ 需要解说时        │            │  写 SharedContext      │
           │ → enqueue commentary_request   │                      │
           └──────────────────┘            └──────────────────────┘

TTS 是主播 LLM 的"嘴"，不是独立的消息类型。
所有消息 → 主播 LLM 生成话术 → TTS 输出语音。
```

## GameGraph — AI 的双手

职责：读游戏状态 + 读主播互动上下文 → LLM 决策 → 操作游戏，偶尔请求主播解说。

写入 SharedContext：_game_history（每轮游戏操作）
读取 SharedContext：全部三项

```
_collect_data (并行读4项)
  ├── MCP 游戏状态
  ├── SharedContext._host_history  ← 主播说了什么
  ├── SharedContext._game_history  ← 自己上轮做了什么
  └── SharedContext._memory        ← 三层记忆(机制/策略/细节)

_build_prompt → 游戏状态转文本 + MCP tools + request_host_commentary

_llm_decide → LLM 生成 tool_calls

_execute_parallel
  ├── MCP 工具 → 执行游戏动作 → 写 _game_history
  └── request_host_commentary → 入消息队列 (pri=1, 间隔≥8秒, 不可跳过, 10秒过期)
      携带 key_points(草稿要点) + mood + reference_danmaku
```

## HostGraph — AI 的嘴

职责：消费队列 → 主播 LLM 统一生成话术 → TTS 播放 → 写 SharedContext。

三个消息类型，全部经同一个主播 LLM：

| msg_type | 谁生产 | 消息内容 | 主播 LLM 做什么 |
|----------|--------|---------|----------------|
| commentary_request | GameGraph | 解说要点(草稿)+情绪+弹幕参考 | 风格化解说 |
| danmaku | HostBrain enqueue | 观众弹幕原文 | 生成口语化回复 |
| gift_thanks | 礼物系统 | 礼物信息 | 生成感谢语 |

消费循环：

```
_host_loop:
  msg = queue.get()
  ├── commentary_request → _handle_commentary()
  │     prompt: 解说要点 + 情绪 + 弹幕参考 + 人设 + 主播历史
  │     → 主播 LLM 生成风格化解说 → TTS → 写 SharedContext
  │
  ├── danmaku → _handle_danmaku()
  │     prompt: 观众弹幕原文 + 人设 + 主播历史
  │     → 主播 LLM 生成口语化回复 → TTS → 写 SharedContext
  │
  └── gift_thanks → _handle_gift_thanks()
        prompt: 礼物信息 + 人设 + 主播历史
        → 主播 LLM 生成感谢语 → TTS → 写 SharedContext
```

写入 SharedContext：_host_history（每次都写 danmaku + 最终回复）
读取 SharedContext：_host_history（用作上下文，避免重复说话）

## HostBrain — 弹幕过滤器

职责：弹幕缓冲、管理命令过滤、sleep 模式、回复间隔控制、标记已回复。

不生成任何话，不调 LLM，不调 TTS。只把原始弹幕推入消息队列。

处理流程：
```
push_danmaku() → 过滤(管理命令/sleep/clear记忆) → 缓冲 → try_reply()
  → 检查间隔/睡眠/未回复
  → 标记为已回复 (SessionHistory)
  → enqueue 原始弹幕文本 (msg_type="danmaku")
```

## SharedContext — 两个 Graph 的桥梁

唯一目的：让 GameGraph 知道主播说了什么。

- _host_history (FIFO 50)：HostGraph 写，GameGraph 读
- _game_history (FIFO 30)：GameGraph 写，GameGraph 读
- _memory (core/important/recent)：MemorySummarizer 定时总结，GameGraph 读

## 消息队列防护

- 全局静音：/sleep 1 → 队列 mute，所有消息丢弃
- 同用户冷却：同一 uid 3秒内一条
- 队列满：priority 0/1 永不丢，priority 2 可丢，priority≥3 直接丢
- 消息取消：cancel_key，GameGraph 可取消过时解说
- 频率限制：game:commentary_request 4s、danmaku:danmaku 3s、gift:gift_thanks 10s
- 过期丢弃：commentary 10秒、danmaku 25秒

---

## 三条链路详解

### 链路一：新弹幕 → 主播回复

**完整调用链：**

```
B站弹幕服务器
  │ WebSocket
  ▼
BilibiliClient._on_danmaku()
  │ callback("danmaku", DanmakuData)
  ▼
router.py on_message()
  │ process_danmaku()
  ▼
danmaku_handler.py process_danmaku()
  │ brain.push_danmaku(msg_id, user, content, uid)
  │     ├── 检查 /clear 命令 → 清除用户记忆，return
  │     ├── 检查管理员命令 → admin_handler.sync_handle()，return
  │     ├── 检查 sleep 模式 → should_process_danmaku()，return
  │     └── 通过 → DanmakuInput 入 _danmaku_buffer
  │
  │ asyncio.create_task(_process_ai_reply)
  │     └── brain.try_reply()
  │         ├── 检查 _is_replying → 正在回复则跳过
  │         ├── 检查 sleep 模式
  │         ├── 检查回复间隔 (config.host_reply_interval)
  │         ├── get_unanswered() → 从 SessionHistory 查未回复
  │         └── _enqueue_danmaku(unanswered)
  │             ├── 取同一用户连续弹幕合并
  │             ├── history.mark_answered_batch(msg_ids)
  │             └── queue.put(Message(
  │                   priority=2 (PRIORITY_NORMAL),
  │                   source="danmaku",
  │                   msg_type="danmaku",
  │                   content=合并后的弹幕原文,
  │                   data={"user": user, "uid": uid, "msg_id": msg_id},
  │                   user_id=str(uid),
  │                   expire_at=now+25,
  │                ))
  ▼
PriorityMessageQueue
  │ 检查: 静音? 取消? 频率限制(danmaku:danmaku 3s)? 用户冷却(3s)? 队列满?
  │ 通过 → 入队
  ▼
HostGraph._host_loop()
  │ msg = await queue.get()
  │ msg.msg_type == "danmaku" → _handle_danmaku(msg)
  ▼
HostGraph._handle_danmaku(msg)
  │ 1. host_personality = get_host_system_prompt()     ← 菲娜人设
  │ 2. host_history = await shared_context.get_host_history_text(limit=5)  ← 最近5条互动
  │ 3. system_content = DANMAKU_REPLY_PROMPT.format(...)
  │ 4. spoken = await _llm_generate(system_content, "请回复弹幕。", max_tokens)
  │ 5. await _speak(spoken)   → TTS 合成播放
  │ 6. await shared_context.add_host_entry(danmaku=弹幕原文, reply=spoken)
  └── 7. await _on_reply(spoken)  ← 回调通知
```

**最终发给主播 LLM 的提示词：**

```
[system]
你是一个名叫菲娜的虚拟主播，正处于B站直播中。

【菲娜的性格特点】
- 说话像童话里的小女孩，用词温柔诗意
- 喜欢用"呀、呢、哦、唔、吧、吗"等语气词
- 自称"菲娜"
- 直播游玩"二重螺旋"这款游戏，游戏id叫"陈千千千千千语"

【菲娜的背景设定】
- 有一个叫"大魔法师"（也叫奥特赛德）的亲人，是说话最好听、最温柔的人
- 菲娜曾有妈妈，但妈妈已经不在了
- 菲娜喜欢蓝色，是天空和独角兽小姐鬃毛的颜色
- 菲娜喜欢蜂蜜吐司、热牛奶等甜食

【菲娜的说话风格】
- 句子较短，简洁而有韵律
- 喜欢把平常事物比喻成童话里的东西
- 回复前简要复述或概括用户弹幕内容（让观众知道这是在回复什么），但尽量避免完全一样地复读
- 回复控制在40字以内，像朋友聊天一样自然

【禁止事项】
- 不要重复用户说的话
- 不要说自己是AI或虚拟主播
- 不要一次回复过长
- 不要偏离童话感的人设
- 使用单纯的中文回复，回复不要加入动作描写，也不要有emoji类表情
- 如果遇到不会回答的问题可以说自己不知道，难以回答的问题可以拒绝回答

【观众说】
主播主播，这个boss好难打呀

【你刚才的互动】
观众: 这个小怪好可爱 | 主播: 唔，是有点像小精灵呢
观众: 加油加油 | 主播: 谢谢你的鼓励呀，菲娜会努力的

请回复这条弹幕:
- 用第一人称
- 口语化、自然
- 可以加入口癖和情感词
- 长度控制在 20-50 字

[user]
请回复弹幕。
```

---

### 链路二：游戏解说请求

**完整调用链：**

```
GameGraph._game_loop()  (每 poll_interval 秒一轮)
  │
  ▼
_collect_data(state)  (并行4项)
  ├── adapter.get_state()                    → state.game_state
  ├── shared_context.get_host_history_text(limit=10)  → state.host_history_text
  ├── shared_context.get_game_history_text(limit=10)  → state.game_history_text
  └── shared_context.get_memory()            → state.core/important/recent_memory
  │
  ▼
_build_prompt(state)
  │ 1. game_state_text = state.game_state.to_prompt_text()
  │ 2. tools = [REQUEST_HOST_COMMENTARY_TOOL] + adapter.get_tools_definition()
  │ 3. system_content = GAME_SYSTEM_PROMPT.format(...)
  └── state._system_content = system_content
  │
  ▼
_llm_decide(state)
  │ messages = [system(state._system_content), user("请决策下一步操作。")]
  │ model = config.game_model  ← 注意：用的是游戏模型，不是主播模型
  │ response = await ai.chat(request)
  └── _parse_tool_calls(state)  ← 解析 JSON 中的 tool_calls
  │
  ▼
_execute_parallel(state)
  │ 对每个 tool_call:
  ├── name == "request_host_commentary" → _handle_commentary_request(params)
  │     ├── 检查解说间隔 (min_commentary_interval=8s)
  │     └── queue.put(Message(
  │           priority=1 (PRIORITY_HIGH),
  │           source="game",
  │           msg_type="commentary_request",
  │           content=key_points 用 " | " 连接,
  │           data={"key_points": [...], "mood": "excited", "reference_danmaku": "..."},
  │           cancel_key=f"commentary_{game_id}_{timestamp}",
  │           expire_at=now+10,
  │           allow_skip=False,
  │        ))
  └── 其他 → _handle_game_action(name, params)
        ├── adapter.execute_action(action)
        └── shared_context.add_game_entry(action, params, result)
  ▼
PriorityMessageQueue
  │ 检查: 静音? 取消? 频率限制(game:commentary_request 4s)?
  │ priority=1 永不丢弃，allow_skip=False 永不过期跳过
  ▼
HostGraph._host_loop()
  │ msg = await queue.get()
  │ msg.msg_type == "commentary_request" → _handle_commentary(msg)
  ▼
HostGraph._handle_commentary(msg)
  │ 1. key_points = msg.data["key_points"]     ← 游戏AI的草稿要点
  │ 2. mood = msg.data["mood"]                 ← 建议情绪
  │ 3. reference_danmaku = msg.data["reference_danmaku"]  ← 参考弹幕
  │ 4. host_personality = get_host_system_prompt()
  │ 5. host_history = await shared_context.get_host_history_text(limit=5)
  │ 6. system_content = COMMENTARY_SYSTEM_PROMPT.format(...)
  │ 7. spoken = await _llm_generate(system_content, "请生成解说。", max_tokens)
  │ 8. await _speak(spoken)   → TTS 合成播放
  │ 9. await shared_context.add_host_entry(
  │        danmaku=reference_danmaku or f"[游戏解说-{mood}]",
  │        reply=spoken,
  │     )
  └── 10. await _on_reply(spoken)
```

**游戏 LLM 收到的提示词（决策用）：**

```
[system]
你是游戏策略AI，控制主播玩游戏并与观众互动。

【游戏状态】
当前楼层: 15
玩家HP: 45/80
手牌: [打击, 打击, 防御, 旋风斩, 重击]
敌人: 尖刺史莱姆 (HP: 30/30)
敌人意图: 攻击 12点
...

【主播近期互动】
观众: 主播加油 | 主播: 谢谢你的鼓励呀，菲娜会努力的
观众: 这个boss好难打呀 | 主播: 唔，确实有点棘手呢...

【你刚才的操作】
play_card(card="防御") -> success
play_card(card="打击") -> success

【核心记忆 - 游戏机制与规则】
旋风斩消耗所有费用，按消耗费用造成伤害
防御提供5点格挡
...

【重要记忆 - 牌组/遗物/策略】
当前牌组: 15张，含2张旋风斩
遗物: 燃烧之血(每回合结束回2HP)
...

【近期记忆 - 具体操作细节】
第13层: 打击→打击→防御，击败了2只小史莱姆
第14层: 旋风斩(3费)→打击，击败精英怪
...

请根据以上信息决策下一步操作。你可以:
1. 使用游戏工具执行游戏动作
2. 使用 request_host_commentary 让主播解说

注意:
- 考虑主播刚才的互动内容，决策要符合直播间氛围
- 关键时刻要让主播解说
- 不要过于频繁地要求解说

[user]
请决策下一步操作。
```

**游戏 LLM 可能返回的 tool_call：**

```json
{
  "tool_calls": [
    {
      "name": "request_host_commentary",
      "params": {
        "key_points": [
          "尖刺史莱姆要攻击了，伤害12点",
          "我HP只剩45，比较危险",
          "手里有旋风斩可以清场"
        ],
        "mood": "nervous",
        "reference_danmaku": "这个boss好难打呀"
      }
    },
    {
      "name": "play_card",
      "params": {"card": "防御"}
    }
  ]
}
```

**最终发给主播 LLM 的提示词（风格化解说）：**

```
[system]
你是一个名叫菲娜的虚拟主播，正处于B站直播中。

【菲娜的性格特点】
- 说话像童话里的小女孩，用词温柔诗意
- 喜欢用"呀、呢、哦、唔、吧、吗"等语气词
- 自称"菲娜"
- 直播游玩"二重螺旋"这款游戏，游戏id叫"陈千千千千千语"

...（人设同上，省略）...

【解说要点】
- 尖刺史莱姆要攻击了，伤害12点
- 我HP只剩45，比较危险
- 手里有旋风斩可以清场

【建议情绪】
nervous

【你刚才的互动】
观众: 主播加油 | 主播: 谢谢你的鼓励呀，菲娜会努力的
观众: 这个boss好难打呀 | 主播: 唔，确实有点棘手呢...

【可参考弹幕】
这个boss好难打呀

请根据以上要点生成一段风格化解说:
- 用第一人称
- 口语化、自然
- 可以加入口癖和情感词
- 长度控制在 20-50 字
- 不要重复要点原文，用自己的风格重新表达

[user]
请生成解说。
```

---

### 链路三：礼物感谢

**完整调用链：**

```
B站弹幕服务器
  │ WebSocket
  ▼
BilibiliClient._on_gift()
  │ callback("gift", GiftData)
  ▼
router.py on_message()
  │ 广播礼物消息到前端 WebSocket  ← 仅此而已！
  │
  ⚠️ 目前没有代码将 gift_thanks 消息入队！
  ⚠️ HostGraph._handle_gift_thanks() 已实现但无生产者。
  ⚠️ 需要在 router.py 或 danmaku_handler.py 中补充礼物入队逻辑。
```

**预期完整链路（待实现）：**

```
BilibiliClient._on_gift()
  │ callback("gift", GiftData)
  ▼
router.py on_message()  (或 danmaku_handler.py)
  │ 补充: queue.put(Message(
  │     priority=3 (PRIORITY_LOW),
  │     source="gift",
  │     msg_type="gift_thanks",
  │     content="用户名 送出 小电视 x1",
  │     data={"gift_info": "用户名 送出 小电视 x1", "user": "用户名", "uid": uid},
  │     expire_at=now+30,
  │ ))
  ▼
PriorityMessageQueue
  │ 频率限制: gift:gift_thanks 10s
  ▼
HostGraph._host_loop()
  │ msg.msg_type == "gift_thanks" → _handle_gift_thanks(msg)
  ▼
HostGraph._handle_gift_thanks(msg)
  │ 1. gift_info = msg.data.get("gift_info", msg.content)
  │ 2. host_personality = get_host_system_prompt()
  │ 3. host_history = await shared_context.get_host_history_text(limit=3)
  │ 4. system_content = GIFT_THANKS_PROMPT.format(...)
  │ 5. spoken = await _llm_generate(system_content, "请生成感谢语。", 80)
  │ 6. await _speak(spoken)   → TTS 合成播放
  │ 7. await shared_context.add_host_entry(
  │        danmaku=f"[{msg.source}] {gift_info}",
  │        reply=spoken,
  │     )
  └── 8. await _on_reply(spoken)
```

**预期发给主播 LLM 的提示词（礼物感谢）：**

```
[system]
你是一个名叫菲娜的虚拟主播，正处于B站直播中。

【菲娜的性格特点】
- 说话像童话里的小女孩，用词温柔诗意
- 喜欢用"呀、呢、哦、唔、吧、吗"等语气词
- 自称"菲娜"
- 直播游玩"二重螺旋"这款游戏，游戏id叫"陈千千千千千语"

...（人设同上，省略）...

【你刚才的互动】
观众: 这个boss好难打呀 | 主播: 唔，确实有点棘手呢...

观众送了礼物: 小明 送出 小电视 x1

请生成一段感谢语:
- 用第一人称
- 口语化、自然
- 长度控制在 15-30 字
- 感谢要真诚不油腻

[user]
请生成感谢语。
```

---

### 三条链路对比

| | 弹幕回复 | 游戏解说 | 礼物感谢 |
|---|---|---|---|
| **入口** | BilibiliClient._on_danmaku | GameGraph._game_loop | BilibiliClient._on_gift |
| **中间层** | danmaku_handler → HostBrain | GameGraph._collect_data → _llm_decide | ⚠️ 缺失 |
| **入队** | HostBrain._enqueue_danmaku | GameGraph._handle_commentary_request | ⚠️ 缺失 |
| **priority** | 2 (NORMAL) | 1 (HIGH) | 3 (LOW) |
| **频率限制** | 3秒 | 4秒 | 10秒 |
| **过期** | 25秒 | 10秒 | 30秒 |
| **allow_skip** | True | False | True |
| **HostGraph handler** | _handle_danmaku | _handle_commentary | _handle_gift_thanks |
| **host_history limit** | 5 | 5 | 3 |
| **max_tokens** | config.host_max_tokens | config.host_max_tokens | 80 |
| **SharedContext 写入** | danmaku=弹幕原文, reply=回复 | danmaku=参考弹幕或[游戏解说-mood], reply=解说 | danmaku=[gift] 礼物信息, reply=感谢语 |
| **实现状态** | ✅ 完整 | ✅ 完整 | ⚠️ 消费端已实现，生产端未接入 |
