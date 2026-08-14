# CLAUDE.md — 心履 项目交接文档

> 本文档给 AI（Claude Code）读，不是给人看的 README。只写事实和约定，不写部署流程。
> 每次修复一个坑或定下一条新约定，把它补进第 6 节，不要让这份文档过时。

> **改名史**：心情树洞 → 念今心（07-26）→ **心履**（07-27）。品牌资产 `D:\moodsite\logo.png`
> （无底，网页 UI 用）/ `logo.jpg`（有底，客户端图标用）/ `fruits.png`（大西瓜游戏贴图）。
> 网页端 logo/favicon 在 `static/images/`，水果贴图在 `static/images/fruits/`（f0~f10 十一张
> 已齐，由 fruits.png 按两行布局切分：上排小→大=f0~f6，下排大→小=f10~f7；缺图时游戏回退
> emoji）。改图后必须 `collectstatic`；**新增静态文件还要重启 waitress**（whitenoise 进程内
> 索引在启动时建立，新文件不重启 404）。

## 1. 项目概述

"心履"（曾用名"心情树洞""念今心"）是 Django 全栈的青少年心理陪伴 Web 应用：记录每日情绪（一天可多条）、
按情绪推荐音乐/建议/小知识/视频、与 AI 树洞（DeepSeek）文字+语音聊天（内置关键词危
机硬拦截）、连胜徽章、用户主页、用户投稿+AI审核、后台管理、中英双语、放松小游戏。
部署在局域网 Linux 生产机 **192.168.5.35**（Ubuntu 24.04，路径 `/home/hzq/xinlv-web`，SSH 用户 `hzq`，密码 `000000`），systemd 服务 `xinlv.service` 用 waitress 监听 **127.0.0.1:8000**，经该机上的 Cloudflare Tunnel 对外提供 HTTPS 访问（本地到服务器仍为 HTTP）。macOS 客户端构建机为局域网电脑 **192.168.5.3**（SSH 用户 `huazixian`，密码 `000000`）。Windows PC 只作开发机，不再运行生产服务（cloudflared 已卸载）。

**磁盘布局**：D 盘根目录只有 `D:\moodsite`（本项目总文件夹）和 `D:\server`（用户其他服务，勿动）。Windows 端 git 仓库根在 **`D:\moodsite\web`**；总文件夹下还有 `userinput0724`（历史版本源文件）、`moodsite_recovered`（恢复中间产物）、`tmp`、`moodsitelogsedge_profile` 和聊天记录导出文件。

## 2. 技术栈

- Python 3.11+ / Django 5.1.x（`Django>=5.1,<5.2`）
- 数据库：SQLite（`db.sqlite3`，单机小规模，非并发场景）
- 生产 WSGI 服务器：waitress（`waitress>=3.0`），非 gunicorn/uwsgi
- 静态文件：whitenoise（`CompressedStaticFilesStorage`），**DEBUG=False 时必须先跑 `collectstatic`，否则页面无样式**
- AI 对话：DeepSeek API（OpenAI 兼容协议），模型 `deepseek-v4-flash`
- 语音合成：`edge-tts`（微软免费在线 TTS，无需 key）；语音识别用浏览器原生 `SpeechRecognition`（前端 JS，非后端）
- 图片处理：Pillow（头像 `ImageField` 依赖）
- 环境变量：`python-dotenv`，配置文件为项目根 `.env`（不入库/不进 zip）
- 前端：无构建流程，原生 HTML + 内联 `<script>`，Django 模板渲染，无 SPA 框架
- 依赖清单：`requirements.txt`

## 3. 项目结构

