# 心履 客户端 API 文档（v1）

> 本文档面向第三方客户端开发者，描述心履（xin-lv.com）为原生客户端提供的 REST API。
> 当前版本 `v1`，最后更新：2026-10-12。接口行为以线上实际返回为准。
>
> 本文只讲**心履自己的服务端**（`xin-lv.com`）。客户端还会用到 **phix 服务端**
> （`phix.ing`，统一账号 / 资料对象同步 / 跨站免密登录 / 应用内更新检查），
> 那部分见 `D:\phix\server\docs\协议规范.md` 与 `D:\phix\server\docs\同步实时化.md`。

---

## 1. 基本信息

| 项目 | 说明 |
|------|------|
| 基础地址 | `https://xin-lv.com` |
| API 前缀 | `/api/v1/` |
| 协议 | HTTPS，请求/响应正文均为 **UTF-8 JSON** |
| 认证方式 | `Authorization: Bearer <token>` 请求头（Token 登录后发放） |
| 时间格式 | ISO8601 带时区，如 `2026-08-18T09:30:00+08:00`；不带时区的时间服务端按 UTC 处理 |

**错误响应统一格式**（HTTP 状态码 + JSON）：

```json
{ "error": "中文错误描述" }
```

| 状态码 | 含义 |
|--------|------|
| 400 | 请求格式/参数错误（`error` 字段有中文说明，可直接展示给用户） |
| 401 | 未携带令牌 / 令牌无效或已注销 → 客户端应清除本地令牌并引导重新登录 |
| 405 | HTTP 方法不对（如 GET 打到了只收 POST 的端点） |
| 429 | 触发限流（目前登录/注册有频率限制），提示用户过几分钟再试 |

**通用注意事项**：

- 除标注"免认证"外，所有接口都必须带 `Authorization: Bearer <token>` 头。
- Token 长期有效（除非用户主动注销），一个账号可在多台设备同时登录，互不挤掉。客户端应把 Token 保存在本地安全存储中，**不要明文写日志，不要保存用户密码**。
- 所有响应中的 `server_time` 建议客户端保存，用于增量同步的 `since` 参数。

---

## 2. 心情枚举（全 API 通用）

`mood` 字段只能是以下 10 个 key 之一：

| key | 中文 | emoji | 主题色 | 情感倾向 |
|-----|------|-------|--------|----------|
| `happy` | 开心 | 😄 | #FFD56B | 正面 |
| `calm` | 平静 | 🙂 | #9BD1C6 | 正面 |
| `excited` | 兴奋 | 🤩 | #FF9F68 | 正面 |
| `grateful` | 感恩 | 🥰 | #F7A6C4 | 正面 |
| `tired` | 疲惫 | 😪 | #A6A6C9 | 负面 |
| `anxious` | 焦虑 | 😟 | #7FA6E8 | 负面 |
| `sad` | 难过 | 😢 | #6D8FB8 | 负面 |
| `angry` | 愤怒 | 😠 | #E8736B | 负面 |
| `lonely` | 孤独 | 🌧️ | #8E94B8 | 负面 |
| `numb` | 麻木 | 😶 | #B0B0B0 | 中性 |

心情记录还带两个强度字段：

- `intensity_level`：整数 1–4（1=略微，2=有点，3=相当，4=十分），默认 2，非法值会被服务端重置为 2。
- `intensity_percent`：整数 0–100，用于 UI 展示，默认 50，超范围会被裁剪到边界。

---

## 3. 认证相关

### 3.1 探活 `GET /api/v1/ping/`（免认证）

客户端用来判断在线/离线，也可校准服务器时间。

```bash
curl https://xin-lv.com/api/v1/ping/
```

```json
{ "ok": true, "version": "v1", "server_time": "2026-08-18T09:30:00.123456+08:00" }
```

### 3.2 注册 `POST /api/v1/register/`（免认证）

请求体：

```json
{ "username": "xiaoming", "password": "abc123", "agree": true, "device": "android-mi14" }
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `username` | 是 | ≤150 字符；只能含字母、数字、下划线、`.`、`@`、`+`、`-` 和中文；全局唯一 |
| `password` | 是 | ≥6 位 |
| `agree` | 是 | 必须为 `true`。客户端注册前**必须展示免责声明**（`https://xin-lv.com/disclaimer/`）并取得用户同意 |
| `device` | 否 | 设备备注（≤100 字符，如 `android-mi14`、`windows-pc`），方便用户管理设备 |

成功（200）：

