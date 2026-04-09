# DNA Builder API 文档

> 《二重螺旋》游戏数据 GraphQL API 接口文档

## 基本信息

| 项目 | 说明 |
|------|------|
| **API 端点** | `https://api.dna-builder.cn/graphql` |
| **请求方式** | POST |
| **Content-Type** | `application/json` |
| **数据格式** | GraphQL |

---

## 快速开始

### 基础请求示例

```bash
curl -X POST https://api.dna-builder.cn/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "{ missionsIngame(server: \"cn\") { id server missions createdAt } }"}'
```

### JavaScript/TypeScript 调用

```typescript
const query = `
  query {
    missionsIngame(server: "cn") {
      id
      server
      missions
      createdAt
    }
  }
`;

const response = await fetch('https://api.dna-builder.cn/graphql', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query })
});

const data = await response.json();
console.log(data.data.missionsIngame);
```

### Python 调用

```python
import requests

query = '''
{
  missionsIngame(server: "cn") {
    id
    server
    missions
    createdAt
  }
}
'''

response = requests.post(
    'https://api.dna-builder.cn/graphql',
    json={'query': query}
)
data = response.json()
print(data['data']['missionsIngame'])
```

---

## 核心 API 接口

### 1. 委托密函查询 (⭐ 推荐)

获取当前游戏内委托密函的关卡轮换信息。

#### 接口

```graphql
missionsIngame(server: String!): MissionsIngame
```

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| server | String | ✅ | 服务器区域，可选值：`"cn"` (国服) |

#### 返回字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int! | 记录 ID |
| server | String! | 服务器区域 |
| missions | [[String]]! | 密函关卡二维数组 |
| createdAt | String | 数据更新时间 |

#### missions 字段说明

`missions` 是一个二维数组，包含三类密函的关卡组合：

| 索引 | 类型 | 说明 |
|------|------|------|
| `missions[0]` | 角色密函 | 角色突破素材关卡 |
| `missions[1]` | 武器密函 | 武器突破素材关卡 |
| `missions[2]` | 魔之楔密函 | MOD 素材关卡 |

每个数组包含 3 个关卡名称，表示当前小时轮换的关卡组合。

#### 请求示例

```graphql
query {
  missionsIngame(server: "cn") {
    id
    server
    missions
    createdAt
  }
}
```

#### 返回示例

```json
{
  "data": {
    "missionsIngame": {
      "id": 2259,
      "server": "cn",
      "missions": [
        ["避险", "拆解", "驱逐"],
        ["调停", "拆解", "驱离"],
        ["调停", "避险", "探险/无尽"]
      ],
      "createdAt": "2026/4/8 19:01:14"
    }
  }
}
```

---

### 2. 历史委托密函查询

获取历史委托密函记录。

#### 接口

```graphql
missionsIngames(server: String!, limit: Int, offset: Int): [MissionsIngame]
```

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| server | String | ✅ | 服务器区域 |
| limit | Int | ❌ | 返回数量限制 |
| offset | Int | ❌ | 偏移量 |

#### 请求示例

```graphql
query {
  missionsIngames(server: "cn", limit: 5, offset: 0) {
    id
    missions
    createdAt
  }
}
```

---

### 3. 活动列表查询

获取游戏内活动列表。

#### 接口

```graphql
activities(server: String!, startTime: DateTime, endTime: DateTime): [Activity]
```

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| server | String | ✅ | 服务器区域 |
| startTime | DateTime | ❌ | 开始时间筛选 |
| endTime | DateTime | ❌ | 结束时间筛选 |

#### 返回字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int | 活动 ID |
| name | String | 活动名称 |
| startTime | Int | 开始时间戳 (毫秒) |
| endTime | Int | 结束时间戳 (毫秒) |

#### 请求示例

```graphql
query {
  activities(server: "cn") {
    id
    name
    startTime
    endTime
  }
}
```

#### 返回示例

```json
{
  "data": {
    "activities": [
      {
        "id": 26,
        "name": "委托密函轮换-卡米拉",
        "startTime": 1777910400000,
        "endTime": 1777996799000
      },
      {
        "id": 29,
        "name": "【定格的往事】",
        "startTime": 1775664000000,
        "endTime": 1776700799000
      }
    ]
  }
}
```