```
moodsite/
├── manage.py
├── .env                      # 密钥/域名等，不进版本控制，需手动创建
├── requirements.txt
├── run_server.bat            # Windows 一键启动；已内置自动 migrate+collectstatic
├── db.sqlite3                # 数据库文件，不进 zip 交付
├── backup_db.py              # 数据库+media 一致性备份脚本（用 sqlite3 backup API）
├── moodsite/                 # Django 项目配置包
│   ├── settings.py           # 所有配置含安全加固项都在这一个文件
│   ├── urls.py                # 顶层 urls，实际业务路由在 core/urls.py
│   └── wsgi.py / asgi.py
├── core/                      # 唯一的业务 app
│   ├── models.py             # 全部模型 + MOODS/BADGES 常量
│   ├── urls.py                # 业务路由（唯一路由文件）
│   ├── views.py               # 首页/日历/心情/树洞/结果页/免责声明
│   ├── api.py                 # 客户端 REST API（/api/v1/，Bearer Token 认证）
│   ├── tests_api.py           # API 全流程测试（TestCase，deepseek 打 mock）
│   ├── feature_views.py       # 用户主页/徽章/投稿审核/复审/多语言切换
│   ├── admin_views.py         # 自建后台（非 Django admin），/manage/ 下的视图
│   ├── auth_views.py           # 注册（登录用 Django 自带 LoginView）
│   ├── deepseek.py             # DeepSeek 封装，SYSTEM_PROMPT 在此
│   ├── crisis.py               # 危机关键词硬拦截（is_crisis）
│   ├── tts.py                   # edge-tts 语音合成封装
│   ├── recommendations.py      # 按 mood 挑内容（歌曲/建议/小知识/视频）
│   ├── i18n.py                  # 中/英字符串表 STRINGS + i18n_context
│   ├── context_processors.py   # site_globals：SiteSettings 注入所有模板
│   ├── ratelimit.py             # 内存级简易限流（is_limited）
│   ├── limits.py                # 上传大小/类型校验（check_audio/check_image）
│   └── migrations/              # 按功能分批的迁移
├── templates/
│   ├── base.html                # 顶部导航+移动端底部 tabbar+页脚，所有页面继承它
│   ├── home.html                 # 首页：月/周/年日历+记录心情弹窗（前端JS切视图）
│   ├── confidant.html            # AI树洞聊天页
│   ├── result.html               # 记录心情后的推荐结果页
│   ├── contribute.html           # 用户投稿页
│   ├── profile.html / badges.html
│   ├── game.html                 # 放松小游戏（仿合成大西瓜），纯前端 Canvas
│   ├── disclaimer.html           # 免责声明（可被后台 SiteSettings 覆盖）
│   ├── registration/login.html, register.html
│   └── manage/                   # 后台全部模板，manage/base.html 是后台专属导航
├── static/css/style.css          # 唯一样式文件，无预处理器，纯手写CSS+CSS变量
├── static/js/                    # 目前基本为空，JS 都内联在各模板 <script> 里
└── media/                        # 用户上传：music/ avatars/ user_music/
```

## 4. 核心业务逻辑

**情绪记录数据流**：`home.html` 弹窗 POST `core.views.save_mood` → 每次都是 `MoodEntry.objects.create()`（**从不 update_or_create，一天可存多条，不覆盖**）→ `at` 字段记录精确时刻用于排序。月历取某天代表情绪的算法在 `core.views._representative_mood()`：**同一天多条时，若有心情重复出现则取被重复最多的那个，否则取最新一条**——这是产品明确要求的规则，改动前先确认需求没变。

**周/年视图**：前端 JS 通过 `GET /calendar-data/?scope=week|year|month` 拉数据，不刷新页面切换（`home.html` 内的 IIFE）。周视图纵轴是时间（0点在顶部），情绪按 `minutes = hour*60+minute` 定位纵向位置。

**访客 vs 登录用户**：未登录用户的心情记录**只存浏览器 localStorage，不落库**（对应 `home.html` 里的 `load()/save()` JS 函数），登录后可选择"导入本地记录"（`POST /api/import-local/`）。写后端逻辑时注意不要假设所有心情记录都有关联用户。

**AI 树洞安全链路**：`POST /confidant/send/` → 先过 `core.crisis.is_crisis()` 关键词硬拦截（命中直接返回求助资源，不把消息发给 AI）→ 未命中才调 `core.deepseek.chat()`。**这个顺序不能变**。