```json
{ "token": "a1b2c3...（40 位十六进制）", "username": "xiaoming", "streak": 0 }
```

注册成功即发放令牌，客户端**不需要再调一次登录**。失败情况（均 400）：账号已被注册、密码太短、未同意免责声明、用户名非法；请求过于频繁返回 429。

### 3.3 登录 `POST /api/v1/login/`（免认证）

```json
{ "username": "xiaoming", "password": "abc123", "device": "windows-pc" }
```

成功（200）：

```json
{ "token": "a1b2c3...", "username": "xiaoming", "streak": 7 }
```

每次登录生成一个新令牌（按设备区分），旧设备的令牌不受影响。账号或密码错误返回 401。**令牌长期有效，客户端本地保存即可，后续所有请求都带它。**

### 3.4 注销 `POST /api/v1/logout/`（需认证）

只注销当前设备的令牌，其他设备不受影响。

```json
{ "ok": true }
```

---

## 4. 心情记录同步（核心）

心情记录是**追加型数据**：一天可以有多条，不存在"一天一条覆盖"的概念。多端同步遵循以下规则，客户端必须按此实现：

1. **uuid 去重**：客户端离线新建记录时，自己生成一个随机 uuid（推荐 UUID v4，36 字符以内）。uuid 是全局唯一键，服务端按 uuid 做 upsert。
2. **最新者赢（LWW）**：同一条记录在两端都被修改时，比较 `updated_at` 时间戳，新的覆盖旧的。服务端只信客户端带来的 `updated_at` 做比较。
3. **墓碑删除**：删除记录不真删，而是置 `deleted=true` 后照常同步（软删除），防止"删了又被同步回来"。客户端拉到 `deleted=true` 的条目应在本地删除或隐藏。
4. **增量拉取**：用上次拉取返回的 `server_time` 作为 `since`，只取之后有变化的条目（含墓碑）。不带 `since` 就是全量。

### 4.1 拉取 `GET /api/v1/sync/pull/?since=<ISO8601>`（需认证）

```
GET /api/v1/sync/pull/?since=2026-08-18T09%3A30%3A00%2B08%3A00
```

> ⚠️ **`since` 参数必须做 URL 编码！** ISO8601 时间里的 `+08:00` 如果不编码，`+` 会被服务端当成空格，导致解析失败**静默退化为全量拉取**。请使用语言自带的 query 编码工具（如 Java 的 `URLEncoder`、JS 的 `URLSearchParams`、Python 的 `urlencode`）。

成功（200）：

```json
{
  "server_time": "2026-08-18T10:00:00.100000+08:00",
  "entries": [
    {
      "uuid": "550e8400-e29b-41d4-a716-446655440000",
      "date": "2026-08-18",
      "at": "2026-08-18T09:30:00+08:00",
      "mood": "happy",
      "note": "今天天气很好",
      "deleted": false,
      "intensity_level": 2,
      "intensity_percent": 60,
      "created_at": "2026-08-18T09:30:01.000000+08:00",
      "updated_at": "2026-08-18T09:30:01.000000+08:00"
    }
  ]
}
```

- 条目按 `updated_at` 升序返回，单次最多 **2000** 条。数据更多的账号请循环拉取（用每次的 `server_time` 接着拉）。
- `date` 是 `YYYY-MM-DD`（按天归属）；`at` 是精确记录时刻（一天内多条排序用），可能为 null。

### 4.2 推送 `POST /api/v1/sync/push/`（需认证）

