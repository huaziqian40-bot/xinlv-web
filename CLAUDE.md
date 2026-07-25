# CLAUDE.md — 心情树洞 项目交接文档

> 本文档给 AI（Claude Code）读，不是给人看的 README。只写事实和约定，不写部署流程。
> 每次修复一个坑或定下一条新约定，把它补进第 6 节，不要让这份文档过时。

## 1. 项目概述

"心情树洞"是 Django 全栈的青少年心理陪伴 Web 应用：记录每日情绪（一天可多条）、
按情绪推荐音乐/建议/小知识/视频、与 AI 树洞（DeepSeek）文字+语音聊天（内置关键词危
机硬拦截）、连胜徽章、用户主页、用户投稿+AI审核、后台管理、中英双语、放松小游戏。
部署在开发者 Windows PC 上，经内网穿透对外提供 http 访问（无 HTTPS）。

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
- **没有自动化测试**：`core/tests.py` 为空。当前验证方式是用 `django.test.Client` 手写一次性脚本跑一遍再交付。要引入正式测试建议 pytest-django，先征求确认。
- **Git 规范**：已用 Git 管理（master 分支为主线，历史快照在孤儿分支 `history` / `history-clients`，见第 6 节）。commit message 用中文写清改了哪个功能即可，不必套用 Conventional Commits。

## 6. 重要约束与踩坑记录

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
- **历史版本归档在两个孤儿分支**：`history`（网页端 21 个提交：2 个早期原型 html + 16 个 zip 快照 + 工具脚本/文档，提交日期=源文件 mtime）和 `history-clients`（客户端壳 3 个快照），源文件在 `D:\userinput0724`。与 master 无共同祖先，仅作存档查阅用（`git log history` / `git show history:<文件>`），不要 merge 进 master。

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

# 生产运行（Windows）
run_server.bat                          # 已内置自动 migrate+collectstatic

# 数据库备份
python backup_db.py                     # 一次性备份到 backups/，保留最近30份

# 没有配置 lint/format 工具（无 black/flake8/eslint 配置文件），
# 保持现有代码风格手写即可，不要引入新的格式化工具链改动全量文件。
```

## 8. 外部依赖与服务

- **DeepSeek API**：`.env` 中 `DEEPSEEK_API_KEY`（树洞+投稿AI审核必需）、`DEEPSEEK_BASE_URL`（默认 `https://api.deepseek.com`）、`DEEPSEEK_MODEL`（默认 `deepseek-v4-flash`）。**未配置 key 时优雅降级**而非崩溃：树洞返回提示文案，投稿审核自动转人工。改动 `deepseek.py`/`ai_review()` 时不要破坏这个降级行为。
- **edge-tts**：无需 key，但需能访问微软服务器（外网）。合成失败时前端自动回退浏览器自带朗读（`confidant.html` 内 `browserSpeak`）。
- **内网穿透**：域名/端口写在 `.env` 的 `DJANGO_ALLOWED_HOSTS` 和 `CSRF_TRUSTED_ORIGINS`，穿透工具（frp等）不在本项目代码范围内。
- **无数据库服务/缓存/消息队列依赖**：SQLite 文件数据库，无 Redis/Celery。
- **本地/生产差异**：仅由 `.env` 的 `DJANGO_DEBUG` 一个开关控制，无 settings_dev/settings_prod 分文件方案。

## 9. 当前工作状态

**已完成**：情绪日历（月/周/年三视图）、一天多条记录、AI树洞（文字+语音+危机拦截）、免责声明（后台可编辑）、连胜徽章、用户主页+头像、用户投稿+AI审核+人工复审、中/英双语、后台管理、安全加固（限流/上传校验/安全响应头/日志/登录防爆破）、数据库备份脚本、Windows/安卓客户端壳、放松小游戏"情绪小西瓜"。

**待办**：HTTPS 未配置（`ENABLE_HTTPS`/`SECURE_COOKIES` 开关已预留）；无自动化测试；树洞页部分 JS 动态文案（语音状态提示、危机弹窗）未接入 i18n，英文模式下仍显示中文；nssm 自启只有手册未验证已配置；SQLite 若用户量明显增长需评估迁移 PostgreSQL。

## 10. 关键文件索引

- 理解**数据模型全貌**：`core/models.py`（一个文件包含所有模型 + MOODS/BADGES 常量）
- 理解**心情记录与日历渲染**：`core/views.py` 的 `home()` / `save_mood()` / `_representative_mood()` / `calendar_data()`，配合 `templates/home.html`
- 理解**AI树洞安全机制**：`core/crisis.py` + `core/deepseek.py`
- 理解**投稿审核全流程**：`core/feature_views.py` 的 `contribute()` / `ai_review()` / `_publish_contribution()` / `review_queue()`
- 理解**权限与后台**：`core/admin_views.py`（`staff_required` 装饰器 + 各管理视图）
- 理解**多语言机制**：`core/i18n.py` + `core/context_processors.py`
- 理解**生产安全配置**：`moodsite/settings.py` 文件末尾"安全加固"注释块
- 理解**整站视觉设计**：`static/css/style.css` 顶部 `:root` 变量定义