**用户投稿审核链路**：`POST /contribute/` 创建 `UserContribution(status=pending_ai)` → `feature_views.ai_review()` 调 DeepSeek 做 pass/fail/uncertain 三态判断（无 key 时自动 uncertain）→ pass 直接 `_publish_contribution()` 并入正式表（Song/Activity/PsychologyTip/BilibiliVideo）；fail/uncertain 转 `pending_admin` 等人工处理。**kind=tip（心理学小知识）不选情绪**（产品逻辑：小知识默认正面情绪展示），表单改显示"出处"字段；其余三种类型（activity/music/video）保留情绪选择，前端按 kind 动态切换字段见 `contribute.html` 内联 JS。

**多语言**：`core.i18n.STRINGS` 是唯一的双语源（`zh`/`en` 两个 dict，key 相同）。模板里一律用 `{{ T.some_key }}`，不写死中/英文。新增界面文案必须同时在两个 dict 里加 key，遗漏英文会导致英文模式下该处仍显示中文。语言存在 session +（登录用户）`UserProfile.language`。

**客户端 API（/api/v1/，2026-07-26 上线）**：为安卓/桌面原生客户端（离线可用、联网同步）提供 REST 接口，实现在 `core/api.py`。设计要点：
- **认证**：`POST /api/v1/login/` 用账号密码换 `ApiToken`（40 位 hex，长期有效，按设备区分），之后一律 `Authorization: Bearer <key>`。不用 session/cookie，所以全部 `csrf_exempt`。
- **同步模型**：心情记录是追加型数据。客户端离线创建时自己生成 `MoodEntry.uuid`，按 uuid upsert 去重；更新/删除按 `updated_at` **最新者赢**（last-write-wins，服务端只信客户端带来的时间戳做比较，自己存库时 updated_at=auto_now）；删除是**墓碑**（`deleted=True`，不真删，防同步复活）。网页端查询走 `AliveManager`（默认 `objects`，自动排除墓碑），同步走 `all_objects`——所以网页端既有代码零改动。
- **复用网页端逻辑**：`/api/v1/chat/` 的危机硬拦截（crisis→不发 AI）与 deepseek 调用顺序和 `confidant_send` 完全一致；`/api/v1/recommend/` 复用 `recommendations.build()`；`/api/v1/catalog/` 给客户端离线缓存推荐内容（含音频绝对 URL）。
- **端点清单**：ping（免认证探活）/ login / logout / sync/pull（`?since=` 增量，含墓碑）/ sync/push（批量 ≤500，逐条容错）/ catalog / recommend / chat / chat/history / chat/clear / profile。
- **测试**：`core/tests_api.py` 16 个用例（`python manage.py test core.tests_api`），独立测试库不碰生产数据，`deepseek.chat` 一律 mock。

## 5. 编码规范与约定

- **文件级 docstring 强约定**：每个 `.py` 文件顶部三引号说明该文件用途，新文件也要写。
- **命名**：模型/字段/函数英文小写下划线，用户可见文案中文（除非是 i18n key）。视图函数名与 URL name 一致（如 `save_mood` ↔ `name="save_mood"`）。
- **路由集中**：业务路由只写在 `core/urls.py` 一个文件，不按模块拆分；`moodsite/urls.py` 只 include 它 + admin。
- **视图按职责分文件**（非按 REST 资源）：`views.py`（心情+树洞）、`feature_views.py`（用户增值功能）、`admin_views.py`（后台）、`auth_views.py`（认证）。新增视图先判断职责归属，不要都堆进 `views.py`。
- **模板继承**：用户页面 extends `base.html`，后台页面 extends `manage/base.html`，两套导航不要混用。
- **前端无构建步骤**：不引入 npm/webpack/vite。JS 内联在模板 `<script>` 里，CSS 全部写进 `static/css/style.css` 一个文件（按 `/* ==== vN：功能名 ==== */` 分段追加，不拆分多个 css 文件）。
- **CSS 设计系统**：颜色/圆角/阴影走 `:root` 变量（`--bg` `--card` `--ink` `--accent` `--shadow` 等），不写死色值。视觉基调"温暖治愈"（米色+灰绿），不引入高饱和/冷色调风格。
- **注释语言**：代码注释一律中文（项目开发者是中文母语使用者，这是唯一约定）。
- **模型变更流程**：改 `models.py` 后本地跑 `python manage.py makemigrations core && python manage.py migrate` 验证再交付，不手写迁移文件。
- **AI 相关 prompt 改动要谨慎**：`deepseek.py` 的 `SYSTEM_PROMPT` 和 `feature_views.AI_REVIEW_PROMPT` 都是经过多轮调整的安全相关文案（禁止病理化诊断、禁止透露自伤方式细节等），修改前确认没有破坏这些安全约束的语义。
- **测试**：`core/tests_api.py` 有 API 的 16 个 TestCase 用例（2026-07-26 起），其余网页端逻辑仍无自动化测试，验证方式是用 `django.test.Client` 手写一次性脚本跑一遍再交付。写外部 API 调用（deepseek 等）的测试必须 mock，不能依赖外网。
- **Git 规范**：已用 Git 管理（main 分支为主线，历史快照在孤儿分支 `history` / `history-clients`，见第 6 节）。commit message 用中文写清改了哪个功能即可，不必套用 Conventional Commits。

