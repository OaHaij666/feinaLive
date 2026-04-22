# 前端组件说明

## 组件分类

### 1. 布局组件

#### TopDecoration

**位置**：`components/layout/TopDecoration.vue`

**功能**：页面顶部装饰区域

**用途**：
- 展示直播间顶部视觉效果
- 可包含 Logo、标题等元素

---

#### BottomDecoration

**位置**：`components/layout/BottomDecoration.vue`

**功能**：页面底部装饰区域

**用途**：
- 展示直播间底部视觉效果
- 可包含版权信息等

---

### 2. 主视图组件

#### MainView

**位置**：`components/mainview/MainView.vue`

**功能**：主视图容器组件

**子组件**：
- InfoBar（信息栏）
- DanmakuPanel（弹幕面板）
- MusicPlayer（音乐播放器）

---

### 3. 信息栏组件

#### InfoBar

**位置**：`components/infobar/InfoBar.vue`

**功能**：顶部信息展示栏

**子组件**：
- ClockDisplay（时钟）
- MarqueeText（跑马灯）
- NoticeBadge（公告徽章）

**数据来源**：
- 时钟：本地时间
- 公告：配置文件

---

#### ClockDisplay

**位置**：`components/infobar/ClockDisplay.vue`

**功能**：实时时钟显示

**特点**：
- 实时更新
- 格式化显示

---

#### MarqueeText

**位置**：`components/infobar/MarqueeText.vue`

**功能**：跑马灯文字滚动

**用途**：
- 展示公告信息
- 循环滚动显示

---

#### NoticeBadge

**位置**：`components/infobar/NoticeBadge.vue`

**功能**：公告徽章显示

---

### 4. 弹幕组件

#### DanmakuPanel

**位置**：`components/danmaku/DanmakuPanel.vue`

**功能**：弹幕展示面板

**职责**：
- 接收 WebSocket 弹幕消息
- 管理弹幕列表显示
- 处理弹幕滚动动画

**状态依赖**：`danmaku.ts` store

---

#### DanmakuItem

**位置**：`components/danmaku/DanmakuItem.vue`

**功能**：单条弹幕显示

**Props**：

| 属性 | 类型 | 说明 |
|-----|------|------|
| danmaku | Danmaku | 弹幕数据对象 |

**特点**：
- 支持不同弹幕类型样式
- 支持颜色显示
- 支持粉丝牌显示

---

### 5. 音乐组件

#### MusicPlayer

**位置**：`components/music/MusicPlayer.vue`

**功能**：音乐播放器控制面板

**职责**：
- 显示当前播放歌曲信息
- 播放/暂停控制
- 音量控制
- 下一首/跳过

**状态依赖**：`music.ts` store

---

### 6. 面板组件

#### MissionPanel

**位置**：`components/panels/MissionPanel.vue`

**功能**：任务面板显示

---

#### PlaceholderPanel

**位置**：`components/panels/PlaceholderPanel.vue`

**功能**：占位面板

---

### 7. 弹出层组件

#### SettingsPanel

**位置**：`components/SettingsPanel.vue`

**功能**：设置面板

**职责**：
- SESSDATA 配置
- 其他系统设置

---

#### PlayUnlockModal

**位置**：`components/PlayUnlockModal.vue`

**功能**：播放解锁弹窗

**用途**：
- 用户首次交互时弹出
- 解锁音频播放权限

---

#### SessdataWarningModal

**位置**：`components/SessdataWarningModal.vue`

**功能**：SESSDATA 警告弹窗

**触发条件**：SESSDATA 无效或未配置

---

#### NotificationToast

**位置**：`components/NotificationToast.vue`

**功能**：通知提示组件

**用途**：
- 显示系统通知
- 显示错误提示
- 显示成功消息

---

#### DanmakuTestPanel

**位置**：`components/DanmakuTestPanel.vue`

**功能**：弹幕测试面板

**用途**：
- 测试环境下模拟发送弹幕
- 调试弹幕处理流程

---

## 组件通信方式

```
┌─────────────────────────────────────────────────────────────────┐
│                     组件通信方式                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   1. Props / Emit (父子组件通信)                               │
│                                                                 │
│      父组件 ──── Props ────▶ 子组件                            │
│      父组件 ◀─── Emit ────── 子组件                            │
│                                                                 │
│                                                                 │
│   2. Pinia Store (跨组件状态共享)                              │
│                                                                 │
│      组件A ────▶ Store ◀───▶ 组件B                            │
│                                                                 │
│                                                                 │
│   3. Composables (逻辑复用)                                    │
│                                                                 │
│      组件 ────▶ useXxx() ────▶ 封装的逻辑                      │
│                                                                 │
│                                                                 │
│   4. Provide / Inject (深层组件通信)                           │
│                                                                 │
│      祖先组件 ──── Provide ────▶ 后代组件                      │
│      祖先组件 ◀─── Inject ───── 后代组件                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 组件生命周期

```
┌─────────────────────────────────────────────────────────────────┐
│                    Vue 组件生命周期                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐                                              │
│   │  setup()    │ ◀─── 组合式API入口                          │
│   └──────┬──────┘                                              │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                              │
│   │ onBeforeMount│ ◀─── 挂载前                                 │
│   └──────┬──────┘                                              │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                              │
│   │  onMounted  │ ◀─── 挂载后（常用：发起请求、建立连接）      │
│   └──────┬──────┘                                              │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                              │
│   │onBeforeUpdate│ ◀─── 更新前                                 │
│   └──────┬──────┘                                              │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                              │
│   │  onUpdated  │ ◀─── 更新后                                  │
│   └──────┬──────┘                                              │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                              │
│   │onBeforeUnmount│ ◀─── 卸载前                                │
│   └──────┬──────┘                                              │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                              │
│   │  onUnmounted│ ◀─── 卸载后（常用：清理连接、定时器）        │
│   └─────────────┘                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 相关文档

- [项目结构](./project-structure.md)
- [状态管理](./stores.md)
