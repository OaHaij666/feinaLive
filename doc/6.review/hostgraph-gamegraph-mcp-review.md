# HostGraph / GameGraph / MCP 游戏集成审查报告

## 审查概述

本报告针对飞娜直播间项目中新增的 HostGraph、GameGraph 及 MCP 游戏集成模块进行全面审查。该模块实现了 LLM 通过 MCP 协议玩游戏、LLM 解说游戏并回复弹幕的核心能力。

**审查日期**：2026-05-04
**审查范围**：`backend/apps/ai/` 下的 game_graph.py、host_graph.py、game_manager.py、game_router.py、shared_context.py、mcp/、messaging/、memory/game_memory.py
**审查方法**：代码审查、架构评审、文档一致性校验
**更新日期**：2026-05-04（第二轮修复后更新）

---

## 一、架构总览

### 1.1 双 Graph 架构

系统采用 GameGraph + HostGraph 双 Graph 架构，两者通过 SharedContext 共享状态，通过 PriorityMessageQueue 传递消息：

```
┌──────────────────────────────────────────────────────────────┐
│                    SharedContext (共享存储)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ 主播回答历史  │  │ 游戏操作历史  │  │ 三层记忆           │ │
│  │ (max 50)      │  │ (max 30)      │  │ core/imp/rec       │ │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘ │
└─────────┼──────────────────┼───────────────────┼─────────────┘
          │ HostGraph:读写    │ GameGraph:读写     │ 两者:读写
          │ GameGraph:只读    │                    │
          ▼                  ▼                    ▼
┌──────────────────┐  ┌──────────────────┐
│   HostGraph      │  │   GameGraph      │
│ 消费消息队列      │  │ MCP游戏决策       │
│ 统一话术生成+TTS  │  │ 产出:动作+消息入队 │
└──────────────────┘  └──────────────────┘
         ▲                    │
         │                    │ PriorityMessageQueue
         └────────────────────┘
```

**评价**: 双 Graph 架构设计合理，职责分离清晰。GameGraph 专注游戏决策，HostGraph 专注话术生成，通过消息队列解耦，避免了两个 LLM 同时 TTS 输出的冲突问题。

---

## 二、模块审查

### 2.1 GameGraph (game_graph.py, 661行)

#### 功能完整性 ✅

| 功能 | 状态 | 说明 |
|-----|------|------|
| MCP 游戏状态获取 | ✅ 已实现 | asyncio.gather 并行收集 |
| LLM 决策 | ✅ 已实现 | 支持 JSON 多格式解析 |
| 游戏动作执行 | ✅ 已实现 | 串行执行+随机抖动 |
| 解说请求 | ✅ 已实现 | request_host_commentary 工具 |
| 记忆更新 | ✅ 已实现 | request_memory_update 工具 |
| GAME_OVER 自动重启 | ✅ 已实现 | proceed → start_game → clear_memory |
| 非玩家回合等待 | ✅ 已实现 | poll_interval 轮询 |

#### 优点

1. **并行数据收集**: `_collect_data` 使用 `asyncio.gather` 并行获取游戏状态、主播历史、游戏历史、三层记忆，减少延迟
2. **多格式 JSON 解析**: `_normalize_tool_calls` 支持 `actions`、`tool_calls`、直接列表三种格式，兼容不同 LLM 的输出风格
3. **Markdown code block 提取**: `_parse_tool_calls` 能从 ` ```json ``` ` 包裹中提取 JSON，增强鲁棒性
4. **内置工具设计**: `request_host_commentary` 和 `request_memory_update` 作为内置工具，让游戏 LLM 能主动触发解说和记忆更新
5. **步进间隔控制**: `game_min_step_interval` 防止游戏操作过快

#### 问题与建议