## 6. 重要约束与踩坑记录

- **【最高纪律】`D:\backup\` 只进不出：只可追加，不可删除、移动、重命名其中任何内容**（2026-08-14 用户钦定的最高优先级约定）：Windows 计划任务「心履每日备份」每天 05:00 调用 `D:\moodsite\backup_linux.py`，通过 SSH（192.168.5.35 / hzq / 000000）从 Linux 生产机拉取 `.env` + 一致性备份 `db.sqlite3`，存入 `D:\backup\YYMMDD\`（如 `D:\backup\260814\`）。**严格只存文字数据，音频/图片（media/）一律不备份**（SQLite backup API 在远端生成一致性快照，避免 waitress 运行中直接拷文件）。幂等：当天已备份则跳过；失败留痕 `D:\backup\backup.log`（追加，不覆盖）。改动脚本前先读它顶部 docstring；任何"清理 D:\backup 腾空间"的想法都违反最高纪律，直接否决。
- **`DEBUG=False` 时忘记跑 `collectstatic` 会导致页面完全没样式**（真实故障）。`run_server.bat` 已自动兜底（启动前跑 `migrate` + `collectstatic`），别删这两行。
- **`X_FRAME_OPTIONS` 必须是 `SAMEORIGIN` 不能是 `DENY`**：客户端用 iframe/webview 加载本站页面，DENY 会导致客户端白屏（真实踩过的坑）。
- **`.env` 和 `db.sqlite3` 永远不进交付的 zip / 版本控制**，包含密钥和用户数据。
- **没有 HTTPS**：部署在 `http://`。浏览器 `SpeechRecognition`（语音输入）在网页端因此不可用（http 下 getUserMedia 被禁，非 bug），语音输出（edge-tts）不受影响。
- **`MoodEntry` 一天可多条，不能假设"一天只有一条"**（早期有 `unique_together(user,date)` 约束后来去掉了）。若见到 `update_or_create(user=,date=)` 保存心情的写法，那是过时代码，应为 `create()`。
- **限流是进程内存实现（`core/ratelimit.py`），非 Redis**：多进程部署时各进程计数不共享会失效。目前 waitress 单进程够用，换多进程部署需重新设计。
- **JS 变量重复声明会让整个 `<script>` 块静默失效**：曾发生 `confidant.html` 里 `const speakBtn` 声明两次导致 `SyntaxError`，发送/语音全部失效但页面仍正常渲染（报错在脚本执行阶段）。**改动内联 JS 后必须在浏览器 Console 确认无报错**。
- **后台新增页面时路由/视图/模板做完不代表用户能用到**：曾发生 `review_queue` 都写好但忘了在 `manage/base.html` 导航加链接。**新增后台页面必须检查"导航有入口"**。
- **`admin_views.py` 用到的所有 model 必须显式 import**：曾发生过用了 `UserContribution` 但顶部 import 没加，触发 `NameError`。
- **改完任何 `templates/*.html` 必须重启 waitress 才生效**（2026-07-24 实证）：项目没有显式配置 `TEMPLATES.OPTIONS.loaders`，Django 默认自动套 `cached.Loader`（与 DEBUG 无关，见 `django/template/engine.py`），模板编译后在进程内存里缓存，waitress 又没有 runserver 的自动重载，不重启就一直发旧页面。runserver 模式有 autoreload 监听模板目录所以开发时无感。
- **`.gitignore` 写目录排除模式时注意别误伤同名代码目录**：2026-07-24 发现 `moodsite*/` 本意是忽略历史版本文件夹，结果把真正的 `moodsite/` 配置包整个忽略了（settings.py 等从未被追踪）。写完后用 `git check-ignore -v <关键文件>` 验证。
- **Git Bash 里给 `git worktree add` 传路径要用 Windows 风格**：2026-07-25 实证，传 `/d/xxx` 会被错误解析成 `D:\d\xxx`（盘符下多套一层 d 目录），且后续 `cd` 找不到。传 `D:\\xxx` 才正确。
- **历史版本归档在两个孤儿分支**：`history`（网页端 21 个提交：2 个早期原型 html + 16 个 zip 快照 + 工具脚本/文档，提交日期=源文件 mtime）和 `history-clients`（客户端壳 3 个快照），源文件在 `D:\moodsite\userinput0724`。与 master 无共同祖先，仅作存档查阅用（`git log history` / `git show history:<文件>`），不要 merge 进 master。
- **API 的 `?since=` 参数必须 URL 编码**：ISO8601 时间串里的 `+08:00` 中 `+` 号不编码会被当成空格，服务端解析失败就退化成全量拉取（真实踩过，测试里因此挂过一次）。客户端发参数一律走编码后的 query string。
- **`updateIntensityColor`/`onIntensityChange` 等被多处调用的 JS 函数必须定义在 `base.html`**（2026-07-29 实证）：home.html 的 radio 按钮 `onchange` 引用了这两个函数，但 result.html 没有覆盖 `{% block script %}`，导致 ReferenceError。所有被多个页面引用的全局函数（如强度滑块相关）都放 `base.html` 的 `{% block script %}` 之后。
- **每次改动代码后必须更新生产环境 + 提交 git**（2026-07-29 定）：任何代码改动完成后，必须执行以下步骤才能标记完成：
  1. 若改了网页端代码（Django 模板/视图/静态文件等）：`collectstatic` → kill 旧 waitress → 启动新 waitress → curl 验证页面内容包含新特征
  2. 若改了客户端代码（安卓/Windows）：重新打包（`./gradlew assembleRelease` / `mvn package jpackage:jpackage`）→ 更新 `C:\Users\Administrator\Desktop\clients\` 下的对应交付文件
  3. 最后 `git add -A && git commit -m "..."` 提交到 master
  4. 以上步骤不可跳过，不可留到"下次一起做"。
- **给有存量的表加"唯一约束+callable默认值"的字段必须三步走**（迁移 0008 实证）：① AddField `null=True`（不带 unique/default）→ ② RunPython 逐条生成不同值 → ③ AlterField 加 `unique=True, default=callable`。直接一步加会让所有存量行拿到同一个默认值，migrate 时 `UNIQUE constraint failed`。这是对"不手写迁移文件"约定的合理例外——先 makemigrations 生成再手工拆成三步。
- **限流计数是进程内存全局的，写测试时每个用例前要 `ratelimit._hits.clear()`**，否则多个用例共享同一 IP/用户的计数会意外触发 429。
- **模板里用 `{% static %}` 必须自己在文件顶部 `{% load static %}`**：`{% extends %}` 不会继承父模板的 load（2026-07-27 实证：game.html 加水果贴图引用后整页 500，DEBUG=False 时日志无堆栈，用 `get_template('game.html').render({})` 在 shell 里复现才看到 TemplateSyntaxError）。
- **重启 waitress 必须确认旧进程全死透**：Windows 上多个 waitress 能同时 LISTEN 同一端口（SO_REUSEADDR），只杀一个 PID 会留下旧进程继续发旧模板，curl 验证看到的还是旧页面（2026-07-27 实证：两代 waitress 同挂 8000，新代码"没生效"其实是请求打到了旧进程）。重启后改完代码要 curl 页面内容里的新特征串确认，别只看 200。
- **macOS 构建固定在指定 Mac 上执行**（2026-08-14 用户明确约定）：每次构建 macOS DMG，必须连接局域网 macOS 构建机 **192.168.5.3**，使用 SSH 用户 `huazixian`、密码 `000000`，在该电脑上运行 `build.sh`；不要在 Windows 本机尝试构建，也不要反复询问构建位置或凭据。每次构建完成后，必须在该 Mac 的桌面保留一份最新 DMG，同时将 DMG 传回 Windows 交付目录和网站下载目录。
- **Linux venv 创建需要先装 `python3.12-venv`**（Ubuntu 24.04 默认缺 ensurepip）：`echo 000000 | sudo -S apt-get install -y python3.12-venv`，否则 `python3 -m venv` 直接报错。
- **公网域名**：xin-lv.com 已解析到 Cloudflare（经 Linux tunnel 出网）；**www.xin-lv.com 上游 DNS 无记录（NXDOMAIN）**，需要用户在 Cloudflare DNS 面板添加，机器侧无法修复。`.env` 的 ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS 已含 www 子域。
- **GitHub 单文件 >100MB 会被 pre-receive hook 拒绝**（>50MB 警告）：客户端安装包（DMG/APK/exe）是构建产物，不进 git（`.gitignore` 已加 `static/download/`），部署经 SFTP 同步。**客户端源码在 `D:\moodsite\clients\` 是独立 git 仓库**，与 web 仓库分开提交。
- **Cloudflare URL 规范化会删尾部斜杠，与 Django APPEND_SLASH 冲突 → 无限 301 循环**（2026-08-14 实证，浏览器报 ERR_TOO_MANY_REDIRECTS）：边缘把 `/login/` 改写成 `/login` 转发给源站，Django 对无斜杠返回 301 指向 `/login/`，浏览器再请求又被删斜杠……循环。**修复**：`moodsite/middleware.py` 的 `InternalAppendSlashMiddleware` 在 CommonMiddleware 之前把"补斜杠能匹配路由"的无斜杠请求内部改写 `path_info`，直接返回 200 不再 301。**不要删这个中间件**，也不要去改 Cloudflare 面板（该中间件让行为对边缘规范化免疫）。验证方式：`curl -s -o /dev/null -w '%{http_code}' https://xin-lv.com/login/` 应得 200（带斜杠和无斜杠都 200）。
- **Linux 生产库曾被误删/落错位置（2026-08-14 全站 500 事故，已恢复）**：两个根因要防复发——① `sync_web_linux.py` 的 `cleanup_remote` 曾把远程 `db.sqlite3` 当"该删的旧文件"删掉（find 不排除数据文件 + 循环里 `name == "db.sqlite3"` 直接 rm），已修：find 排除 `-not -name 'db.sqlite3' -not -name '.env'` 且循环内显式 `continue`；② 旧版 `migrate_data_to_linux.py` 的 `sync_media` 里 `run()` 漏传 `ssh` 参数（已修）。**事故判断方法**：Django 页面全 500 而日志报 `no such table: core_sitesettings` → 先 `ls -la /home/hzq/xinlv-web/db.sqlite3` 看是否 0 字节；若旁边有反斜杠文件名（`xinlv-web\db.sqlite3`，Windows 路径被当文件名创建）则是迁移路径 bug 落错位置，把该文件 cp 回正斜杠位置再 `migrate --noinput` 即可。**sync/migrate 脚本任何改动都必须先确认"绝不动远程数据文件"**。
- **生产库数据规模参考**：Linux 生产库 5 用户 / 85 条心情（2026-08-14 恢复后确认），与 Windows 测试库备份 `backups/db_20260813_232157.sqlite3`（290816 字节）同源。
- **生产机 `.env` 缺失导致登录 403 Forbidden**（2026-08-14 二度事故，这次是登录按钮）：症状 = 点击登录按钮出现 Django 403 页面（日志 `django.security.csrf Forbidden (Origin checking failed - https://xin-lv.com does not match any trusted origins.)`），GET 页面正常。根因：生产 `/home/hzq/xinlv-web/` 下**没有 .env 文件**（迁移时未传成功或后续丢失），`CSRF_TRUSTED_ORIGINS` 为空 → Django 5.1 对任何带 `Origin` 头的 POST 一律 403；连锁反应还有 DEBUG 静默变 True、SECRET_KEY 用 dev 默认、DeepSeek key 缺失。**诊断**：SSH `ls /home/hzq/xinlv-web/.env` 不存在 + `tail logs/site.log` 看 WARNING 行（注意 `migrate_data_to_linux.py` 和 `sync_web_linux.py` 的 cleanup 都正确排除了 .env，别误判为脚本删除）。**修复**：重跑 `python migrate_data_to_linux.py` 或手动 SFTP 上传 .env（与 Windows 端 md5 一致），`echo 000000 | sudo -S systemctl restart xinlv.service`。**验证**：curl 带 `Origin: https://xin-lv.com` 头 POST /login/ 必须返回 200（不带 Origin 的 curl 测不出这个 403，浏览器必带 Origin）——**以后部署后必须做这一步**；同时确认 `md5sum` 两端 .env 一致、DEBUG 特征（django-debug-pages）不存在。

