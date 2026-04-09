# AI VTuber 直播前端 - 架构设计文档

## 一、项目概述

### 1.1 项目目标
构建一个精美的 AI VTuber 直播前端界面，用于 OBS 推流捕获。界面采用清新绿白风格，包含主画面区域、实时弹幕面板、信息栏等模块。

### 1.2 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| **Vue 3** | ^3.4.x | 前端框架 (Composition API) |
| **TypeScript** | ^5.0 | 类型安全 |
| **Vite** | ^5.x | 构建工具 |
| **Tailwind CSS** | ^3.4 | 样式框架 |
| **Socket.IO Client** | ^4.7 | 实时通信 (弹幕/状态) |
| **Pinia** | ^2.x | 状态管理 |

### 1.3 OBS 推流方案

```
┌─────────────────────────────────────────────────────────────┐
│  浏览器窗口 (1920×1080)                                       │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │           Vue 应用 (透明背景)                         │    │
│  │                                                      │    │
│  │   ┌──────────────────┬────────────────────┐         │    │
│  │   │                  │                    │         │    │
│  │   │   主画面区域      │   实时评论面板       │         │    │
│  │   │   (16:9)        │   (Danmaku Panel)   │         │    │
│  │   │                  │                    │         │    │
│  │   └──────────────────┴────────────────────┘         │    │
│  │                                                      │    │
│  │   ┌──────────────────────────────────────────┐       │    │
│  │   │        信息栏 (时钟 + 跑马灯)              │       │    │
│  │   └──────────────────────────────────────────┘       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                   ┌──────────────────┐
                   │  OBS 浏览器源     │
                   │  URL: http://... │
                   │  宽度: 1920      │
                   │  高度: 1080      │
                   │  自定义CSS:      │
                   │  background:     │
                   │  transparent     │
                   └──────────────────┘
```

---

## 二、界面布局设计

### 2.1 整体布局结构

```
┌═════════════════════════════════════════════════════════════════┐
│  🌸 TopDecoration (顶部装饰边框)                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                                                           │  │
│  │  ┌─────────────────────────────┬─────────────────────────┐│  │
│  │  │                             │                         ││  │
│  │  │      MainView               │    DanmakuPanel          ││  │
│  │  │      (主画面区域)            │    (实时评论)            ││  │
│  │  │                             │                         ││  │
│  │  │  16:9 Screen Capture        │  實時評論               ││  │
│  │  │                             │  ┌─────────────────┐   ││  │
│  │  │                             │  │                 │   ││  │
│  │  │                             │  │  弹幕列表        │   ││  │
│  │  │                             │  │                 │   ││  │
│  │  │                             │  └─────────────────┘   ││  │
│  │  │                             │                         ││  │
│  │  └─────────────────────────────┴─────────────────────────┘│  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│  🌿 BottomDecoration (底部花卉装饰)                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  InfoBar (信息栏)                                          │  │
│  │  TIME 13:54:30 ▌ 跑马灯滚动文字...              NOTICE     │  │
│  └───────────────────────────────────────────────────────────┘  │
└═════════════════════════════════════════════════════════════════┘
```

### 2.2 尺寸规格

| 区域 | 尺寸 | 说明 |
|------|------|------|
| **整体画布** | 1920×1080 | 固定尺寸，OBS 捕获用 |
| **MainView** | 1400×800 | 主画面显示区 |
| **DanmakuPanel** | 420×800 | 弹幕列表区 |
| **InfoBar** | 1880×60 | 底部信息栏 |
| **TopDecoration** | 1920×80 | 顶部装饰 |
| **BottomDecoration** | 1920×100 | 底部花卉 |

### 2.3 颜色主题

```css
:root {
  /* 背景色 */
  --bg-primary: #f5f5f0;
  --bg-secondary: #e8f0e8;
  --bg-danmaku: rgba(232, 240, 232, 0.95);
  
  /* 强调色 */
  --accent-green: #7da87d;
  --accent-light: #a8c8a8;
  --accent-dark: #5a7a5a;
  
  /* 文字色 */
  --text-primary: #4a5a4a;
  --text-secondary: #6b7a6b;
  --text-muted: #8a9a8a;
  
  /* 边框 */
  --border-color: #c5d5c5;
  --border-radius-lg: 20px;
  --border-radius-md: 12px;
  --border-radius-sm: 8px;
}
```