```json
{
  "entries": [
    {
      "uuid": "550e8400-e29b-41d4-a716-446655440000",
      "date": "2026-08-18",
      "at": "2026-08-18T09:30:00+08:00",
      "mood": "happy",
      "note": "今天天气很好",
      "intensity_level": 3,
      "intensity_percent": 75,
      "updated_at": "2026-08-18T09:30:00+08:00",
      "deleted": false
    }
  ]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `uuid` | 是 | ≤36 字符；若该 uuid 已被**其他用户**占用会报"uuid 冲突" |
| `date` | 是 | `YYYY-MM-DD`；不能是未来日期 |
| `mood` | 是 | 10 个合法 key 之一（墓碑条目除外） |
| `at` | 否 | 记录时刻，缺省用服务器当前时间 |
| `note` | 否 | 备注，≤2000 字符（超长自动截断） |
| `intensity_level` / `intensity_percent` | 否 | 默认 2 / 50 |
| `updated_at` | 建议 | 本条的最后修改时间；缺省按"服务器当前时间"处理 |
| `deleted` | 否 | `true` 表示删除（墓碑）；删除服务器上不存在的 uuid 会被安全跳过 |

规则：

- 单次最多 **500** 条（超出部分被忽略），请分批推送。
- **逐条独立处理**：某一条格式错误不影响其他条目。
- 按 uuid upsert：新 uuid → 新建（`saved`）；已存在且带来的 `updated_at` 更新 → 覆盖（`updated`）；已存在但不比服务器新 → 跳过（`skipped`）。

成功（200）：

```json
{
  "saved": 2,
  "updated": 1,
  "skipped": 0,
  "errors": [ { "index": 3, "uuid": "xxx", "error": "未知心情" } ],
  "server_time": "2026-08-18T10:00:00.100000+08:00"
}
```

### 4.3 长轮询 `GET /api/v1/sync/watch/?since=<光标>`（需认证）

**别的设备一改，这边立刻知道** —— 不用自己定时间隔去问，也不用等用户手动刷新。

请求挂在服务端不回，直到这个账号的心情数据真的变了、或挂满 **25 秒**才返回。
所以客户端的**读超时必须大于 25 秒**（各端现在给 35 秒）；给短了会在服务端刚要返回时
被本地掐断，长轮询就退化成"看起来像长轮询、其实一秒一次"的空轮询。

```jsonc
// 没带 since：当作第一次问，立刻回当前光标，不挂
{ "changed": false, "cursor": "3:2026-10-12T04:31:07.123456+00:00", "server_time": "..." }

// 挂满超时：没变化
{ "changed": false, "cursor": "...", "server_time": "..." }

// 服务端挂起名额满了：立刻回，**多一个 retry_after**
{ "changed": false, "cursor": "...", "retry_after": 1.0, "server_time": "..." }

// 真的变了
{ "changed": true,  "cursor": "...", "server_time": "..." }
```

`cursor` 是**不透明字符串**，客户端只负责原样回传（下一步放进 `since`），**不许解析**。
服务端从数据库现算（记录条数 + 最新 `updated_at`），换 worker、重启都不会漏变化。
`changed=true` 只**发信号**，客户端随即自己调 4.1 的 `sync/pull/` 把变化收下来。

#### ⚠️ 两种 `changed=false` 含义相反，必须分清

| 回包 | 含义 | 客户端该做什么 |
|---|---|---|
| `changed=false`，**没有** `retry_after` | 正常挂满 25 秒超时 | **立刻**再挂上（长轮询接力） |
| `changed=false`，**有** `retry_after` | 服务端同时挂起的个数满了 | 先等 `retry_after` 秒再挂 |

前两种在 HTTP 层长得**一模一样**，只能靠 `retry_after` 区分：

* 把"被打回"当"超时" → 立刻重挂 → **热循环打服务器**，比不挂还糟；
* 把"超时"当"被打回" → 每次多睡几秒 → **秒级延迟就没了**。

服务端同时挂起的个数有上限（默认 2，见服务端 `core/syncwatch.py` 的 `WATCH_SLOTS`），
因为挂起实打实占一个 waitress 线程：不设上限会被客户端把线程池占满，
连"把数据写进去、好让长轮询醒过来"的那个写请求都进不来。

#### 客户端该怎么用

```
1. 先 GET /api/v1/sync/watch/（不带 since）拿一个 cursor
2. 挂上：GET /api/v1/sync/watch/?since=<cursor>，读超时 35 秒
3. changed=true  → 更新 cursor → 跑一轮 4.1 的 pull（推+拉）→ 立刻重挂
   changed=false 且无 retry_after → 立刻重挂
   changed=false 且有 retry_after → 等 retry_after 秒再挂
4. 出错/断网 → 退避几秒重试；**异常要吞掉**，绝不能打断原本的定时/手动同步
5. 老服务端没有这个端点会返回 404 → 安静降级回原来的定时同步
```

**长轮询是优化，不是替换**：原有的定时同步与手动同步都要保留作兜底。

---

### 4.4 推荐的同步流程

```
应用启动 / 网络恢复：
1. push：把本地所有"脏"条目（新建/修改/删除未同步的）分批推上去
2. pull：GET sync/pull?since=<上次保存的 server_time>
3. 对每个返回条目：
   - 若本地不存在 → 新建（deleted=true 则直接不建/跳过）
   - 若本地存在且服务器 updated_at 更新 → 用服务器版本覆盖本地
