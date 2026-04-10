import type { MusicItem, QueueResponse } from '@/types/music'
import { MusicStatus } from '@/types/music'

const MOCK_AUDIO_URL = 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3'

export const MOCK_COVER_URL = 'https://pic.imgdb.cn/item/6238c2dc27f86bbe3b2cb0b6.jpg'

export const mockCurrentSong: MusicItem = {
  id: 'mock-1',
  bvid: 'BV1DghJzKEoK',
  title: '【AI少女】桜花下的约定 - 完整版',
  upName: 'Feina_Official',
  upFace: 'https://i0.hdslb.com/bfs/face/placeholder.gif',
  duration: 245,
  audioUrl: MOCK_AUDIO_URL,
  coverUrl: MOCK_COVER_URL,
  status: MusicStatus.PLAYING,
  requestedBy: 'admin',
  requestedAt: new Date(),
}

export const mockQueue: MusicItem[] = [
  {
    id: 'mock-2',
    bvid: 'BV1DghJzKEoK',
    title: '【Vocaloid】炉火炖融 - 极乐净土',
    upName: 'Feina_Official',
    upFace: 'https://i0.hdslb.com/bfs/face/placeholder.gif',
    duration: 198,
    audioUrl: MOCK_AUDIO_URL,
    coverUrl: MOCK_COVER_URL,
    status: MusicStatus.PENDING,
    requestedBy: 'user1',
    requestedAt: new Date(),
  },
  {
    id: 'mock-3',
    bvid: 'BV1DghJzKEoK',
    title: '【MMD】月下独酌 - 舞蹈版',
    upName: 'Feina_Official',
    upFace: 'https://i0.hdslb.com/bfs/face/placeholder.gif',
    duration: 312,
    audioUrl: MOCK_AUDIO_URL,
    coverUrl: MOCK_COVER_URL,
    status: MusicStatus.PENDING,
    requestedBy: 'user2',
    requestedAt: new Date(),
  },
  {
    id: 'mock-4',
    bvid: 'BV1DghJzKEoK',
    title: '【翻唱】时光正好 - 官方版',
    upName: 'Feina_Official',
    upFace: 'https://i0.hdslb.com/bfs/face/placeholder.gif',
    duration: 267,
    audioUrl: MOCK_AUDIO_URL,
    coverUrl: MOCK_COVER_URL,
    status: MusicStatus.PENDING,
    requestedBy: 'user3',
    requestedAt: new Date(),
  },
]

export function getMockQueueResponse(): QueueResponse {
  return {
    current: mockCurrentSong,
    queue: mockQueue,
    total: mockQueue.length,
  }
}
