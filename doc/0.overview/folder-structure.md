# 项目文件夹结构说明

## 整体目录结构

```
feinaLive/
├── backend/                 # FastAPI 后端服务根目录
│   ├── apps/               # 应用模块（核心业务逻辑）
│   ├── EasyVtuber/          # 虚拟形象渲染引擎
│   ├── core/               # 核心基础设施
│   ├── services/           # 外部服务集成
│   ├── tests/              # 单元测试
│   ├── utils/              # 工具函数
│   ├── main.py             # 应用入口
│   ├── config.py           # 配置管理
│   └── config.example.yaml # 配置模板
│
├── frontend/               # Vue 3 前端项目
│   ├── src/
│   │   ├── components/     # Vue 组件
│   │   ├── composables/    # 组合式API
│   │   ├── stores/         # Pinia 状态管理
│   │   ├── types/          # TypeScript 类型定义
│   │   └── utils/          # 工具函数
│   ├── index.html
│   └── package.json
│
├── nginx-rtmp-win32/      # nginx RTMP 流媒体服务器（Windows版）
│   ├── conf/               # 配置文件
│   ├── logs/               # 日志目录
│   └── nginx.exe          # 可执行文件
│
├── doc/                   # 技术文档
│   ├── 0.overview/        # 项目总览
│   ├── 1.architecture/    # 架构文档
│   ├── 2.backend/         # 后端文档
│   ├── 3.frontend/        # 前端文档
│   ├── 4.business/        # 业务流程
│   ├── 5.requirements/    # 需求文档
│   └── 6.review/          # 代码审查
│
└── README.md              # 项目说明
```

---

## backend/ 目录详解

### backend/apps/ - 应用模块

这是项目的核心业务逻辑所在，包含多个功能模块：

```
backend/apps/
├── __init__.py
├── config.py               # 全局配置类，从 config.yaml 读取
├── config_router.py        # 配置管理 API
├── db.py                   # SQLAlchemy 数据库连接和表定义
├── exceptions.py           # 自定义异常类
│
├── live/                   # 直播间功能模块
│   ├── __init__.py
│   ├── danmaku_handler.py  # 弹幕处理核心逻辑（被各模块调用）
│   ├── bilibili/           # B站弹幕接入模块
│   │   ├── client.py      # BilibiliClient - B站API封装
│   │   ├── handlers.py    # 弹幕消息处理
│   │   ├── models.py      # 弹幕数据模型
│   │   └── router.py      # WebSocket 弹幕路由
│   │
│   └── music/              # 音乐播放模块
│       ├── client.py      # BilibiliMusicClient - 音乐API封装
│       ├── library.py     # 播放列表管理
│       ├── llm_verify.py  # LLM音乐验证
│       ├── models.py      # 音乐数据模型（Pydantic）
│       ├── queue.py       # 播放队列管理（核心）
│       ├── router.py      # 音乐API路由
│       ├── service.py     # 弹幕拦截点歌服务
│       └── up_videos.py   # UP主视频管理
│
├── ai/                     # AI对话模块
│   ├── admin_commands.py  # 管理员指令处理
│   ├── client.py          # LLM API 客户端
│   ├── history.py         # 会话历史管理
│   ├── host_brain.py     # AI主播大脑（核心）
│   ├── prompt.py         # Prompt 构建
│   ├── router.py          # AI API 路由
│   ├── tts.py            # 火山引擎 TTS 客户端
│   └── memory/           # 用户记忆系统
│       ├── summarizer.py # 记忆摘要生成
│       └── user_profile.py # 用户画像管理
│
├── easyvtuber/            # 虚拟形象控制模块
│   ├── __init__.py       # EasyVtuberManager 管理器
│   └── router.py         # 虚拟形象控制 API
│
└── image/                  # 图片处理模块（预留）
```

### backend/EasyVtuber/ - 虚拟形象渲染引擎

这是基于 EasyVtuber 的虚拟形象渲染系统：

```
backend/EasyVtuber/
├── src/                    # 主程序源码
│   ├── main.py            # 入口
│   ├── args.py           # 参数解析
│   ├── audio_client.py   # 音频输入
│   ├── face_mesh_client.py # 人脸检测
│   ├── mouse_client.py    # 鼠标输入
│   ├── open_see_face_client.py # 人脸识别
│   ├── model_infer_client.py # 模型推理
│   └── utils/             # 工具函数
│
├── ezvtuber-rt/           # 运行时引擎（子模块）
│   ├── ezvtb_rt/         # ONNX 推理实现
│   │   ├── tha3.py       # THA3 模型
│   │   ├── tha4.py       # THA4 模型
│   │   ├── tha4_ort.py   # ONNX 优化版
│   │   └── ...
│   └── setup.py
│
├── data/                   # 数据目录
│   ├── images/            # 测试图片
│   └── models/            # 模型文件（需手动下载）
│       ├── tha3/
│       ├── tha4/
│       ├── rife/
│       └── sr/
│
├── runner.py              # 运行器
├── env_init.py            # 环境初始化
└── requirements.txt       # 依赖
```

