# FeinaLive

FeinaLive 是一个个人开发的虚拟主播直播系统，目标是把 AI 主播、B 站弹幕互动、点歌、数字人渲染、游戏 AI 自动化和长期记忆系统放在同一个本地直播工作流里。

项目目前面向 Windows 本地单机运行。OBS 推流建议安装 Spout2 插件，用 OBS 捕获 FeinaAvatar 输出的数字人画面。控制接口默认只监听本机回环地址，不作为公网服务暴露。

## 当前能力

- Bilibili、抖音与内部测试平台接入，统一标准弹幕、礼物与价值数据
- AI 主播回复：HostRuntime、流式 LLM、TTS、消费队列与播放确认
- 独立音乐系统：Bilibili 审核源、本地音乐源、可信曲库、队列及自动压低
- FeinaAvatar：THA3/THA4 推理、浏览器口型输入、预览与 Spout2 输出
- 通用 Agent：按静态场景装配 MCP、记忆、事件与主播解说能力
- 记忆系统：用户原子记忆、用户/游戏知识图谱、工作记忆、SQLite 与 ChromaDB
- 桌面控制中心：PySide6 集成进程管理、日志、配置、直播操作、语音、音乐、Agent 与记忆工具

## 项目结构

```text
feinaLive/
├── backend/                 # FastAPI 后端
│   ├── apps/
│   │   ├── agent/           # 通用 Agent、场景与能力装配
│   │   ├── ai/              # 主播 Runtime、记忆、消息与语音流水线
│   │   ├── live/            # 直播平台适配与唯一房间 Runtime
│   │   ├── music/           # Provider、审核、曲库与播放队列
│   │   ├── avatar/          # FeinaAvatar 生命周期与控制 API
│   │   ├── storage/         # SQLite 初始化与系统密钥库
│   │   └── config_router.py # 配置 API
│   ├── avatar_engine/       # FeinaAvatar 渲染引擎
│   ├── data/                # 本地运行数据，不提交
│   ├── main.py              # FastAPI 入口，默认端口 9191
│   └── pyproject.toml       # uv 依赖配置
├── fronted/                 # Vue 3 直播展示端，开发端口 5173
├── launcher/                # PySide6 运行中心与运营控制台
├── speech_gateway/          # 独立 TTS Gateway，默认端口 8091
├── .ua/                     # Understand Anything 架构知识图谱
├── mcp/                     # 杀戮尖塔 MCP Mod
├── nginx-rtmp-win32/        # 本地 HLS/HTTP 代理运行文件
└── cankao/                  # 参考项目，不提交
```

## 环境要求

- Windows 10/11
- Python 3.11
- uv
- Node.js 20+
- NVIDIA GPU/CUDA 环境（运行 FeinaAvatar GPU 推理时需要）
- OBS + Spout2 插件（正式推流时建议）
- SQLite（用户画像、播放列表、记忆原子和知识图谱）
- ChromaDB（可从 SQLite 重建的向量索引）

## 快速开始

### 推荐：桌面控制中心一键启动

完成下方配置后，双击仓库根目录的 `start_feinalive.bat`。首次运行会自动创建 Launcher 独立虚拟环境并安装 PySide6，随后打开 FeinaLive Control Center：

- 自动启动 Speech Gateway 和 Backend，并由 Backend 启动 Nginx；
- 首次缺少前端依赖或生产构建时，自动执行安装与构建；
- 集中显示 Bifrost、Speech Gateway、Backend、MCP、直播展示端、FeinaAvatar、直播平台 Runtime 和 Agent Runtime 的健康状态；
- 集中收集托管进程日志到 `launcher/logs/`，支持模块筛选、搜索与自动滚动；
- 支持单模块启动、停止、重启、打开直播端，并在同一窗口使用原生运营控制台。
- Nginx、FeinaAvatar、直播平台 Runtime 与 Agent 使用生命周期 API 独立启停；Bifrost/MCP 可在首次启动时配置外部启动命令并交由窗口托管。
- 桌面窗口支持中文 / English 即时切换以及亮色 / 暗色主题，选择会自动保存。

Bifrost 默认由外部独立管理。若希望控制中心同时托管它，可在启动 BAT 前设置完整启动命令，例如：

```powershell
$env:BIFROST_START_COMMAND = '你的 Bifrost 启动命令'
.\start_feinalive.bat
```

只打开控制中心、不自动启动服务，可使用：

```powershell
uv run --project launcher python -m launcher.main --no-autostart
```