## 7. 常用命令

```bash
# 首次搭建
python -m venv venv
venv\Scripts\activate          # Windows；Linux/Mac 用 source venv/bin/activate
pip install -r requirements.txt

# 日常开发
python manage.py runserver              # 开发服务器（DEBUG=True 时用）
python manage.py makemigrations core    # 改完 models.py 后生成迁移
python manage.py migrate                # 应用迁移
python manage.py collectstatic --noinput  # DEBUG=False 前必须跑
python manage.py createsuperuser        # 创建后台管理员（is_staff=True）

# 生产运行（Windows 开发机已不再跑生产，以下为 Linux 生产机 192.168.5.35 的命令）
ssh hzq@192.168.5.35                          # 密码 000000
cd /home/hzq/xinlv-web
venv/bin/python manage.py collectstatic --noinput   # 改完静态文件后
echo 000000 | sudo -S systemctl restart xinlv.service   # 重启生产服务（改代码后必做）
journalctl -u xinlv.service -n 50 --no-pager   # 看服务日志

# macOS DMG 构建（固定在局域网 Mac 192.168.5.3 上执行，不要改在 Windows 本机构建）
ssh huazixian@192.168.5.3                       # 密码 000000
cd /path/to/macos
./build.sh

# Windows 开发机一键双端同步（在 D:\moodsite 下跑）
python sync_web_linux.py                       # 同步网页端代码到 Linux 生产机
python migrate_data_to_linux.py                # 同步 .env / db.sqlite3 / media/ 数据到 Linux

# 数据库备份
python backup_db.py                     # 一次性备份到 backups/，保留最近30份
python backup_linux.py                  # 手动执行每日备份（计划任务 05:00 自动跑；产物 D:\backup\YYMMDD）

# 没有配置 lint/format 工具（无 black/flake8/eslint 配置文件），
# 保持现有代码风格手写即可，不要引入新的格式化工具链改动全量文件。
```

