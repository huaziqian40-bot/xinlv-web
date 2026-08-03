"""极简双语文案（中/英）。前端界面文案走这里；用户生成内容不翻译。"""

STRINGS = {
    "zh": {
        # 导航 / 账号
        "nav_calendar": "心情日历", "nav_confidant": "AI 树洞", "nav_about": "关于我们",
        "nav_contribute": "我要分享", "nav_game": "小游戏", "login": "登录", "register": "注册", "logout": "退出",
        "my_home": "我的主页", "manage": "管理后台", "hello": "你好，",
        # 页脚
        "contact_us": "联系我们", "email": "邮箱", "phone": "电话", "wechat": "微信",
        "foot_slogan": "记录情绪 · 倾听自己", "foot_disclaimer": "这里的 AI 与内容仅供陪伴和参考，不能替代专业心理帮助。",
        "crisis_note_1": "如果你正经历强烈的痛苦，请联系信任的人，或拨打全国心理援助热线",
        "crisis_note_2": "（请以当地最新公布的号码为准）。你并不孤单。",
        "disclaimer_link": "免责声明",
        # 日历
        "view_month": "月", "view_week": "周", "view_year": "年",
        "hero_title": "今天，心情怎么样？",
        "hero_sub": "点一个日子，记录此刻的感受。我会陪你一起，看看能做点什么。",
        "recent_moods": "最近的心情", "record_mood": "记录心情",
        "save_and_see": "保存并看看建议", "cancel": "取消",
        "note_placeholder": "想写点什么吗？（可留空）",
        "week_needs_login": "周/年视图需要登录后查看（访客数据存在本机，仅支持月视图）。",
        "add_more": "再记一条 ↓",
        # 结果页
        "you_feel": "你感到", "psych_tip": "今天的心理学小知识", "try_now": "此刻可以试试",
        "gentle_things": "一些温柔的小事", "listen_awhile": "听一会儿这些",
        "recommend_video": "给你推一个视频", "watch_on_bili": "去 B 站观看",
        "talk_to_someone": "想找人说说话吗？", "go_confidant": "去和 AI 树洞聊聊 →",
        "back_calendar": "‹ 回到日历",
        # 树洞
        "confidant_title": "AI 电子树洞", "confidant_sub": "把心里的话说出来吧。这里没有评判，我会一直听着。",
        "confidant_hello": "嘿，我在呢。今天发生了什么，想说说吗？",
        "send": "发送", "read_reply": "朗读回复", "on": "开", "off": "关",
        "clear_chat": "清空对话", "input_placeholder": "说点什么……（Enter 发送，Shift+Enter 换行）",
        # 主页
        "streak": "连续记录", "days": "天", "badges": "徽章", "total_records": "累计记录",
        "edit_profile": "编辑资料", "bio": "简介", "avatar": "头像", "save": "保存",
        "mood_footprint": "情绪足迹", "no_records": "还没有情绪记录。",
        # 上传
        "contribute_title": "分享给大家",
        "contribute_sub": "你的心理小知识、舒缓建议、音乐或视频，经审核后会加入网站。",
        "kind": "类型", "title": "标题", "optional": "（可选）", "content": "内容",
        "video_link": "视频链接", "audio_file": "音频文件", "apply_mood": "适用心情",
        "submit": "提交", "my_submissions": "我的投稿",
        "review_note": "提交后会先由 AI 审核内容是否健康、与所选情绪相符；通过即发布，不通过转管理员复审。",
        "no_submissions": "还没有投稿。",
        # 认证
        "login_title": "登录", "register_title": "注册",
        "login_sub": "登录后，你的心情记录会保存在账号里，换设备也能看到。",
        "register_sub": "只需要设置一个账号和密码，没有验证码、不用邮箱。",
        "username": "账号", "password": "密码", "password_again": "再输一次密码",
        "no_account": "还没有账号？", "go_register": "去注册",
        "have_account": "已经有账号了？", "go_login": "去登录",
        "agree_pre": "我已阅读并同意", "register_and_login": "注册并登录",
        # 徽章页
        "badge_page_title": "连胜徽章", "badge_page_sub": "坚持记录心情，解锁这些徽章，它们会显示在你的名字旁。",
        "obtained": "已获得", "still_need": "还差", "keep_going": "继续加油！",
        "current_streak_pre": "你当前连续记录", "current_streak_post": "天，继续加油！",
        "lang_name": "中文",
        # 下载页面
        "download": "下载客户端", "download_title": "下载心履",
        "download_sub": "随时随地记录心情，与 AI 树洞倾诉。",
        "download_android": "安卓版", "download_windows": "Windows 版",
        "download_macos": "macOS 版", "download_linux": "Linux 版",
        "download_developing": "正在开发中", "download_other": "其他平台敬请期待",
        "download_old_versions": "历史版本", "download_current": "当前版本",
        # 项目源码
        "github_source": "项目源码",
        "github_visit": "访问 GitHub 下载源代码",
        "github_desc": "心履的所有代码都在 GitHub 上开源，欢迎访问。",
        "github_web": "网页端",
        "github_android": "安卓客户端",
        "github_windows": "Windows 客户端",
        "github_macos": "macOS 客户端",
        "github_linux": "Linux 客户端",
        # 情绪强度
        "intensity": "强度", "intensity_slight": "略微", "intensity_some": "有点",
        "intensity_quite": "相当", "intensity_very": "十分",
    },
    "en": {
        "nav_calendar": "Calendar", "nav_confidant": "AI Tree Hole", "nav_about": "About",
        "nav_contribute": "Share", "nav_game": "Game", "login": "Log in", "register": "Sign up", "logout": "Log out",
        "my_home": "My Page", "manage": "Admin", "hello": "Hi, ",
        "contact_us": "Contact us", "email": "Email", "phone": "Phone", "wechat": "WeChat",
        "foot_slogan": "Track feelings · Listen to yourself",
        "foot_disclaimer": "The AI and content here are for companionship and reference only, and cannot replace professional mental-health help.",
        "crisis_note_1": "If you are in severe distress, please reach out to someone you trust, or call the national mental-health helpline",
        "crisis_note_2": "(please verify the current local number). You are not alone.",
        "disclaimer_link": "Disclaimer",
        "view_month": "M", "view_week": "W", "view_year": "Y",
        "hero_title": "How are you feeling today?",
        "hero_sub": "Pick a day and note how you feel. I'll help you find something that helps.",
        "recent_moods": "Recent moods", "record_mood": "Record mood",
        "save_and_see": "Save & see suggestions", "cancel": "Cancel",
        "note_placeholder": "Want to write something? (optional)",
        "week_needs_login": "Week/Year views require logging in (guest data stays on this device, month view only).",
        "add_more": "Add another ↓",
        "you_feel": "you feel", "psych_tip": "Today's psychology tip", "try_now": "Try this right now",
        "gentle_things": "A few gentle things", "listen_awhile": "Listen for a while",
        "recommend_video": "A video for you", "watch_on_bili": "Watch on Bilibili",
        "talk_to_someone": "Want to talk to someone?", "go_confidant": "Chat with the AI Tree Hole →",
        "back_calendar": "‹ Back to calendar",
        "confidant_title": "AI Tree Hole", "confidant_sub": "Say what's on your mind. No judgment here — I'm listening.",
        "confidant_hello": "Hey, I'm here. What happened today? Want to talk about it?",
        "send": "Send", "read_reply": "Read aloud", "on": "On", "off": "Off",
        "clear_chat": "Clear chat", "input_placeholder": "Say something… (Enter to send, Shift+Enter for a new line)",
        "streak": "Streak", "days": "days", "badges": "Badges", "total_records": "Total records",
        "edit_profile": "Edit profile", "bio": "Bio", "avatar": "Avatar", "save": "Save",
        "mood_footprint": "Mood history", "no_records": "No mood records yet.",
        "contribute_title": "Share with others",
        "contribute_sub": "Your tips, activities, music or videos will join the site after review.",
        "kind": "Type", "title": "Title", "optional": "(optional)", "content": "Content",
        "video_link": "Video link", "audio_file": "Audio file", "apply_mood": "For which moods",
        "submit": "Submit", "my_submissions": "My submissions",
        "review_note": "After you submit, AI checks whether the content is healthy and matches the chosen mood; approved items publish immediately, otherwise they go to admin review.",
        "no_submissions": "No submissions yet.",
        "login_title": "Log in", "register_title": "Sign up",
        "login_sub": "Once logged in, your mood records are saved to your account and sync across devices.",
        "register_sub": "Just set a username and password — no captcha, no email needed.",
        "username": "Username", "password": "Password", "password_again": "Repeat password",
        "no_account": "No account yet?", "go_register": "Sign up",
        "have_account": "Already have an account?", "go_login": "Log in",
        "agree_pre": "I have read and agree to the", "register_and_login": "Sign up & log in",
        "badge_page_title": "Streak Badges", "badge_page_sub": "Keep logging your moods to unlock these badges shown next to your name.",
        "obtained": "Obtained", "still_need": "need", "keep_going": "keep going!",
        "current_streak_pre": "Your current streak is", "current_streak_post": "days. Keep going!",
        "lang_name": "English",
        # 下载页面
        "download": "Download App", "download_title": "Download XinLv",
        "download_sub": "Record your moods anytime, anywhere. Chat with the AI Tree Hole.",
        "download_android": "Android", "download_windows": "Windows",
        "download_macos": "macOS", "download_linux": "Linux",
        "download_developing": "Under development", "download_other": "More platforms coming soon",
        "download_old_versions": "Previous versions", "download_current": "Current version",
        # 项目源码
        "github_source": "Source Code",
        "github_visit": "Get source code on GitHub",
        "github_desc": "All Xinlv source code is open-source on GitHub.",
        "github_web": "Web App",
        "github_android": "Android",
        "github_windows": "Windows",
        "github_macos": "macOS",
        "github_linux": "Linux",
        # 情绪强度
        "intensity": "Intensity", "intensity_slight": "Slightly", "intensity_some": "Somewhat",
        "intensity_quite": "Quite", "intensity_very": "Very",
    },
}


def get_lang(request):
    if request.user.is_authenticated:
        try:
            l = request.user.profile.language
            if l in STRINGS:
                return l
        except Exception:
            pass
    return request.session.get("lang", "zh")


def i18n_context(request):
    lang = get_lang(request)
    return {"LANG": lang, "T": STRINGS[lang]}