4. 保存本次 server_time，作为下次 since
```

**跑完上面这一轮之后**，挂上 4.3 的长轮询。此后：云端一变 → 长轮询立刻返回
→ 再跑一轮上面的 1~4。这样延迟从一个轮询间隔降到一个 RTT（实测本机 0.03 秒、
经 Cloudflare 隧道 0.03~1 秒）。

---

## 5. 推荐内容

### 5.1 内容目录 `GET /api/v1/catalog/`（需认证）

返回全量内容目录（心情定义 + 音乐/建议/小知识/视频）。数据量小，客户端登录后**拉一次缓存到本地**，离线也能做推荐展示。音乐 `url` 是可直接播放的绝对地址。

```json
{
  "moods":     [ { "key": "happy", "label": "开心", "emoji": "😄", "color": "#FFD56B", "valence": 1, "image": "images/mood_happy.png" } ],
  "songs":     [ { "id": 1, "title": "歌名", "artist": "歌手", "url": "https://xin-lv.com/media/music/xx.mp3", "moods": ["happy", "calm"] } ],
  "activities":[ { "id": 1, "text": "出门散十分钟步", "moods": ["anxious"] } ],
  "tips":      [ { "id": 1, "title": "标题", "content": "正文", "source": "出处" } ],
  "videos":    [ { "id": 1, "title": "视频标题", "url": "https://b23.tv/xxx", "moods": ["sad"] } ]
}
```

### 5.2 获取推荐 `GET /api/v1/recommend/?mood=<key>`（需认证）

与网页端结果页同一套推荐逻辑。`mood` 必须是合法 key，否则 400。

```json
{
  "mood": "sad",
  "info": { "label": "难过", "emoji": "😢", "color": "#6D8FB8", "valence": -1 },
  "valence": -1,
  "songs":     [ { "title": "歌名", "artist": "歌手", "url": "https://xin-lv.com/media/music/xx.mp3" } ],
  "activities":[ "给自己泡一杯热饮" ],
  "tips":      [ { "title": "标题", "content": "正文", "source": "出处" } ],
  "practice":  "一段练习引导文案",
  "video":     { "title": "视频标题", "url": "https://b23.tv/xxx", "embed_url": "https://player.bilibili.com/..." }
}
```

`video` 可能为 `null`（该情绪暂无视频）。

---

## 6. AI 树洞（聊天）

### 6.1 发消息 `POST /api/v1/chat/`（需认证）

```json
{ "message": "今天有点难过" }
```

- 消息 ≤4000 字符（超长自动截断）；空消息 400。
- 服务端自动携带该用户最近 20 条对话作为上下文，**客户端不需要（也不应该）自己拼历史**。
- 每条消息（用户和 AI 的）服务端都会落库，多端历史互通。

成功（200）——普通回复：

```json
{ "reply": "听起来今天不容易……" }
```

**命中危机关键词时**（检测到自我伤害/自杀风险，AI 不参与回复，直接返回求助资源）：

```json
{
  "crisis": true,
  "reply": "（一段关怀话术与求助指引）",
  "hotline": "12356"
}
```

> ⚠️ 客户端收到 `crisis: true` 时，**必须醒目展示 `reply` 全文和 `hotline` 热线号码**（如弹窗/置顶卡片），不要折叠或弱化。这是产品安全要求，不是可选项。

发送过快触发限流时不返回 429，而是正常 200，`reply` 为一句温和提示（"你发得有点快啦……"），客户端当普通消息展示即可。

### 6.2 历史记录 `GET /api/v1/chat/history/`（需认证）

返回最近 50 条对话（**升序**），客户端进入聊天页时拉取渲染：

```json
{
  "messages": [
    { "role": "user",      "content": "今天有点难过", "created_at": "2026-08-18T09:30:00+08:00" },
    { "role": "assistant", "content": "听起来今天不容易……", "created_at": "2026-08-18T09:30:05+08:00" }
  ]
}
```

`role` 只有 `"user"` / `"assistant"` 两种。AI 主动消息（见下）也会出现在这个历史里，客户端可按 `content + created_at` 去重。

### 6.3 AI 主动消息轮询 `GET /api/v1/chat/proactive/?since=<ISO8601>`（需认证）

AI 会在一天内随机主动给用户发几条关怀消息，每周还会发一篇小结长文。客户端**建议每 60 秒轮询一次**（应用在前台时），把新消息用系统通知或聊天气泡展示（样式与普通 AI 回复一致）。

- 不带 `since`：返回最近 24 小时内的主动消息。
- 带 `since`：返回该时间之后新增的主动消息。
- 同样注意 `since` 要 URL 编码。

```json
{
  "server_time": "2026-08-18T10:00:00+08:00",
  "messages": [
    { "role": "assistant", "content": "午安～记得喝口水休息一下", "is_weekly_essay": false, "created_at": "2026-08-18T12:00:00+08:00" }
  ]
}
```

`is_weekly_essay: true` 表示这是每周小结长文，客户端可给一个特殊样式（如卡片/全屏阅读）。

### 6.4 清空对话 `POST /api/v1/chat/clear/`（需认证）

删除该用户的**全部**聊天记录（不可恢复，客户端应先向用户二次确认）：

```json
{ "ok": true }
```

---

## 7. 个人资料 `GET /api/v1/profile/`（需认证）

```json
{
  "username": "xiaoming",
  "bio": "每天好心情",
  "language": "zh",
  "avatar_url": "https://xin-lv.com/media/avatars/xx.jpg",
  "streak": 7,
  "badges": [
    { "emoji": "🌱", "name": "初心", "image": "images/badge_5.png", "desc": "连续记录 5 天", "days": 5 }
  ],
  "total_entries": 85,
  "date_joined": "2026-07-01T10:00:00+08:00"
}
```

- `avatar_url` 可能为空字符串（未设置头像）。
- `badges` 为已获得徽章列表（当前或历史最高连续天数达标即获得），可能为空数组。

徽章档位：

| 连续天数 | emoji | 名称 |
|----------|-------|------|
| 5 | 🌱 | 初心 |
| 30 | 🌿 | 坚持 |
| 100 | 🌳 | 百日 |
| 365 | 🏆 | 一年 |
| 1000 | 👑 | 千日 |

---

## 8. 小游戏参数 `GET /api/game-config/`（免认证，注意无 `/v1/`）

公开的合成小游戏物理参数，做游戏玩法的客户端可用：

```json
{ "gravity": 0.5, "damping": 0.99, "wall_bounce": 0.6, "merge_boost": 1.2, "updated_at": "..." }
```

---

## 9. 对接清单（第三方客户端 checklist）

- [ ] 所有请求走 `https://xin-lv.com`，JSON 编码 UTF-8。
- [ ] 登录/注册成功后本地安全保存 `token`；之后每个需认证请求带 `Authorization: Bearer <token>`。
- [ ] 收到 401 → 清除本地令牌，引导用户重新登录。
- [ ] 收到 429 → 提示"稍后再试"，不要自动重试轰炸。
- [ ] 同步：离线新建记录生成 uuid v4；`?since=` 参数**必须 URL 编码**；拉取后保存 `server_time`。
- [ ] 拉到 `deleted=true` 的条目 → 本地删除或隐藏；本地删除的记录置 `deleted=true` 推送，不要本地物理删除后就不推了。
- [ ] **长轮询**（4.3）：读超时给 35 秒（大于服务端 25 秒挂起）；`retry_after` 与"普通超时"要分开处理；异常一律吞掉并退避，不能打断定时同步；老服务端 404 要能安静降级。
- [ ] 心情 key、强度等级按第 2 节的枚举做输入校验。
- [ ] 聊天收到 `crisis: true` → 醒目展示回复全文与热线号码。