| 编号 | 严重级别 | 问题描述 | 建议 | 状态 |
|-----|---------|---------|------|------|
| G1 | 🟡 中危 | `_game_loop` 中 GAME_OVER 处理硬编码 `character="IRONCLAD"`，不支持角色选择 | 从配置或 SharedContext 读取角色偏好 | ✅ 已修复：使用 `config.game_default_character` |
| G2 | 🟡 中危 | `_game_loop` 异常后固定 sleep 5秒，无指数退避 | 引入指数退避策略 | 待修复 |
| G3 | 🟢 低危 | `build_game_system_prompt` 中游戏规则硬编码为杀戮尖塔，不利于多游戏扩展 | 将游戏规则提取到适配器层 | 待修复 |
| G4 | 🟢 低危 | `_format_game_state` 是静态方法但与杀戮尖塔强耦合 | 移到 SlayTheSpireAdapter 中 | ✅ 已修复：移至 `SlayTheSpireAdapter.format_state_for_prompt`，`BaseGameAdapter` 提供默认实现 |
| G5 | 🟢 低危 | ~~`_last_commentary_time` 字段存在但未在代码中使用~~ | ~~确认是否冗余，若冗余则移除~~ | ❌ 审查结论有误：`_last_commentary_time` 实际在使用中，与 RateLimiter 是两层不同粒度的频率控制（GameGraph 层 15s vs 队列层 4s），无需移除 |
| G6 | 🟡 中危 | `_execute_parallel` 中游戏动作串行执行，但缺少单步失败后的跳过机制 | 添加单步超时和失败跳过逻辑 | ❌ 审查结论有误：串行执行的设计意图是先排出解说要求和记忆操作，剩余游戏操作在时间预算内逐步执行，失败后立即执行下一步，当前实现符合设计意图 |

---

### 2.2 HostGraph (host_graph.py, 277行)

#### 功能完整性 ✅

| 功能 | 状态 | 说明 |
|-----|------|------|
| 消息队列消费 | ✅ 已实现 | queue.get(timeout=5s) 阻塞等待 |
| 弹幕回复 | ✅ 已实现 | _handle_danmaku |
| 游戏解说 | ✅ 已实现 | _handle_commentary |
| 礼物感谢 | ⚠️ 空实现 | _handle_gift_thanks 框架已有，但上游未触发 |
| TTS 播放 | ✅ 已实现 | _speak 含最小间隔控制 |
| SharedContext 写回 | ✅ 已实现 | add_host_entry |

#### 优点

1. **统一话术生成**: 所有消息类型统一走主播 LLM，保证风格一致性
2. **TTS 最小间隔**: 3秒间隔避免语音重叠
3. **提示词模板化**: 三种消息类型各有独立提示词模板，清晰易维护
4. **超时等待**: queue.get(timeout=5s) 避免无限阻塞，便于优雅停止

#### 问题与建议

| 编号 | 严重级别 | 问题描述 | 建议 | 状态 |
|-----|---------|---------|------|------|
| H1 | 🟡 中危 | 礼物感谢功能框架已有但上游未触发，`_handle_gift_thanks` 不会被调用 | 在 danmaku_handler 中添加礼物事件入队逻辑 | ✅ 已修复：在 `bilibili/router.py` 的 `on_message` 回调中添加了礼物事件入队逻辑 |
| H2 | 🟢 低危 | `_llm_generate` 中 max_tokens 参数对 gift_thanks 硬编码为 80 | 提取为配置项 | 待修复 |
| H3 | 🟢 低危 | 缺少消息处理失败的回退机制（如 LLM 超时后的降级回复） | 添加超时降级逻辑 | 待修复 |
| H4 | 🟡 中危 | HostGraph 和 AIHostBrain 的 LangGraph 流程使用不同的记忆系统，可能导致主播人格不一致 | 考虑统一记忆来源或明确双路径的使用场景 | 待修复 |

---

### 2.3 SharedContext (shared_context.py, 266行)

#### 功能完整性 ✅