以下步骤保留用于首次配置、开发调试和手动启动。

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

Speech Gateway 独立安装和启动：

```powershell
cd speech_gateway
uv sync
Copy-Item config.example.yaml config.yaml
uv run python -m speech_gateway.main
```

Gateway 默认监听 `127.0.0.1:8091`。桌面控制台提供 Provider JSON 配置、连通测试和运行结果；普通配置写入 `speech_gateway/config.yaml`，上游密钥写入系统 keyring，环境变量可作为部署覆盖。用户自行选择 Speaches、LocalAI、Piper/Kokoro 服务或其他兼容 `/v1/audio/speech` 的本地实现，feinaLive 不绑定具体模型。

### 3. 配置

复制配置模板：

```powershell
Copy-Item backend\config.example.yaml backend\config.yaml
```

至少需要检查：

- `storage.sqlite_path`：SQLite 权威数据库路径
- `storage.chroma_path`：ChromaDB 向量索引路径
- `bilibili.room_id` / `bilibili.sessdata`
- `llm` / `host` / `agent` 的模型 API 配置
- `tts.gateway_url`、模型路由、音色和音频格式
- `agent.enabled`、`agent.scenario_id`、`agent.mcp_url`
- `avatar` 数字人角色、输入、输出和性能配置

FeinaAvatar 的动作来源使用下拉选项，默认 `hybrid`：平时采用自主动作，管理员切换到鼠标追踪时临时接管；也可选择始终自主或始终使用浏览器控制。

敏感凭据通过运营控制台写入系统密钥库，也可使用环境变量；`backend/config.yaml` 只保存非敏感运行参数，仍不应提交个人配置。

LLM 与 Embedding 统一通过独立的 Bifrost Gateway 接入。feinaLive 只调用其 OpenAI-compatible `/v1` API，不直接保存上游供应商配置；供应商路由、fallback、限流和上游密钥均由 Bifrost 管理。示例配置使用 `http://127.0.0.1:8081/v1`，避免与默认 MCP 端口 `8080` 冲突。

TTS 通过独立 Feina Speech Gateway 的 `/v1/audio/speech` 接入。供应商配置、能力差异、路由、熔断和 fallback 留在 Gateway；主项目只接收统一音频产物和采样率、时长、RTF、fallback、可选时间轴等元数据。Gateway 对不支持的格式、情绪或时间轴能力明确报错，不会静默丢弃参数，并通过 `/v1/status` 与 `/metrics` 暴露运行状态。

### 4. FeinaAvatar 模型

FeinaAvatar 继承的模型文件不要提交到仓库。模型下载地址：

```
https://drive.google.com/file/d/1pWKIpjWeqfpa3Rub185FVvxDr5H09pOi/view?usp=drive_link
```

下载后解压到：

```text
backend/avatar_engine/data/models/
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

直播展示端：

```powershell
cd fronted
npm run dev
```

打开 Vite 输出的地址，通常是：

```text
http://127.0.0.1:5173
```

运营控制台已经整合进 PySide6 Control Center，不再启动第二个 Web 前端。Nginx 只在 `8088` 提供直播展示端。

后端启动时会初始化音乐队列、用户画像、记忆引擎、FeinaAvatar 和本地 Nginx/HLS 代理。

## 常用入口

| 入口 | 说明 |
| --- | --- |
| `GET /health` | 后端健康检查 |
| `GET /config` / `PUT /config` | 集中配置读取与保存 |
| `GET /stream/status` | 本地 Nginx/HLS 状态 |
| `GET /live/state` | 唯一直播平台会话状态 |
| `POST /test/live/event` | 测试平台标准事件 |
| `GET /agent/status` | Agent Runtime 状态 |
| `POST /agent/start` / `POST /agent/stop` | 手动启停 Agent |
| `GET /music/state` | 音乐队列与播放状态 |
| `GET /avatar/status` | FeinaAvatar 运行状态 |
| `GET /ai/memory/stats` | 记忆系统统计 |
| `POST /ai/memory/recall/test` | 记忆召回测试 |
| `GET /ai/memory/graph/overview` | 记忆/知识图谱概览 |

桌面运营控制台包含：

- 运行总览、AI 主播、模型、TTS、消息调度、数字人、Agent 场景、音乐和直播平台
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


## 架构知识图谱

项目架构、模块关系与引导式导览由 Understand Anything 维护在 `.ua/knowledge-graph.json`，使用 UA Dashboard 查看。