---

### 4. 角色构建查询

获取用户分享的角色构建方案。

#### 接口

```graphql
builds(search: String, charId: Int, userId: String, limit: Int, offset: Int, sortBy: String): [Build]
buildsCount(search: String, charId: Int): Int
build(id: String!): Build
recommendedBuilds(limit: Int): [Build]
trendingBuilds(limit: Int): [Build]
```

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| search | String | ❌ | 搜索关键词 |
| charId | Int | ❌ | 角色 ID |
| userId | String | ❌ | 用户 ID |
| limit | Int | ❌ | 返回数量限制 |
| offset | Int | ❌ | 偏移量 |
| sortBy | String | ❌ | 排序方式 |

#### Build 类型字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String! | 构建 ID |
| title | String! | 构建标题 |
| desc | String | 构建描述 |
| charId | Int! | 角色 ID |
| charSettings | String! | 角色配置 (JSON) |
| userId | String! | 用户 ID |
| views | Int! | 浏览量 |
| likes | Int! | 点赞数 |
| isRecommended | Boolean | 是否推荐 |
| isPinned | Boolean | 是否置顶 |
| createdAt | String! | 创建时间 |
| updateAt | String! | 更新时间 |
| user | User | 用户信息 |
| isLiked | Boolean | 当前用户是否点赞 |

#### 请求示例

```graphql
query {
  builds(charId: 1801, limit: 5) {
    id
    title
    charId
    views
    likes
    createdAt
  }
}
```

#### 返回示例

```json
{
  "data": {
    "builds": [
      {
        "id": "EaqP0_efVi",
        "title": "纯输出副C菲娜构筑",
        "charId": 1801,
        "views": 9,
        "likes": 0,
        "createdAt": "2026/4/8 12:31:39"
      }
    ]
  }
}
```

---

### 5. 技能时间线查询

获取角色技能释放时间线配置。

#### 接口

```graphql
timelines(search: String, charId: Int, userId: String, limit: Int, offset: Int, sortBy: String): [Timeline]
timelinesCount(search: String, charId: Int): Int
timeline(id: String!): Timeline
recommendedTimelines(limit: Int): [Timeline]
trendingTimelines(limit: Int): [Timeline]
```

#### Timeline 类型字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String! | 时间线 ID |
| title | String! | 标题 |
| charId | Int! | 角色 ID |
| charName | String! | 角色名称 |
| tracks | String! | 轨道配置 (JSON) |
| items | String! | 时间线项目 (JSON) |
| userId | String! | 用户 ID |
| views | Int! | 浏览量 |
| likes | Int! | 点赞数 |
| isRecommended | Boolean | 是否推荐 |
| isPinned | Boolean | 是否置顶 |
| createdAt | String! | 创建时间 |
| updateAt | String! | 更新时间 |
| user | User | 用户信息 |
| isLiked | Boolean | 当前用户是否点赞 |

---

### 6. DPS 数据查询

获取角色 DPS 计算结果。

#### 接口

```graphql
dpsList(charId: Int, buildId: String, timelineId: String, limit: Int, offset: Int, sortBy: String): [DPS]
dpsCount(charId: Int, buildId: String, timelineId: String): Int
charDPS(charId: Int!, limit: Int): [DPS]
```

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| charId | Int | ✅ (charDPS) | 角色 ID |
| buildId | String | ❌ | 构建 ID |
| timelineId | String | ❌ | 时间线 ID |
| limit | Int | ❌ | 返回数量限制 |
| offset | Int | ❌ | 偏移量 |
| sortBy | String | ❌ | 排序方式 |

#### DPS 类型字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String! | DPS 记录 ID |
| charId | Int! | 角色 ID |
| buildId | String | 构建 ID |
| timelineId | String | 时间线 ID |
| dpsValue | Int! | DPS 数值 |
| details | String | 详细信息 (JSON) |
| userId | String! | 用户 ID |
| createdAt | String! | 创建时间 |
| updateAt | String! | 更新时间 |
| user | User | 用户信息 |
| build | Build | 构建信息 |
| timeline | Timeline | 时间线信息 |

#### 请求示例

```graphql
query {
  charDPS(charId: 1001, limit: 5) {
    id
    charId
    dpsValue
    buildId
    timelineId
  }
}
```