### 关于 phix 那边（不是本服务端，但客户端一般都要接）

- **应用内更新检查**：`GET https://phix.ing/api/v1/update/check?product=xinlv&platform=win|mac|android`
  （`product` 用 `xinlv`）。响应里有 `latest_version` / `url` / `sha256` / `size` / `notes`。
  客户端拿它和**自己当前版本**比，比它旧就提示更新。
- **「关于软件」里的手动「检查更新」**：复用同一个端点，但有一条硬性要求 ——
  **检查失败（断网 / 服务器不可达）只能显示「检查失败」，绝不能显示成「已是最新版本」。**
  这两件事看起来像、意思完全相反：把"没检查成"说成"已是最新"，用户会以为自己没落后，
  反而错过更新。所以「请求失败」和「确实没有新版本」在代码里必须是两条互斥的分支。
- 客户端还可能用到 phix 的统一账号、资料对象同步与跨站免密登录，见
  `D:\phix\server\docs\协议规范.md`。
- [ ] 注册流程必须先展示免责声明（`https://xin-lv.com/disclaimer/`）并取得用户明确同意（`agree=true`）。
- [ ] AI 主动消息：前台每 60 秒轮询 `/api/v1/chat/proactive/`，用系统通知或聊天气泡展示。
- [ ] 善待服务器：同步不要高频轮询（心情同步是"事件驱动 + 启动时"即可），聊天历史进入页面拉一次就够。
