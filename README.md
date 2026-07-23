# 心情树洞 · Mood Calendar + AI 电子树洞

记录每天心情的日历网站：选心情后推送舒缓方式（本地歌曲 / 行为建议 / 即时练习），正面心情则推送心理学小知识；内置 DeepSeek 驱动的"AI 电子树洞"陪聊。
附带一个**给非技术站长用的极简管理后台**（`/manage/`），能在浏览器里直接上传音乐、加内容。

- 访客端：`/`（日历）、`/confidant/`（AI 树洞）—— 无需注册
- 管理端：`/manage/` —— 站长登录后管理内容

---

## 一、部署到 Windows PC（站长 / 你来做）

> 服务器是一台 Windows PC，通过你已有的内网穿透端口对外。下面每一步在 PC 上操作。

### 1. 装 Python
去 https://www.python.org/downloads/ 装 **Python 3.10 以上**。
安装时**勾选 "Add Python to PATH"**。

### 2. 把项目放到 PC 上
解压本项目，记住路径（有 `manage.py` 的那个文件夹）。在该文件夹地址栏输入 `cmd` 回车，打开命令行。

### 3. 装依赖（建虚拟环境）
```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
（以后每次开命令行操作前，都先 `venv\Scripts\activate`）

### 4. 写配置文件 `.env`
```bat
copy .env.example .env
notepad .env
```
按下面填（**对外正式服务时这几项很关键**）：
```
DJANGO_SECRET_KEY=换成一长串随机字符
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=你的穿透域名或IP        例如 mood.example.com
CSRF_TRUSTED_ORIGINS=https://你的穿透域名     例如 https://mood.example.com
DEEPSEEK_API_KEY=你的DeepSeek密钥
```
> `SECRET_KEY` 生成方法：命令行运行 `python -c "import secrets;print(secrets.token_urlsafe(50))"`，把输出贴进去。
> `CSRF_TRUSTED_ORIGINS` 不填的话，访客通过公网域名记录心情 / 发消息会报 **CSRF 403**。

### 5. 初始化
```bat
python manage.py migrate
python manage.py seed_data
python manage.py collectstatic --noinput
```

### 6. 建两个账号
```bat
:: 给你自己（站长 / 超级管理员）
python manage.py createsuperuser