---

### 7. 攻略查询

获取游戏攻略内容。

#### 接口

```graphql
guides(search: String, type: String, charId: Int, userId: String, limit: Int, offset: Int): [Guide]
guidesCount(search: String, type: String): Int
guide(id: String!): Guide
```

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| search | String | ❌ | 搜索关键词 |
| type | String | ❌ | 攻略类型 |
| charId | Int | ❌ | 角色 ID |
| userId | String | ❌ | 用户 ID |
| limit | Int | ❌ | 返回数量限制 |
| offset | Int | ❌ | 偏移量 |

#### Guide 类型字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String! | 攻略 ID |
| title | String! | 标题 |
| type | String! | 类型 |
| content | String! | 内容 |
| images | [String]! | 图片列表 |
| charId | Int | 关联角色 ID |
| userId | String! | 用户 ID |
| buildId | String | 关联构建 ID |
| views | Int! | 浏览量 |
| likes | Int! | 点赞数 |
| isRecommended | Boolean | 是否推荐 |
| isPinned | Boolean | 是否置顶 |
| createdAt | String! | 创建时间 |
| updateAt | String! | 更新时间 |
| user | User | 用户信息 |
| isLiked | Boolean | 当前用户是否点赞 |

---

### 8. 脚本查询

获取自动化脚本。

#### 接口

```graphql
scripts(search: String, category: String, userId: String, limit: Int, offset: Int): [Script]
scriptsCount(search: String, category: String): Int
script(id: String!, preview: Boolean): Script
scriptCategories: [ScriptCategory]
scriptCategory(id: String!): ScriptCategory
scriptCategoriesCount: Int
```

#### Script 类型字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String! | 脚本 ID |
| title | String! | 标题 |
| description | String | 描述 |
| content | String! | 脚本内容 |
| category | String! | 分类 |
| userId | String! | 用户 ID |
| views | Int! | 浏览量 |
| likes | Int! | 点赞数 |
| isRecommended | Boolean | 是否推荐 |
| isPinned | Boolean | 是否置顶 |
| createdAt | String! | 创建时间 |
| updateAt | String! | 更新时间 |
| user | User | 用户信息 |
| isLiked | Boolean | 当前用户是否点赞 |

---

### 9. 深渊使用统计

获取深渊副本的角色/武器使用统计。

#### 接口

```graphql
abyssUsageSubmissions(limit: Int, offset: Int, seasonId: Int, minLevel: Int, maxLevel: Int): [AbyssSubmission]
abyssUsageSubmissionsCount(seasonId: Int, minLevel: Int, maxLevel: Int): Int
abyssUsageRoleStats(seasonId: Int, minLevel: Int, maxLevel: Int): [RoleStat]
abyssUsageWeaponStats(seasonId: Int, minLevel: Int, maxLevel: Int): [WeaponStat]
abyssUsageLineupStats(seasonId: Int, charId: Int, mainOnly: Boolean, limit: Int, minLevel: Int, maxLevel: Int): [LineupStat]
abyssUsageSlotStats(seasonId: Int, minLevel: Int, maxLevel: Int): [SlotStat]
abyssUsageLevelStats(seasonId: Int, minLevel: Int, maxLevel: Int): [LevelStat]
abyssUsageRoleRank(seasonId: Int, limit: Int, minLevel: Int, maxLevel: Int): [RoleRank]
abyssUsageWeaponRank(seasonId: Int, limit: Int, minLevel: Int, maxLevel: Int): [WeaponRank]
```

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| seasonId | Int | 赛季 ID |
| minLevel | Int | 最小层数 |
| maxLevel | Int | 最大层数 |
| charId | Int | 角色 ID |
| mainOnly | Boolean | 仅主角色 |
| limit | Int | 返回数量限制 |
| offset | Int | 偏移量 |

---

### 10. 商店商品查询

获取积分商店商品列表。

#### 接口

```graphql
shopProducts(limit: Int, offset: Int, search: String, rewardType: String, activeOnly: Boolean): [ShopProduct]
shopProductsCount(search: String, rewardType: String, activeOnly: Boolean): Int
myShopItems: [ShopItem]
myShopSummary: ShopSummary
```

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| search | String | 搜索关键词 |
| rewardType | String | 奖励类型 |
| activeOnly | Boolean | 仅显示活跃商品 |
| limit | Int | 返回数量限制 |
| offset | Int | 偏移量 |

