# 飞娜直播间技术文档

欢迎阅读飞娜直播间项目的技术文档体系。本文档旨在帮助开发人员快速理解项目全貌，掌握各模块的设计思路与实现细节。

## 文档导航

### 📖 0. 项目总览
- [项目简介](./0.overview/project-intro.md) - 项目背景、功能特性、技术栈
- [文件夹结构说明](./0.overview/folder-structure.md) - 详细说明各目录作用

### 🏗️ 1. 系统架构
- [系统整体架构](./1.architecture/system-overview.md) - 系统架构图、核心组件
- [模块间交互关系](./1.architecture/module-interactions.md) - 模块通信机制、数据流向
- [技术栈说明](./1.architecture/tech-stack.md) - 技术选型理由

### 💻 2. 后端文档
#### 2.1 API接口
- [B站弹幕API](./2.backend/2.1-api/bilibili-api.md) - WebSocket弹幕接入
- [音乐播放API](./2.backend/2.1-api/music-api.md) - 点歌、队列管理
- [AI对话API](./2.backend/2.1-api/ai-api.md) - AI主播对话接口
- [配置管理API](./2.backend/2.1-api/config-api.md)

#### 2.2 数据库设计
- [ER图与表结构](./2.backend/2.2-database/er-diagram.md)
- [用户画像表](./2.backend/2.2-database/table-user-profile.md)
- [UP主视频表](./2.backend/2.2-database/table-up-video.md)
- [播放列表表](./2.backend/2.2-database/table-playlist.md)

#### 2.3 数据模型
- [B站数据模型](./2.backend/2.3-models/bilibili-models.md)
- [音乐数据模型](./2.backend/2.3-models/music-models.md)

### 🎨 3. 前端文档
- [项目结构](./3.frontend/project-structure.md)
- [组件说明](./3.frontend/components.md)
- [状态管理](./3.frontend/stores.md)

### 🔄 4. 业务流程
- [弹幕处理流程](./4.business/danmaku-flow.md)
- [点歌业务流程](./4.business/music-flow.md)
- [AI回复流程](./4.business/ai-reply-flow.md)
- [虚拟形象渲染流程](./4.business/avatar-flow.md)

### 📋 5. 需求文档
- [功能需求](./5.requirements/functional-requirements.md)
- [非功能需求](./5.requirements/non-functional-requirements.md)

### 🔍 6. 代码审查
- [代码审查报告](./6.review/code-review-report.md)

## 快速入门

### 后端启动
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# 编辑 config.yaml 填入配置
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端启动
```bash
cd frontend
npm install
npm run dev
```

## 技术支持

如有问题，请查阅各模块详细文档，或参考代码中的注释说明。