| 功能 | 状态 | 说明 |
|-----|------|------|
| 主播历史 FIFO | ✅ 已实现 | deque(maxlen=50)，asyncio.Lock 保护 |
| 游戏历史 FIFO | ✅ 已实现 | deque(maxlen=30)，asyncio.Lock 保护 |
| 三层记忆 | ✅ 已实现 | LongTermMemory dataclass |
| 记忆重写 | ✅ 已实现 | rewrite_memory |
| 搜索替换 | ✅ 已实现 | search_replace_memory (fuzzy模式) |
| 历史清理 | ✅ 已实现 | trim_histories |
| 全部清空 | ✅ 已实现 | clear_all_memory |

#### 优点

1. **线程安全**: 所有操作通过 `asyncio.Lock` 保护
2. **FIFO 自动淘汰**: deque(maxlen=N) 自动丢弃旧记录
3. **搜索替换**: fuzzy 模式支持模糊匹配，适应 LLM 输出的不确定性
4. **上下文摘要**: `get_context_summary` 提供 API 级别的状态查看

#### 问题与建议

| 编号 | 严重级别 | 问题描述 | 建议 | 状态 |
|-----|---------|---------|------|------|
| S1 | 🟡 中危 | `search_replace_memory` 的 fuzzy 匹配可能误替换，缺少确认机制 | 添加匹配置信度阈值或日志记录 | ✅ 已修复：`_handle_memory_update_request` 和 `_handle_commentary_request` 现在会通过 `add_game_entry` 将操作记录写入游戏历史，LLM 下一轮决策时可见 |
| S2 | 🟢 低危 | 主播历史和游戏历史的 maxlen 硬编码 | 提取为配置项 | ✅ 已修复：使用 `config.game_host_history_maxlen` 和 `config.game_game_history_maxlen` |
| S3 | 🟢 低危 | `trim_histories` 的 keep_seconds 参数为 300秒，可能清理过快 | 根据实际使用调整，或提取为配置 | 待修复 |

---

### 2.4 MCP 客户端与适配器 (mcp/)

#### MCPClient (client.py)

| 功能 | 状态 | 说明 |
|-----|------|------|
| JSON-RPC 2.0 通信 | ✅ 已实现 | HTTP POST 到 /mcp 端点 |
| 工具列表缓存 | ✅ 已实现 | 60秒刷新 |
| 健康检查 | ✅ 已实现 | 独立 /health 端点 |
| 工具调用 | ✅ 已实现 | call_tool 封装 |

#### BaseGameAdapter (base_adapter.py)

| 功能 | 状态 | 说明 |
|-----|------|------|
| 抽象接口定义 | ✅ 已实现 | 7个抽象方法 + 1个具体方法 |
| 统一状态格式 | ✅ 已实现 | UnifiedGameState dataclass |
| 统一动作格式 | ✅ 已实现 | UnifiedAction dataclass |

#### SlayTheSpireAdapter (adapters/slay_the_spire.py, 264行)

| 功能 | 状态 | 说明 |
|-----|------|------|
| 游戏状态获取 | ✅ 已实现 | 三级回退策略 |
| 动作执行 | ✅ 已实现 | 返回 tuple[bool, str] |
| 回合判断 | ✅ 已实现 | ready_for_command + 画面类型 |
| 工具定义转换 | ✅ 已实现 | MCP → OpenAI function calling |
| 角色名修正 | ✅ 已实现 | 支持别名映射 |
| 开局清理 | ✅ 已实现 | start_game 前 abandon_run |

#### 优点

1. **适配器模式**: BaseGameAdapter 抽象基类设计良好，易于扩展新游戏
2. **三级回退**: `get_state` 依次尝试 `get_game_state` → `get_screen_state` → `get_available_commands`，增强鲁棒性
3. **统一状态格式**: UnifiedGameState 将不同游戏的状态归一化
4. **角色名修正**: 支持多种角色名输入（character_index/role/class/char），增强 LLM 输出兼容性

#### 问题与建议