### backend/core/ - 核心基础设施

```
backend/core/
├── __init__.py
└── websocket.py           # WebSocket 连接管理器（ConnectionManager）
```

### backend/services/ - 外部服务

```
backend/services/
├── __init__.py
└── nginx_service.py       # nginx 服务管理
```

---

## frontend/ 目录详解

```
frontend/
├── src/
│   ├── App.vue            # 根组件
│   ├── main.ts            # 入口文件
│   │
│   ├── components/        # Vue 组件目录
│   │   ├── DanmakuTestPanel.vue    # 弹幕测试面板
│   │   ├── NotificationToast.vue   # 通知提示
│   │   ├── PlayUnlockModal.vue     # 播放解锁弹窗
│   │   ├── SessdataWarningModal.vue # SESSDATA 警告
│   │   ├── SettingsPanel.vue       # 设置面板
│   │   │
│   │   ├── danmaku/       # 弹幕相关组件
│   │   │   ├── DanmakuItem.vue     # 单条弹幕
│   │   │   └── DanmakuPanel.vue    # 弹幕面板
│   │   │
│   │   ├── infobar/       # 信息栏组件
│   │   │   ├── ClockDisplay.vue    # 时钟显示
│   │   │   ├── InfoBar.vue         # 信息栏
│   │   │   ├── MarqueeText.vue     # 跑马灯文字
│   │   │   └── NoticeBadge.vue     # 公告徽章
│   │   │
│   │   ├── layout/        # 布局组件
│   │   │   ├── BottomDecoration.vue
│   │   │   └── TopDecoration.vue
│   │   │
│   │   ├── mainview/      # 主视图
│   │   │   └── MainView.vue
│   │   │
│   │   ├── music/        # 音乐组件
│   │   │   └── MusicPlayer.vue
│   │   │
│   │   └── panels/       # 面板组件
│   │       ├── MissionPanel.vue
│   │       └── PlaceholderPanel.vue
│   │
│   ├── composables/       # 组合式 API
│   │   ├── useAdminCommands.ts    # 管理员指令
│   │   ├── useAvatarInput.ts      # 虚拟形象输入
│   │   ├── useBilibiliDanmaku.ts  # B站弹幕
│   │   └── useHlsPlayer.ts        # HLS 播放器
│   │
│   ├── stores/            # Pinia 状态管理
│   │   ├── danmaku.ts    # 弹幕状态
│   │   ├── llm.ts        # AI 对话状态
│   │   ├── mission.ts    # 任务状态
│   │   ├── music.ts      # 音乐状态
│   │   └── stream.ts     # 流状态
│   │
│   ├── types/            # TypeScript 类型
│   │   ├── danmaku.ts
│   │   ├── music.ts
│   │   └── stream.ts
│   │
│   └── utils/            # 工具函数
│       └── notification.ts
│
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
└── tsconfig.json
```

---

## nginx-rtmp-win32/ 目录

Windows 平台的 nginx RTMP 服务器，用于直播推流：

```
nginx-rtmp-win32/
├── conf/
│   ├── nginx.conf        # 主配置文件
│   └── mime.types        # MIME 类型
├── logs/
│   ├── access.log        # 访问日志
│   └── error.log         # 错误日志
├── html/                 # 静态网页
│   ├── index.html        # 测试页面
│   ├── stat.xsl          # 统计页面
│   └── vod.html          # 点播测试
├── nginx.exe            # 可执行文件
└── stop.bat             # 停止脚本
```

---

## 快速理解项目的建议

### 新人入门路径

1. **先看后端主入口**：[backend/main.py](file:///c:\my_code\feinaLive\backend\main.py)
   - 了解 FastAPI 应用初始化
   - 了解各路由模块的注册
   - 了解启动时初始化流程

2. **再看核心流程**：
   - 弹幕处理 → [danmaku_handler.py](file:///c:\my_code\feinaLive\backend\apps\danmaku_handler.py)
   - 点歌流程 → [music/service.py](file:///c:\my_code\feinaLive\backend\apps\music\service.py)
   - AI对话 → [ai/host_brain.py](file:///c:\my_code\feinaLive\backend\apps\ai\host_brain.py)

3. **理解数据流**：
   - 弹幕：用户 → B站服务器 → WebSocket → danmaku_handler → AI大脑
   - 音乐：弹幕 → 点歌服务 → 队列 → 音频代理 → 前端

### 关键文件速查表

| 功能 | 关键文件 |
|-----|---------|
| 应用启动 | backend/main.py |
| 配置管理 | backend/apps/config.py |
| 数据库 | backend/apps/db.py |
| WebSocket | backend/core/websocket.py |
| 弹幕处理 | backend/apps/live/danmaku_handler.py |
| 点歌服务 | backend/apps/live/music/service.py |
| AI对话 | backend/apps/ai/host_brain.py |
| TTS | backend/apps/ai/tts.py |
| 虚拟形象 | backend/apps/easyvtuber/ |