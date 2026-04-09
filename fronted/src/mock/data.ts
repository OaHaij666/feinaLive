import { DanmakuType } from '@/types/danmaku'

export const mockDanmakuMessages = [
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
  }
]

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
  '第一次来，关注了！',
  '太厉害了吧',
  '主播好可爱',
  '冲冲冲！',
  '支持支持',
  '来了老铁'
]

export function generateRandomDanmaku() {
  return {
    id: Math.random().toString(36).substr(2, 9),
    user: randomUsers[Math.floor(Math.random() * randomUsers.length)],
    content: randomContents[Math.floor(Math.random() * randomContents.length)],
    timestamp: new Date(),
    type: DanmakuType.NORMAL
  }
}

export const mockStreamStatus = {
  isLive: true,
  title: '🌸 春日游戏时光 - 和大家一起玩游戏',
  startTime: new Date(Date.now() - 3600000),
  viewerCount: 1234,
  currentTopic: '讨论游戏配置推荐'
}

export const mockAnnouncement = '欢迎来到直播间！这里是个人简介/活动信息，这里是个人的简介/活动信息这里是个人的简介/活动信息，个人简介'