| 编号 | 严重级别 | 问题描述 | 建议 |
|-----|---------|---------|------|
| M1 | 🟡 中危 | MCPClient 无重试机制，网络抖动可能导致工具调用失败 | 添加指数退避重试（2-3次） |
| M2 | 🟢 低危 | 工具列表缓存时间 60秒硬编码 | 提取为配置项 |
| M3 | 🟡 中危 | SlayTheSpireAdapter 的 `execute_action` 中 `start_game` 前调用 `abandon_run`，如果旧存档有价值会丢失 | 添加确认逻辑或配置开关 |
| M4 | 🟢 低危 | `is_my_turn` 的判断逻辑与杀戮尖塔强耦合 | 在 BaseGameAdapter 中提供默认实现 |

---

### 2.5 消息队列 (messaging/)

#### PriorityMessageQueue (queue.py)

| 功能 | 状态 | 说明 |
|-----|------|------|
| 5级优先级 | ✅ 已实现 | INTERRUPT/DISPOSABLE |
| 消息过期 | ✅ 已实现 | expire_at + allow_skip |
| 消息合并 | ✅ 已实现 | merge_key 相同的消息拼接 |
| 消息取消 | ✅ 已实现 | cancel_key |
| 用户冷却 | ✅ 已实现 | 3秒内同用户只发一条 |
| 队列满丢弃 | ✅ 已实现 | 按优先级丢弃，INTERRUPT/HIGH 永不丢弃 |
| 全局静音 | ✅ 已实现 | mute/unmute |
| 统计信息 | ✅ 已实现 | 入队/丢弃/消费计数 |

#### RateLimiter (rate_limiter.py)

| 功能 | 状态 | 说明 |
|-----|------|------|
| 频率限制 | ✅ 已实现 | source:action 维度 |
| 突发控制 | ✅ 已实现 | max_burst=1, burst_window=1.0s |

#### 优点

1. **优先级设计合理**: 游戏解说(HIGH) > 弹幕(NORMAL) > 礼物(LOW)，确保重要消息优先处理
2. **消息合并**: 相同 merge_key 的消息自动合并，减少 LLM 调用次数
3. **永不丢弃策略**: INTERRUPT 和 HIGH 优先级消息永不丢弃，保证关键消息不丢失
4. **统计信息**: 便于监控队列健康状态

#### 问题与建议

| 编号 | 严重级别 | 问题描述 | 建议 |
|-----|---------|---------|------|
| Q1 | 🟡 中危 | 队列满时丢弃策略只看优先级，不考虑消息等待时间 | 添加等待时间因子，避免低优先级消息永远得不到处理 |
| Q2 | 🟢 低危 | 用户冷却时间 3秒硬编码 | 提取为配置项 |
| Q3 | 🟢 低危 | 消息合并时内容直接拼接，无分隔符 | 添加换行或分隔符提高可读性 |

---

### 2.6 GameManager (game_manager.py, 97行)

#### 功能完整性 ✅

| 功能 | 状态 | 说明 |
|-----|------|------|
| 游戏注册/注销 | ✅ 已实现 | register_game / unregister_game |
| 启动/停止 | ✅ 已实现 | start / stop |
| 静音/取消静音 | ✅ 已实现 | mute / unmute |
| 状态查询 | ✅ 已实现 | get_game_status |

#### 优点

1. **简洁设计**: 97行代码，职责单一
2. **单例模式**: `get_game_manager()` 全局单例
3. **统一管理**: 同时管理 HostGraph 和多个 GameGraph

#### 问题与建议

| 编号 | 严重级别 | 问题描述 | 建议 |
|-----|---------|---------|------|
| GM1 | 🟡 中危 | `start` 方法中 HostGraph 先于 GameGraph 启动，但 GameGraph 可能在 HostGraph 就绪前就发送解说请求 | 确保 HostGraph 完全就绪后再启动 GameGraph |
| GM2 | 🟢 低危 | `get_game_status` 缺少 MemorySummarizer 的运行状态 | 添加 memory_running 字段 |
| GM3 | 🟢 低危 | `stop` 方法无超时保护，如果某个 Graph 停止卡住会阻塞 | 添加 asyncio.wait_for 超时 |

---

### 2.7 MemorySummarizer (memory/game_memory.py, 274行)

#### 功能完整性 ✅