### 2.4 字体规范

```css
/* 字体栈 */
--font-primary: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;

/* 字号规范 */
--font-size-xs: 12px;    /* 辅助信息 */
--font-size-sm: 14px;    /* 次要内容 */
--font-size-base: 16px;  /* 正文 */
--font-size-lg: 18px;    /* 小标题 */
--font-size-xl: 24px;    /* 大标题 */
--font-size-2xl: 32px;   /* 特大标题 */

/* 字重 */
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
```

---

## 三、组件架构

### 3.1 组件树结构

```
App.vue
├── LiveStreamLayout.vue (主布局容器)
│   ├── TopDecoration.vue (顶部装饰边框)
│   │   ├── LaceBorder.vue (蕾丝边框效果)
│   │   └── FlowerOrnament.vue (花卉装饰元素)
│   │
│   ├── MainContent.vue (中间内容区)
│   │   ├── MainView.vue (主画面区域)
│   │   │   ├── Placeholder.vue (占位符/预览图)
│   │   │   └── Overlay.vue (可选: 叠加层)
│   │   │
│   │   └── DanmakuPanel.vue (右侧弹幕面板)
│   │       ├── PanelHeader.vue (面板标题 "實時評論")
│   │       ├── DanmakuList.vue (弹幕列表容器)
│   │       │   └── DanmakuItem.vue (单条弹幕) × N
│   │       └── PanelFooter.vue (面板底部装饰)
│   │
│   ├── BottomDecoration.vue (底部花卉装饰)
│   │   ├── FlowerLeft.vue (左侧花卉)
│   │   ├── FlowerRight.vue (右侧花卉)
│   │   └── VinePattern.vue (藤蔓图案)
│   │
│   └── InfoBar.vue (底部信息栏)
│       ├── ClockDisplay.vue (时钟显示)
│       ├── MarqueeText.vue (跑马灯滚动文字)
│       └── NoticeBadge.vue (NOTICE 标签)
│
└── [全局组件]
    ├── LoadingSpinner.vue (加载动画)
    └── ToastNotification.vue (通知提示)
```

### 3.2 组件职责说明

#### TopDecoration.vue
- 渲染顶部蕾丝风格边框
- 包含中央花卉装饰元素
- 支持半透明渐变效果

#### MainView.vue
- 主画面显示区域 (16:9)
- 预留 VTuber 形象或游戏画面位置
- 支持图片/视频源切换
- 可选叠加层 (如状态指示)

#### DanmakuPanel.vue
- 实时评论显示面板
- 固定高度，内容可滚动
- 新消息入场动画
- 自动滚动到最新

#### DanmakuItem.vue
- 单条弹幕渲染
- 显示用户名 + 内容 + 时间戳
- 支持不同样式 (普通/高亮/礼物/系统)

#### InfoBar.vue
- 底部信息栏容器
- 左侧: 实时时钟
- 中间: 跑马灯公告/活动信息
- 右侧: NOTICE 标签

#### BottomDecoration.vue
- 底部花卉装饰元素
- 左右对称布局
- 半透明 PNG/SVG 图案

---

## 四、数据流与状态管理

### 4.1 Pinia Store 结构