---

### 11. 待办事项查询

获取用户待办事项。

#### 接口

```graphql
todos(type: String, limit: Int, offset: Int): [Todo]
todo(id: String!): Todo
todosCount(type: String): Int
```

---

### 12. 实时协作相关

实时房间和消息相关接口。

#### 接口

```graphql
room(id: String!): Room
rooms(name_like: String, limit: Int, offset: Int): [Room]
roomsCount(name_like: String): Int
msgCount(roomId: String!): Int
msgs(roomId: String!, limit: Int, offset: Int): [Message]
lastMsgs(roomId: String!, limit: Int, offset: Int): [Message]
tasks(roomId: String!, limit: Int, offset: Int): [Task]
doingTasks(roomId: String!): [Task]
rtcClients(roomId: String!): [RTCClient]
timeOffset(t: Int!): TimeOffset
```

---

## 完整 API 列表

| 接口名称 | 描述 | 主要参数 |
|----------|------|----------|
| `missionsIngame` | 获取当前委托密函 | server |
| `missionsIngames` | 获取历史委托密函 | server, limit, offset |
| `activities` | 获取活动列表 | server |
| `builds` | 获取角色构建列表 | charId, search, limit |
| `build` | 获取单个构建 | id |
| `recommendedBuilds` | 获取推荐构建 | limit |
| `trendingBuilds` | 获取热门构建 | limit |
| `timelines` | 获取时间线列表 | charId, search, limit |
| `timeline` | 获取单个时间线 | id |
| `recommendedTimelines` | 获取推荐时间线 | limit |
| `trendingTimelines` | 获取热门时间线 | limit |
| `charDPS` | 获取角色 DPS 数据 | charId, limit |
| `dpsList` | 获取 DPS 列表 | charId, buildId, timelineId |
| `guides` | 获取攻略列表 | search, type, charId |
| `guide` | 获取单个攻略 | id |
| `scripts` | 获取脚本列表 | search, category |
| `script` | 获取单个脚本 | id |
| `scriptCategories` | 获取脚本分类 | - |
| `abyssUsageRoleStats` | 深渊角色使用统计 | seasonId, minLevel, maxLevel |
| `abyssUsageWeaponStats` | 深渊武器使用统计 | seasonId, minLevel, maxLevel |
| `abyssUsageRoleRank` | 深渊角色排名 | seasonId, limit |
| `abyssUsageWeaponRank` | 深渊武器排名 | seasonId, limit |
| `shopProducts` | 商店商品列表 | search, rewardType |
| `todos` | 待办事项列表 | type |
| `room` | 获取房间 | id |
| `rooms` | 获取房间列表 | name_like |
| `msgs` | 获取房间消息 | roomId |
| `tasks` | 获取房间任务 | roomId |

---

## 使用建议

### 1. 委托密函实时监控

建议每小时调用一次 `missionsIngame` 接口获取最新的关卡轮换信息。

```typescript
async function fetchMissions() {
  const response = await fetch('https://api.dna-builder.cn/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: `{ missionsIngame(server: "cn") { id missions createdAt } }`
    })
  });
  return response.json();
}

setInterval(fetchMissions, 60 * 60 * 1000);
```

### 2. 活动时间转换

活动时间戳为毫秒级，需要转换：

```typescript
const startTime = new Date(activity.startTime);
const endTime = new Date(activity.endTime);
```

### 3. 错误处理

API 返回格式：

```json
{
  "data": { ... },
  "errors": [
    {
      "message": "错误信息",
      "locations": [{ "line": 1, "column": 10 }],
      "extensions": { "code": "GRAPHQL_VALIDATION_FAILED" }
    }
  ]
}
```

---

## 相关资源

- **DNA Builder 官网**: https://dna-builder.cn/
- **GitHub 仓库**: https://github.com/pa001024/dna-builder
- **npm 包**: `dna-api`, `dna-builder-data`

---

## 更新日志

| 日期 | 说明 |
|------|------|
| 2026-04-08 | 初始文档创建 |