| 功能 | 状态 | 说明 |
|-----|------|------|
| 定期总结 | ✅ 已实现 | check_interval=60s |
| 触发阈值 | ✅ 已实现 | trigger_threshold=30 |
| 记忆工具 | ✅ 已实现 | search_replace_memory + rewrite_memory |
| 历史清理 | ✅ 已实现 | trim_histories(keep_seconds=300) |

#### 优点

1. **异步服务**: 不阻塞主循环
2. **专用 LLM**: 使用低温度(0.3)确保记忆总结的准确性
3. **两种更新模式**: search_replace 适合小幅修正，rewrite 适合大幅重组

#### 问题与建议

| 编号 | 严重级别 | 问题描述 | 建议 |
|-----|---------|---------|------|
| ME1 | 🟡 中危 | MemorySummarizer 使用 `get_ai_client()` 而非 `get_game_ai_client()`，与 GameGraph 使用不同的 LLM 实例 | 确认是否为有意设计，统一或文档化差异 |
| ME2 | 🟢 低危 | 总结失败后无重试机制 | 添加失败计数和重试逻辑 |
| ME3 | 🟢 低危 | trigger_threshold 和 check_interval 硬编码 | 提取为配置项 |

---

### 2.8 Game Router (game_router.py, 73行)

#### API 端点

| 端点 | 方法 | 状态 | 说明 |
|-----|------|------|------|
| /game/status | GET | ✅ | 获取游戏状态 |
| /game/start | POST | ✅ | 启动游戏集成 |
| /game/stop | POST | ✅ | 停止游戏集成 |
| /game/context | GET | ✅ | 获取共享上下文 |
| /game/mute | POST | ✅ | 静音消息队列 |
| /game/unmute | POST | ✅ | 取消静音 |
| /game/queue | GET | ✅ | 获取队列统计 |

#### 问题与建议

| 编号 | 严重级别 | 问题描述 | 建议 |
|-----|---------|---------|------|
| R1 | 🟡 中危 | `/game/start` 的 GameStartRequest 参数未被使用，游戏适配器需提前注册 | 要么使用参数动态创建适配器，要么移除无用参数 |
| R2 | 🟢 低危 | 缺少错误处理端点（如 MCP 连接失败的详细错误信息） | 添加错误详情到响应 |
| R3 | 🟢 低危 | 缺少 WebSocket 推送端点（游戏状态变更实时通知前端） | 考虑添加 WS 端点 |

---

## 三、跨模块问题

### 3.1 双路径记忆不一致 🟡

AIHostBrain 的 LangGraph 流程使用 SessionHistory + UserProfile 记忆系统，而 HostGraph 使用 SharedContext 的主播回答历史。两条路径的主播人格和上下文可能不一致。

**建议**: 明确双路径的使用场景。消息队列路径（HostGraph）用于生产环境的弹幕/解说，流式 API 路径（LangGraph）仅用于测试面板。在文档中明确标注。

### 3.2 礼物感谢未打通 🟡 → ✅ 已修复

`_handle_gift_thanks` 方法在 HostGraph 中已实现，但上游缺少将礼物事件推入 PriorityMessageQueue 的逻辑。

**修复方案**: 在 `bilibili/router.py` 的 `on_message` 回调中添加了礼物事件处理，当 `msg_type == "gift"` 时将礼物信息封装为 `Message(priority=PRIORITY_LOW, source="gift", msg_type="gift_thanks")` 推入消息队列。HostGraph 的 `_host_loop` 会消费 `gift_thanks` 类型消息并调用 `_handle_gift_thanks`。

**数据流**: B站礼物事件 → `CustomHandler._on_gift` → `on_message("gift", GiftData)` → `PriorityMessageQueue.put` → `HostGraph._handle_gift_thanks` → LLM 生成感谢语 → TTS

### 3.3 配置分散 🟢 → ✅ 已修复

游戏相关配置分散在 config.py 的多个字段中，部分硬编码在代码中。

