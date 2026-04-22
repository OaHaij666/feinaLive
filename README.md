# feinaLive

这是一个仿照 Neuro-Sama 完成的包含前后端的项目。由于是个人开发的练习项目，有诸多不完善的地方，前端后端很多组件也是根据自身需求打造。
推流时建议使用OBS，安装spout2插件，在OBS中捕获数字人图像。

## 项目结构

```
feinaLive/
├── backend/           # FastAPI 后端服务
│   ├── apps/          # 应用模块
│   │   ├── easyvtuber/    # EasyVtuber 集成模块
│   │   ├── music/         # 音乐播放管理
│   │   └── ...
│   ├── EasyVtuber/         # 虚拟形象渲染引擎
│   └── main.py            # 入口文件
├── fronted/           # Vue 前端界面
└── oss-referances/    # 参考文档（不上传）
```

## 快速开始

### 1. 安装依赖

#### 后端
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

#### 前端
```bash
cd fronted
npm install
```

### 2. 下载模型文件

EasyVtuber 需要下载模型文件才能运行：

**下载地址**: [Google Drive](https://drive.google.com/file/d/1pWKIpjWeqfpa3Rub185FVvxDr5H09pOi/view?usp=drive_link)

下载后解压到 `backend/EasyVtuber/data/models/` 目录下。

目录结构应为：
```
backend/EasyVtuber/data/models/
├── rife/
├── sr/
├── tha3/
└── tha4/
```

### 3. 配置

复制配置文件模板：
```bash
cp backend/config.example.yaml backend/config.yaml
```

编辑 `config.yaml` 填入数据库连接信息等配置。

### 4. 启动服务

#### 后端
```bash
cd backend
.venv\Scripts\activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

#### 前端
```bash
cd fronted
npm run dev
```

## 功能特性

- **虚拟形象渲染**: 基于 EasyVtuber 的实时虚拟形象驱动
- **WebSocket 流媒体**: 实时将渲染画面推送到前端
- **透明背景支持**: PNG 格式输出，支持透明通道
- **GPU 加速**: 支持 CUDA GPU 加速推理

## 技术栈

- **后端**: FastAPI, SQLAlchemy, ONNX Runtime
- **前端**: Vue 3, TypeScript
- **虚拟形象**: EasyVtuber (THA3/THA4 模型)

## 许可证

MIT License