:: 给"不懂电脑的朋友"——也用同一条命令，再建一个就行
python manage.py createsuperuser
```
把第二个账号的用户名密码给朋友，他用它登录 `/manage/`。

### 7. 启动（正式）
直接**双击 `run_server.bat`**，或命令行：
```bat
python -m waitress --listen=0.0.0.0:8000 moodsite.wsgi:application
```
本机访问 http://127.0.0.1:8000 能打开就成功了。

### 8. 接内网穿透
把你的穿透工具（frp / cpolar / cloudflared / 花生壳等）的**目标指向本机 `127.0.0.1:8000`**，
公网域名/端口映射过去即可。确保第 4 步的 `ALLOWED_HOSTS` 和 `CSRF_TRUSTED_ORIGINS` 写的是这个公网域名。

### 9.（可选）让它开机自动跑、关窗口也不停
最省事：把 `run_server.bat` 加入 **任务计划程序**（触发器选"登录时"）。
更稳的做法：用 [nssm](https://nssm.cc/) 把 waitress 注册成 Windows 服务。

### 10. 备份
重要数据就两样：根目录的 **`db.sqlite3`**（所有记录）和 **`media/` 文件夹**（音乐）。
定期复制这两个到别处即可。

> 静态文件已交给内置的 whitenoise，媒体音乐由 Django 直接提供，**都不用额外配反向代理**，适合这种小站。

---

## 二、给朋友用的管理后台 `/manage/`

朋友打开 `你的网址/manage/`，用你给的账号登录，就能看到：

- **🏠 概览**：有多少音乐 / 小知识 / 心情记录 / 树洞倾诉次数
- **🎵 音乐**：点"选择音频文件"直接上传（mp3/m4a/flac/ogg/wav），填歌名歌手、勾选适合的心情；下面能改心情或删除
- **🌱 心理学小知识**：填标题+内容就能加，访客正面心情时随机展示
- **🤍 舒缓建议**：加温柔的小事建议，访客负面心情时展示

改完**不用重启**，访客刷新即可看到。朋友完全不用碰命令行，也不用进 Django 自带的 `/admin/`。

> 站长自己若想做更细的操作（看心情记录、批量管理），可以用超级管理员账号登录 `/admin/`。

---

## 三、AI 树洞配置（含语音）

**文字对话（DeepSeek）**
- 去 https://platform.deepseek.com 申请 API Key，填进 `.env` 的 `DEEPSEEK_API_KEY`。
- 默认模型 `deepseek-v4-flash`（便宜快，适合聊天）。人设和安全规则在 `core/deepseek.py`，可改语气。

**语音输出（朗读回复）= edge-tts，完全免费，不用申请任何账号/key/实名/付款**
- 已写在 `requirements.txt` 里，`pip install -r requirements.txt` 就装好了，**开箱即用，不用配置**。
- 它白嫖微软在线语音，需要服务器能联网（你那台 PC 平时能上网就行）。
- 想换音色或语速，在 `.env` 里加（不加就用默认的温柔女声晓晓）：
  ```
  TTS_VOICE=zh-CN-XiaoxiaoNeural   # 音色
  TTS_RATE=+0%                     # 语速，-10% 慢一点 / +10% 快一点
  ```
  常用中文音色：`zh-CN-XiaoxiaoNeural`(晓晓·温柔女)、`zh-CN-XiaoyiNeural`(晓伊·活泼女)、
  `zh-CN-YunxiNeural`(云希·年轻男)、`zh-CN-YunyangNeural`(云扬·沉稳男)。
  想看全部：命令行运行 `edge-tts --list-voices`（Windows 可加 `| findstr zh-CN`）。
- 用户在树洞页点「🔊 朗读回复：开」即可。若服务器连不上微软，会自动退回浏览器自带声音，不会报错。

**语音输入（麦克风）= 浏览器自带识别，自适应**
- 在 **https 或 本机(localhost/127.0.0.1)** 下可用；**http 公网域名下浏览器会禁用麦克风**，按钮会提示原因（这是浏览器的安全限制，不是 bug）。
- 想让朋友在公网也能用语音输入，需要把内网穿透换成 **https**（如 cloudflared 自带 https）。换成 https 后无需改任何代码，浏览器识别即可用。

**危机安全机制（重要，已内置）**
- `core/crisis.py` 在消息发给 AI **之前**做风险检测，命中（自伤/轻生等表达）就**强制停止 AI 咨询**，弹出窗口显示心理援助热线 + 110 + 120，并暂停输入。
- 这是关键词兜底，会漏判也会误判，**它是你这个真人树洞背后的备份，不是独立安全系统**。可在 `core/crisis.py` 增删词条。
- 系统提示词已禁止 AI 做任何心理诊断或贴病症标签（避免病理化、误导）。
- ⚠️ 页脚和危机弹窗里的心理援助热线（默认 12356）**请你上线前核实当地最新公布的号码**，可在管理后台「关于我们 / 联系方式」里改。

---

## 四、目录结构
```
moodsite/
├── manage.py
├── .env.example / requirements.txt / run_server.bat
├── moodsite/settings.py · urls.py
├── core/
│   ├── models.py            心情/歌曲/行为/小知识/聊天 数据模型
│   ├── views.py             访客端：日历、记录、推荐、树洞
│   ├── admin_views.py       /manage/ 简易管理后台（朋友用）
│   ├── recommendations.py   心情→推荐 逻辑
│   ├── deepseek.py          DeepSeek 客户端 + 树洞人设
│   └── management/commands/ scan_music.py（命令行批量导音乐）· seed_data.py
├── templates/               访客端 + manage/ 管理端 页面
├── static/css/style.css
└── media/music/             上传的音乐落在这里
```

## 五、隐私
访客用浏览器 session 区分，**不需要注册**；心情和聊天记录存在本地 SQLite。
日后若要"换设备同步"，再加访客登录即可。

---

## 七、v2 新增功能 & 从旧版升级

新增内容：
- **用户账号**：访客可注册/登录(只要账号+密码，无验证码/邮箱)。密码用哈希存储。
  - **未登录**：心情记录存在「这台设备的浏览器」(localStorage)。
  - **登录后**：心情记录存到服务器账号，**换设备也能看到**。首次登录若本机有本地记录，会提示一键导入到账号。
- **「关于我们」页**：和心情日历、AI 树洞并列。内容在管理后台用 **Markdown 编辑器**(带实时预览)编辑。
- **联系方式**：显示在每页页脚和关于页，可在管理后台修改。
- **用户管理**(管理后台)：查看每个用户的注册/登录时间、心情记录数、树洞次数；可**封禁/解封**、**授予/取消管理员**。
- **权限**：管理后台(/manage/)只有管理员(is_staff)能进；管理员登录后可在「管理端 ↔ 网页端」间自由切换(导航栏有入口)。
- 登录入口统一为 **/login/**(旧的 /manage/login/ 已移除)。

**如果你已经部署过旧版，升级只需 3 步**(在项目目录、已激活 venv)：
```bat
pip install -r requirements.txt      :: 新增了 markdown 依赖
python manage.py migrate             :: 数据库结构有变动（加了用户字段、网站设置表）
python manage.py collectstatic --noinput
```
> 说明：旧版里用浏览器 session 存的访客心情记录不会自动转到用户账号(那是匿名数据)。正式上线前的测试数据可以忽略。

**第一个管理员**仍然用 `python manage.py createsuperuser` 创建。之后想再加管理员，直接在「用户管理」里把某个注册用户「设为管理员」即可。