**修复方案**:
1. 在 `config.py` 中新增 5 个配置属性：`game_default_character`、`game_min_commentary_interval`、`game_queue_max_size`、`game_host_history_maxlen`、`game_game_history_maxlen`
2. 在 `config.example.yaml` 的 game 区块中添加对应配置项及注释
3. 在代码中使用配置替换硬编码值：
   - `GameGraph.__init__`: `poll_interval` 和 `min_commentary_interval` 从 config 读取
   - `GameGraph._game_loop`: `IRONCLAD` → `config.game_default_character`
   - `SharedContext.__init__`: `maxlen` 从 config 读取
   - `PriorityMessageQueue.__init__`: `max_size` 从 config 读取

### 3.4 错误恢复不足 🟡

GameGraph 的 `_game_loop` 在异常后固定 sleep 5秒，无指数退避。如果 MCP 服务持续不可用，会产生大量无效请求。

**建议**: 引入指数退避策略：
```python
retry_delay = min(5 * (2 ** consecutive_failures), 60)
```

---

## 四、文档更新记录

本次审查同步更新了以下文档：

| 文档 | 更新内容 |
|-----|---------|
| `1.architecture/mcp-game-integration.md` | 完整重写，反映实际的双Graph架构、SharedContext、消息队列、三层记忆等实现 |
| `1.architecture/system-overview.md` | 添加游戏集成模块说明、/game/* 路由、AI对话模块架构变更 |
| `1.architecture/module-interactions.md` | 更新AI对话交互流程、新增游戏集成交互章节 |
| `4.business/ai-reply-flow.md` | 添加双路径架构说明（消息队列路径 vs 流式API路径） |
| `4.business/danmaku-flow.md` | 更新AI对话处理步骤，反映PriorityMessageQueue + HostGraph架构 |
| `0.overview/project-intro.md` | 添加游戏集成（MCP）核心功能特性、更新系统架构图 |
| `5.requirements/functional-requirements.md` | 添加第7模块"游戏集成模块（MCP）"的13项功能需求 |

---

## 五、问题汇总

| 严重级别 | 数量 | 说明 |
|---------|------|------|
| 🔴 高危 | 0 | - |
| 🟡 中危 | 9 → 6 | 3项已修复，2项审查结论有误降级 |
| 🟢 低危 | 15 → 12 | 3项已修复 |

### 已修复问题

| 编号 | 模块 | 修复内容 |
|-----|------|---------|
| G1 | GameGraph | 硬编码 `IRONCLAD` → `config.game_default_character` |
| G4 | GameGraph | `_format_game_state` 移至 `SlayTheSpireAdapter.format_state_for_prompt` |
| H1 | HostGraph | 在 `bilibili/router.py` 添加礼物事件入队逻辑 |
| S1 | SharedContext | `search_replace_memory` 和 `request_host_commentary` 操作记录写入游戏历史 |
| S2 | SharedContext | `maxlen` 从配置读取 |
| 3.3 | 跨模块 | 配置统一到 config.yaml 的 game 区块，新增 5 个配置项 |

### 审查结论有误的问题

| 编号 | 原结论 | 实际情况 |
|-----|--------|---------|
| G5 | `_last_commentary_time` 未使用 | 实际在使用：GameGraph 层面 15s 间隔控制，与 RateLimiter 队列层 4s 间隔是两层不同粒度的频率控制 |
| G6 | 游戏动作缺少单步超时 | 设计意图正确：先排出解说和记忆操作，剩余游戏操作在时间预算内逐步执行，失败后立即执行下一步 |

### 🟡 中危问题清单（待修复）

| 编号 | 模块 | 问题 | 优先级建议 |
|-----|------|------|-----------|
| G2 | GameGraph | 异常后无指数退避 | P1 |
| H4 | HostGraph | 双路径记忆不一致 | P2 |
| M1 | MCP | 无重试机制 | P1 |
| M3 | MCP | abandon_run 可能丢失存档 | P2 |
| Q1 | Queue | 低优先级消息可能饿死 | P2 |
| GM1 | GameManager | Graph 启动顺序 | P2 |

### 🟢 低危问题清单（待修复）

| 编号 | 模块 | 问题 |
|-----|------|------|
| G3 | GameGraph | 游戏规则硬编码 |
| ~~G4~~ | ~~GameGraph~~ | ~~_format_game_state 耦合~~ ✅ 已修复 |
| ~~G5~~ | ~~GameGraph~~ | ~~_last_commentary_time 冗余~~ ❌ 审查有误 |
| H2 | HostGraph | max_tokens 硬编码 |
| H3 | HostGraph | 缺少降级回复 |
| ~~S2~~ | ~~SharedContext~~ | ~~maxlen 硬编码~~ ✅ 已修复 |
| S3 | SharedContext | trim 间隔硬编码 |
| M2 | MCP | 缓存时间硬编码 |
| M4 | MCP | is_my_turn 耦合 |
| Q2 | Queue | 冷却时间硬编码 |
| Q3 | Queue | 合并无分隔符 |
| GM2 | GameManager | 缺少 memory 状态 |
| GM3 | GameManager | stop 无超时 |
| ME2 | Memory | 总结无重试 |
| ME3 | Memory | 参数硬编码 |

---

## 六、修复优先级建议

```
┌─────────────────────────────────────────────────────────────────┐
│                     修复优先级（第二轮更新）                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ✅ 已完成:                                                    │
│   - H1: 打通礼物感谢入队逻辑 (bilibili/router.py)              │
│   - G1: 角色选择配置化 (config.game_default_character)          │
│   - G4: _format_game_state 移至 SlayTheSpireAdapter            │
│   - S1: 记忆/解说操作写入游戏历史                               │
│   - S2: maxlen 配置化                                          │
│   - 3.3: 配置统一到 config.yaml game 区块                      │
│                                                                 │
│   第一阶段 (尽快修复):                                          │
│   - M1: MCPClient 添加重试机制                                 │
│   - G2: GameGraph 异常指数退避                                 │
│                                                                 │
│   第二阶段 (迭代优化):                                          │
│   - H4: 明确双路径记忆策略，文档化                              │
│   - GM1: Graph 启动顺序保证                                    │
│   - R1: start API 参数清理                                     │
│   - ME1: 统一 LLM 实例或文档化差异                             │
│   - Q1: 低优先级消息防饿死                                     │
│   - M3: abandon_run 添加确认/配置开关                           │
│                                                                 │
│   第三阶段 (持续改进):                                          │
│   - 所有低危问题: 配置项提取、硬编码消除                        │
│   - 添加单元测试覆盖                                           │
│   - 添加游戏状态 WebSocket 推送                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 七、优秀实践

本次审查中也发现了一些值得肯定的设计：

1. **双 Graph 架构**: GameGraph 和 HostGraph 职责分离，通过消息队列解耦，避免话术冲突
2. **适配器模式**: BaseGameAdapter 抽象基类设计良好，SlayTheSpireAdapter 实现完整，易于扩展新游戏
3. **三层记忆系统**: core/important/recent 分层设计，支持 rewrite 和 search_replace 两种更新模式
4. **PriorityMessageQueue**: 5级优先级 + 过期/合并/取消/静音，功能完善
5. **并行数据收集**: GameGraph 使用 asyncio.gather 并行获取上下文，减少延迟
6. **多格式 JSON 解析**: 兼容不同 LLM 的输出格式，增强鲁棒性
7. **MemorySummarizer**: 异步服务不阻塞主循环，低温度确保总结质量
8. **GameManager 简洁设计**: 97行代码，职责单一，易于维护

---

## 相关文档

- [MCP游戏集成架构](../1.architecture/mcp-game-integration.md)
- [系统整体架构](../1.architecture/system-overview.md)
- [模块间交互关系](../1.architecture/module-interactions.md)
- [AI回复流程](../4.business/ai-reply-flow.md)
- [弹幕处理流程](../4.business/danmaku-flow.md)
- [功能需求](../5.requirements/functional-requirements.md)
- [代码审查报告(旧)](./code-review-report.md)