## 8. 外部依赖与服务

- **DeepSeek API**：`.env` 中 `DEEPSEEK_API_KEY`（树洞+投稿AI审核必需）、`DEEPSEEK_BASE_URL`（默认 `https://api.deepseek.com`）、`DEEPSEEK_MODEL`（默认 `deepseek-v4-flash`）。**未配置 key 时优雅降级**而非崩溃：树洞返回提示文案，投稿审核自动转人工。改动 `deepseek.py`/`ai_review()` 时不要破坏这个降级行为。
- **edge-tts**：无需 key，但需能访问微软服务器（外网）。合成失败时前端自动回退浏览器自带朗读（`confidant.html` 内 `browserSpeak`）。
- **内网穿透**：域名/端口写在 `.env` 的 `DJANGO_ALLOWED_HOSTS` 和 `CSRF_TRUSTED_ORIGINS`；公网由 **Linux 生产机上的 Cloudflare Tunnel**（cloudflared）提供，Windows 上的 cloudflared 已卸载，站点只需监听 127.0.0.1:8000。穿透工具配置不在本项目代码范围内。
- **无数据库服务/缓存/消息队列依赖**：SQLite 文件数据库，无 Redis/Celery。
- **本地/生产差异**：仅由 `.env` 的 `DJANGO_DEBUG` 一个开关控制，无 settings_dev/settings_prod 分文件方案。