```typescript
// stores/danmaku.ts - 弹幕状态
interface DanmakuStore {
  // 状态
  danmakuList: DanmakuMessage[]      // 弹幕列表 (最多保留100条)
  isConnected: boolean               // Socket 连接状态
  
  // 操作
  addDanmaku(message: DanmakuMessage): void
  clearDanmaku(): void
  connect(): void
  disconnect(): void
}

// stores/stream.ts - 直播状态
interface StreamStore {
  // 状态
  currentTime: string                // 当前时间
  isStreaming: boolean               // 是否在直播
  streamTitle: string                // 直播标题
  announcement: string               // 公告/活动信息
  viewerCount: number                // 观看人数
  
  // 操作
  updateAnnouncement(text: string): void
  setStreaming(status: boolean): void
}

// stores/config.ts - UI配置
interface ConfigStore {
  // 状态
  theme: 'light' | 'dark'            // 主题模式
  showDecorations: boolean           // 是否显示装饰
  danmakuSpeed: number               // 弹幕滚动速度
  fontSize: number                   // 字体大小
  
  // 操作
  updateConfig(config: Partial<Config>): void
}
```

### 4.2 数据类型定义

```typescript
// types/danmaku.ts
export interface DanmakuMessage {
  id: string
  user: string           // 用户名
  content: string        // 弹幕内容
  timestamp: Date        // 发送时间
  type: DanmakuType      // 弹幕类型
  color?: string         // 自定义颜色 (VIP用户)
  badge?: string         // 徽章 (管理员/房管等)
}

export enum DanmakuType {
  NORMAL = 'normal',        // 普通弹幕
  HIGHLIGHT = 'highlight',  // 高亮 (被选中回复)
  GIFT = 'gift',            // 礼物
  SYSTEM = 'system',        // 系统消息
  WELCOME = 'welcome'       // 进入直播间
}

// types/stream.ts
export interface StreamStatus {
  isLive: boolean
  title: string
  startTime?: Date
  viewerCount: number
  currentTopic?: string      // 当前话题
}

// types/config.ts
export interface UIConfig {
  resolution: {
    width: number
    height: number
  }
  theme: ThemeColors
  animations: AnimationSettings
}
```

---

## 五、API 与通信协议

### 5.1 Socket.IO 事件定义

#### 客户端 → 服务端 (发送)

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `connect` | - | 建立连接 |
| `disconnect` | - | 断开连接 |
| `join_room` | `{ roomId: string }` | 加入直播间 |

#### 服务端 → 客户端 (接收)

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `danmaku` | `DanmakuMessage` | 新弹幕到达 |
| `danmaku_batch` | `DanmakuMessage[]` | 批量弹幕 (重连时) |
| `stream_status` | `StreamStatus` | 直播状态更新 |
| `announcement` | `{ text: string }` | 公告更新 |
| `viewer_count` | `{ count: number }` | 观众数更新 |
| `topic_change` | `{ topic: string }` | 话题变更 |
| `ai_status` | `{ thinking: boolean, speaking: boolean }` | AI 状态 |

### 5.2 REST API (可选)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/stream/status` | 获取直播状态 |
| GET | `/api/danmaku/recent?limit=50` | 获取最近弹幕 |
| GET | `/api/config/ui` | 获取UI配置 |
| PUT | `/api/config/ui` | 更新UI配置 |

### 5.3 Socket.IO 服务封装

```typescript
// services/socket.ts
import { io, Socket } from 'socket.io-client'

class SocketService {
  private socket: Socket | null = null
  private url: string
  
  connect(url: string): void {
    this.socket = io(url, {
      transports: ['websocket'],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000
    })
    
    this.setupListeners()
  }
  
  private setupListeners(): void {
    if (!this.socket) return
    
    this.socket.on('connect', () => {
      console.log('已连接到服务器')
      this.socket?.emit('join_room', { roomId: 'live' })
    })
    
    this.socket.on('danmaku', (message: DanmakuMessage) => {
      useDanmakuStore().addDanmaku(message)
    })
    
    this.socket.on('stream_status', (status: StreamStatus) => {
      useStreamStore().updateStatus(status)
    })
    
    // ... 其他事件监听
  }
  
  disconnect(): void {
    this.socket?.disconnect()
    this.socket = null
  }
}

export const socketService = new SocketService()
```

---

## 六、Mock 数据设计

### 6.1 Mock 弹幕数据

