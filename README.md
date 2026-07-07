# FeinaLive

FeinaLive 是一个个人开发的虚拟主播直播系统，目标是把 AI 主播、B 站弹幕互动、点歌、数字人渲染、游戏 AI 自动化和长期记忆系统放在同一个本地直播工作流里。

项目目前主要面向 Windows 本地运行。OBS 推流建议安装 Spout2 插件，用 OBS 捕获 EasyVtuber 输出的数字人画面。

## 当前能力

- B 站直播间弹幕接入、测试房间、管理员弹幕指令
- AI 主播回复：HostGraph、流式 LLM、TTS、数字人口型联动
- 弹幕点歌：B 站 BV/关键词点歌、队列、播放列表、音量/暂停控制
- EasyVtuber 数字人：THA3/THA4 推理、WebSocket 输入、Spout2 输出
- 游戏 AI：通过 MCP 驱动杀戮尖塔，GameGraph 决策、操作、请求主播解说
- 记忆系统：单局记忆、长期记忆原子、游戏知识图谱、召回测试与可视化调试台
- 前端直播界面：视频/HLS、弹幕面板、音乐播放器、任务面板、集中配置面板

## 项目结构

```text
feinaLive/
├── backend/                 # FastAPI 后端
│   ├── apps/
│   │   ├── ai/              # 主播/游戏 AI、记忆、消息队列、MCP 适配
│   │   ├── live/            # B 站弹幕与点歌
│   │   ├── easyvtuber/      # 数字人运行管理
│   │   └── config_router.py # 配置 API
│   ├── EasyVtuber/          # 数字人渲染引擎
│   ├── data/                # 本地运行数据，不提交
│   ├── main.py              # FastAPI 入口，默认端口 9191
│   └── pyproject.toml       # uv 依赖配置
├── fronted/                 # Vue 3 前端，默认端口 5173/5174
├── docs/                    # 业务流程与系统架构文档
├── mcp/                     # 杀戮尖塔 MCP Mod
├── nginx-rtmp-win32/        # 本地 HLS/HTTP 代理运行文件
└── cankao/                  # 参考项目，不提交
```

## 环境要求

- Windows 10/11
- Python 3.11
- uv
- Node.js 20+
- NVIDIA GPU/CUDA 环境（运行 EasyVtuber GPU 推理时需要）
- OBS + Spout2 插件（正式推流时建议）
- MySQL（用户画像、播放列表等业务数据）

## 快速开始

### 1. 后端依赖

```powershell
cd backend
uv sync
```

如果已存在 `.venv`，也可以直接使用：

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 9191
```

### 2. 前端依赖

```powershell
cd fronted
npm install
```

### 3. 配置

复制配置模板：

```powershell
Copy-Item backend\config.example.yaml backend\config.yaml
```

至少需要检查：

- `database.url`：MySQL 连接
- `bilibili.room_id` / `bilibili.sessdata`
- `llm` / `host` / `game` 的模型 API 配置
- `tts` / `volcano` 或 Edge TTS 配置
- `game.enabled`、`game.mcp_url`
- `easyvtuber` 数字人角色、输入和性能配置

`backend/config.yaml` 包含凭证，不应提交。

### 4. EasyVtuber 模型

EasyVtuber 模型文件不要提交到仓库。模型下载地址：

```
https://drive.google.com/file/d/1pWKIpjWeqfpa3Rub185FVvxDr5H09pOi/view?usp=drive_link
```

下载后解压到：

```text
backend/EasyVtuber/data/models/
├── rife/
├── sr/
├── tha3/
└── tha4/
```

### 5. 启动

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 9191
```

前端：

```powershell
cd fronted
npm run dev
```

打开 Vite 输出的地址，通常是：

```text
http://127.0.0.1:5173
```

后端启动时会初始化音乐队列、用户画像、记忆引擎、EasyVtuber 和本地 Nginx/HLS 代理。

## 常用入口

| 入口 | 说明 |
| --- | --- |
| `GET /health` | 后端健康检查 |
| `GET /config` / `PUT /config` | 集中配置读取与保存 |
| `GET /stream/status` | 本地 Nginx/HLS 状态 |
| `POST /test/danmaku` | 测试弹幕 |
| `POST /test/admin/command` | 测试管理员指令 |
| `GET /game/status` | 游戏 AI 状态 |
| `POST /game/start` / `POST /game/stop` | 手动启停游戏 AI |
| `GET /ai/memory/stats` | 记忆系统统计 |
| `POST /ai/memory/recall/test` | 记忆召回测试 |
| `GET /ai/memory/graph/overview` | 记忆/知识图谱概览 |

前端按 `Ctrl + Shift + S` 打开集中配置面板。面板内包含：

- AI 主播、AI 模型、TTS、消息调度、数字人、游戏参数、直播、直播状况
- 记忆调试台：概览、记忆管理、召回测试、知识图谱、单局/注入、备份

## 管理员指令

常用弹幕指令包括：

| 指令 | 作用 |
| --- | --- |
| `/sleep 1` / `/sleep 0` | 暂停 / 恢复 AI 主播 |
| `/face 1` / `/face 0` | 鼠标追踪 / 漫步 |
| `/voice 1` / `/voice 0` | 管理员接管 / AI 主播模式 |
| `/hide 1` / `/hide 0` | 隐藏 / 显示管理员弹幕 |
| `/next` | 下一首 |
| `/pause 1` / `/pause 0` | 暂停 / 恢复音乐 |
| `/rm` | 移除当前歌曲 |
| `/clear` | 清除当前用户记忆 |

## 开发与验证

后端测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

前端构建：

```powershell
cd fronted
npm run build
```

针对记忆调试台的快速后端测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests\test_memory_debug.py -q
```

## Git 注意事项

不应提交：

- `__pycache__/`、`*.pyc`
- `.venv/`、`.pytest_cache/`、`.ruff_cache/`
- `backend/config.yaml`
- `backend/data/`、`memory.db*`、记忆备份
- `fronted/test-results/`、`playwright-report/`
- 日志、pid、临时 zip 包
- `cankao/` 参考项目

如果某个运行产物已经被 Git 跟踪，需要先从索引移除：

```powershell
git rm --cached path\to\file
```

## 文档

更完整的业务流程和架构说明见 [docs/README.md](docs/README.md)。

## 说明

这是个人实验性项目，很多模块按直播间实际需求迭代，接口和内部结构仍可能调整。优先参考当前代码和 `docs/` 下的最新文档。