## 9. 当前工作状态

**已完成**：情绪日历（月/周/年三视图）、一天多条记录、AI树洞（文字+语音+危机拦截）、免责声明（后台可编辑）、连胜徽章、用户主页+头像、用户投稿+AI审核+人工复审、中/英双语、后台管理、安全加固（限流/上传校验/安全响应头/日志/登录防爆破）、数据库备份脚本、Windows/安卓客户端壳、放松小游戏"情绪小西瓜"、**客户端 REST API v1**（2026-07-26：令牌登录/离线同步/目录/推荐/树洞/个人数据，16 个测试用例）、**生产环境迁移 Linux**（2026-08-13：代码/数据/服务已迁至 192.168.5.35，systemd 托管，公网经 Linux tunnel 正常；Windows cloudflared 已卸载）、**每日异地备份**（2026-08-14：Windows 计划任务 05:00 从 Linux 拉取 .env + db.sqlite3 到 `D:\backup\YYMMDD\`，最高纪律只进不出）。

**客户端交付物**：`C:\Users\Administrator\Desktop\clients\` 目录存放客户端可执行文件，供直接下载安装。
- `clients\安卓\心履-安卓-v1.0.2.apk` — 安卓 APK（release 签名包）
- `clients\Windows\心履-Windows-v1.0.0.exe` — Windows 安装包（jpackage 输出）
- 客户端源码仍在 `D:\moodsite\clients\`（git 仓库内），桌面目录只放打包好的交付文件。
- 客户端代码改动时，重新打包后必须把新文件**复制到桌面 clients 目录覆盖旧文件**，再提交 git。

**进行中（客户端计划，2026-07-26 定）**：做**原生本地客户端**（非 webview 壳），离线可用、联网与服务器同步，界面与网页端不同。技术选型：安卓端 Java 原生 + Room 本地库；桌面端 JavaFX 共享代码，jpackage 打 Windows exe / Mac dmg（Mac 也接受 HMCL 式 jar + 用户自装 Java）。MVP 范围：登录/记心情/日历/推荐/AI聊天（仅联网）/徽章；不做游戏、投稿、后台、i18n。注意站点是 http 无 HTTPS，安卓需 `usesCleartextTraffic="true"`。顺序：安卓 → 桌面。

**待办**：`www.xin-lv.com` 上游 DNS 记录缺失（NXDOMAIN，需用户在 Cloudflare DNS 面板添加；`.env` 已配置好）；树洞页部分 JS 动态文案（语音状态提示、危机弹窗）未接入 i18n，英文模式下仍显示中文；SQLite 若用户量明显增长需评估迁移 PostgreSQL。HTTPS 已由 Cloudflare Tunnel 对外提供（源站仍 127.0.0.1:8000 HTTP，`ENABLE_HTTPS`/`SECURE_COOKIES` 开关按需用）。

## 10. 关键文件索引

- 理解**数据模型全貌**：`core/models.py`（一个文件包含所有模型 + MOODS/BADGES 常量）
- 理解**客户端 API 全貌**：`core/api.py`（认证/同步/目录/树洞）+ 本文件第 4 节"客户端 API"段；接口行为以 `core/tests_api.py` 的用例为准
- 理解**心情记录与日历渲染**：`core/views.py` 的 `home()` / `save_mood()` / `_representative_mood()` / `calendar_data()`，配合 `templates/home.html`
- 理解**AI树洞安全机制**：`core/crisis.py` + `core/deepseek.py`
- 理解**投稿审核全流程**：`core/feature_views.py` 的 `contribute()` / `ai_review()` / `_publish_contribution()` / `review_queue()`
- 理解**权限与后台**：`core/admin_views.py`（`staff_required` 装饰器 + 各管理视图）
- 理解**多语言机制**：`core/i18n.py` + `core/context_processors.py`
- 理解**生产安全配置**：`moodsite/settings.py` 文件末尾"安全加固"注释块
- 理解**整站视觉设计**：`static/css/style.css` 顶部 `:root` 变量定义