```typescript
// mock/danmaku.ts
export const mockDanmakuMessages: DanmakuMessage[] = [
  {
    id: '1',
    user: '樱花飘落',
    content: '主播今天好漂亮啊~',
    timestamp: new Date(Date.now() - 5000),
    type: DanmakuType.NORMAL
  },
  {
    id: '2',
    user: '游戏达人',
    content: '这把能赢吗？感觉对面好强',
    timestamp: new Date(Date.now() - 4000),
    type: DanmakuType.NORMAL
  },
  {
    id: '3',
    user: '✨月兔酱✨',
    content: '来了来了！打卡打卡！',
    timestamp: new Date(Date.now() - 3000),
    type: DanmakuType.WELCOME,
    badge: '粉丝牌'
  },
  {
    id: '4',
    user: '技术宅',
    content: '请问这个配置大概多少钱？想组装一台类似的',
    timestamp: new Date(Date.now() - 2000),
    type: DanmakuType.HIGHLIGHT,
    color: '#7da87d'
  },
  {
    id: '5',
    user: '系统消息',
    content: '感谢「星辰大海」赠送的火箭 x1',
    timestamp: new Date(Date.now() - 1000),
    type: DanmakuType.GIFT
  },
  // ... 更多mock数据
]
```

### 6.2 Mock 直播状态

```typescript
// mock/stream.ts
export const mockStreamStatus: StreamStatus = {
  isLive: true,
  title: '🌸 春日游戏时光 - 和大家一起玩游戏',
  startTime: new Date(Date.now() - 3600000), // 1小时前开始
  viewerCount: 1234,
  currentTopic: '讨论游戏配置推荐'
}

export const mockAnnouncement = '欢迎来到直播间！这里是个人简介/活动信息，这里是个人的简介/活动信息这里是个人的简介/活动信息，个人简介'
```

### 6.3 Mock 数据自动生成

```typescript
// mock/generator.ts
const randomUsers = ['樱花飘落', '游戏达人', '月兔酱', '技术宅', '星空漫步者', 
                     '咖啡爱好者', '音乐精灵', '动漫迷', '程序员小王', '设计师小李']

const randomContents = [
  '主播加油！',
  '这个操作太秀了！',
  '哈哈哈笑死我了',
  '学到了学到了',
  '666666',
  '主播声音好好听~',
  '这游戏我也在玩！',
  '求推荐配置',
  '几点下播呀？',
  '第一次来，关注了！'
]

export function generateRandomDanmaku(): DanmakuMessage {
  return {
    id: Math.random().toString(36).substr(2, 9),
    user: randomUsers[Math.floor(Math.random() * randomUsers.length)],
    content: randomContents[Math.floor(Math.random() * randomContents.length)],
    timestamp: new Date(),
    type: DanmakuType.NORMAL
  }
}
```

---

## 七、动画与交互细节

### 7.1 弹幕入场动画

```css
.danmaku-item-enter-active {
  animation: slideInRight 0.3s ease-out;
}

@keyframes slideInRight {
  from {
    opacity: 0;
    transform: translateX(20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
```

### 7.2 跑马灯动画

```css
.marquee-container {
  overflow: hidden;
  white-space: nowrap;
}

.marquee-text {
  display: inline-block;
  animation: marquee 20s linear infinite;
}

@keyframes marquee {
  0% {
    transform: translateX(0);
  }
  100% {
    transform: translateX(-50%);
  }
}
```

### 7.3 时钟闪烁效果

```css
.clock-colon {
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
```

### 7.4 装饰元素微动效

```css
/* 花卉轻微摇曳 */
.flower-ornament {
  animation: gentleSway 4s ease-in-out infinite;
  transform-origin: bottom center;
}

@keyframes gentleSway {
  0%, 100% { transform: rotate(-2deg); }
  50% { transform: rotate(2deg); }
}
```

---

## 八、项目目录结构

```
frontend/
├── public/
│   └── images/                      # 静态图片资源
│       ├── decorations/             # 装饰素材
│       │   ├── top-border.png
│       │   ├── flower-left.png
│       │   ├── flower-right.png
│       │   └── lace-pattern.svg
│       └── backgrounds/             # 背景图
│           └── main-bg.jpg
│
├── src/
│   ├── assets/                      # 资源文件
│   │   └── styles/
│   │       ├── main.css             # 全局样式
│   │       ├── variables.css        # CSS变量
│   │       └── animations.css       # 动画定义
│   │
│   ├── components/                  # 组件目录
│   │   ├── layout/                  # 布局组件
│   │   │   ├── LiveStreamLayout.vue
│   │   │   ├── TopDecoration.vue
│   │   │   └── BottomDecoration.vue
│   │   │
│   │   ├── mainview/                # 主画面组件
│   │   │   └── MainView.vue
│   │   │
│   │   ├── danmaku/                 # 弹幕组件
│   │   │   ├── DanmakuPanel.vue
│   │   │   ├── DanmakuList.vue
│   │   │   └── DanmakuItem.vue
│   │   │
│   │   ├── infobar/                 # 信息栏组件
│   │   │   ├── InfoBar.vue
│   │   │   ├── ClockDisplay.vue
│   │   │   └── MarqueeText.vue
│   │   │
│   │   └── common/                  # 公共组件
│   │       ├── LoadingSpinner.vue
│   │       └── ToastNotification.vue
│   │
│   ├── composables/                 # 组合式函数
│   │   ├── useClock.ts              # 时钟逻辑
│   │   ├── useSocket.ts             # Socket连接
│   │   └── useAnimation.ts          # 动画控制
│   │
│   ├── stores/                      # Pinia状态管理
│   │   ├── danmaku.ts
│   │   ├── stream.ts
│   │   └── config.ts
│   │
│   ├── services/                    # 服务层
│   │   ├── socket.ts                # Socket.IO封装
│   │   └── api.ts                   # REST API封装
│   │
│   ├── types/                       # TypeScript类型
│   │   ├── danmaku.ts
│   │   ├── stream.ts
│   │   └── config.ts
│   │
│   ├── mock/                        # Mock数据
│   │   ├── danmaku.ts
│   │   ├── stream.ts
│   │   └── generator.ts
│   │
│   ├── App.vue                      # 根组件
│   ├── main.ts                      # 入口文件
│   └── env.d.ts                     # 环境类型声明
│
├── index.html                       # HTML入口
├── package.json                     # 依赖配置
├── tsconfig.json                    # TS配置
├── tailwind.config.js               # Tailwind配置
├── vite.config.ts                   # Vite配置
└── README.md                        # 项目说明
```

---

## 九、开发计划

### Phase 1: 基础框架 (当前阶段)
- [x] 架构设计与文档编写
- [ ] Vue项目初始化 (Vite + TypeScript)
- [ ] Tailwind CSS 配置
- [ ] 基础布局实现 (固定1920×1080)

### Phase 2: 核心组件
- [ ] MainView 主画面区域
- [ ] DanmakuPanel 弹幕面板
- [ ] InfoBar 信息栏 (时钟+跑马灯)
- [ ] 装饰元素 (顶边框+底花卉)

### Phase 3: 数据与通信
- [ ] Pinia Store 实现
- [ ] Mock 数据服务
- [ ] Socket.IO 集成
- [ ] API 服务层

### Phase 4: 动画与优化
- [ ] 入场/退场动画
- [ ] 微动效 (花卉摇曳等)
- [ ] 性能优化
- [ ] OBS 兼容性测试

---

## 十、注意事项

### 10.1 OBS 浏览器源设置
1. URL 填入本地开发地址 (如 `http://localhost:5173`)
2. 设置宽高为 1920×1080
3. 自定义CSS添加 `background: transparent !important;`
4. 关闭"关闭时刷新浏览器"选项
5. 硬件加速根据显卡选择

### 10.2 性能考虑
- 弹幕列表虚拟滚动 (如果数量>50)
- 使用 CSS transform 做动画 (GPU加速)
- 图片资源使用 WebP 格式
- Socket.IO 心跳检测

### 10.3 响应式适配
- 主要针对 1920×1080 分辨率
- 开发时可缩放浏览器窗口查看
- 生产环境固定尺寸输出
