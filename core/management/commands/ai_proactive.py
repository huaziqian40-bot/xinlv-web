"""AI 主动消息发送命令。

由 cron 每 30 分钟执行一次：检查有哪些用户的哪些时段已到但未执行，
按需生成主动消息或每周小结。

设计要点：
- 每天首次运行为每个活跃用户生成 2-4 个随机时段（8:00-22:00）
- 每个时段只执行一次，执行后标记 executed=True
- 每周日 22:00 生成 800-1200 字小结
- 减少 API 调用：只在有未执行时段时才调用 DeepSeek
"""
import datetime as dt
import random

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from core.models import ProactiveSchedule, ChatMessage, MoodEntry, MOOD_MAP
from core import deepseek

User = get_user_model()

# 主动消息的 prompt
PROACTIVE_PROMPT = """你是心履树洞，一个温柔耐心的电子树洞。现在你要主动给用户发一条消息，开启对话。

要求：
1. 根据用户最近的心情记录和之前的对话内容，用自然、温暖的口吻问候
2. 2-4 句话，简短自然，不要长篇大论
3. 不要重复用户说过的话，不要做心理分析
4. 如果不知道说什么，就简单问候一下
5. 不要用"看起来""似乎"这类猜测性语言，直接表达关心
6. 不要主动提及任何具体情绪标签，除非用户自己说过

直接输出你要说的话，不要加引号、不要加"树洞说："前缀。"""

# 每周小结的 prompt
WEEKLY_ESSAY_PROMPT = """你是心履树洞，一个温柔耐心的电子树洞。现在要为用户写一篇本周小结小作文，回顾用户这一周的情绪状态。

要求：
1. 写 800-1200 字的中文小作文，语言温暖、自然、有文学感
2. 回顾用户这一周的情绪变化，用诗意的方式描述
3. 不要做心理诊断，不要说"你似乎有抑郁症/焦虑症"这类话
4. 不要逐条罗列用户每天的心情，而是整体感受一周的情绪流动
5. 在结尾给予温暖的鼓励和陪伴
6. 语气像朋友写信一样自然，不要像分析报告
7. 直接输出正文，不要加标题和署名"""


def _build_mood_context(user):
    """构建用户最近心情上下文，供主动消息和每周小结使用。"""
    recent = list(MoodEntry.objects.filter(user=user)
                  .order_by("-date", "-at")[:7])
    if not recent:
        return None
    parts = []
    for e in reversed(recent):
        info = MOOD_MAP.get(e.mood, {})
        label = info.get("label", e.mood)
        level_names = {1: "略微", 2: "有点", 3: "相当", 4: "十分"}
        level_str = level_names.get(e.intensity_level, "")
        d = e.date.strftime("%m月%d日")
        note = f"，备注：{e.note[:60]}" if e.note else ""
        parts.append(f"{d} 记录了「{label}」{level_str}{note}")
    return "以下是用户最近的心情记录，供参考：\n" + "\n".join(parts)


def _build_chat_context(user):
    """构建用户最近对话上下文，供主动消息参考。"""
    recent = list(ChatMessage.objects.filter(
        user=user, is_proactive=False, is_weekly_essay=False
    ).order_by("-created_at")[:6])
    if not recent:
        return None
    recent.reverse()
    lines = [f"{m.role}: {m.content[:100]}" for m in recent]
    return "以下是用户最近的对话记录（供参考，不要重复提及）：\n" + "\n".join(lines)


def _generate_slots(today, count=None):
    """为某天生成随机时段（8:00-22:00 之间），每个时段之间至少间隔 1 小时。
    返回 [(slot_index, time), ...]"""
    if count is None:
        count = random.randint(2, 4)
    available = list(range(8, 22))  # 8:00-21:00 每个整点
    if count > len(available):
        count = len(available)
    chosen = sorted(random.sample(available, count))
    result = []
    for i, hour in enumerate(chosen):
        minute = random.randint(0, 50)
        result.append((i, dt.time(hour, minute)))
    return result


class Command(BaseCommand):
    help = "生成 AI 主动消息和每周小结"

    def add_arguments(self, parser):
        parser.add_argument("--force-user", type=int, default=None,
                            help="只对指定用户 ID 执行（测试用）")
        parser.add_argument("--force-essay", action="store_true",
                            help="强制生成每周小结（测试用）")
        parser.add_argument("--dry-run", action="store_true",
                            help="只打印计划，不实际发送")

    def handle(self, *args, **options):
        now = timezone.localtime(timezone.now())
        today = now.date()
        current_time = now.time()

        force_user = options.get("force_user")
        force_essay = options.get("force_essay", False)
        dry_run = options.get("dry_run", False)

        # 确定活跃用户：有过对话记录或心情记录的用户
        users = User.objects.filter(
            Q(chats__isnull=False) | Q(moods__isnull=False)
        ).distinct()
        if force_user:
            users = users.filter(id=force_user)

        if not users:
            self.stdout.write("没有活跃用户")
            return

        is_sunday = now.weekday() == 6  # Sunday
        is_essay_hour = (now.hour == 22 and now.minute < 30) or force_essay

        self.stdout.write(f"检查 {users.count()} 个用户（{today} {current_time.strftime('%H:%M')}）")

        for user in users:
            self._process_user(user, today, current_time, is_sunday,
                               is_essay_hour, force_essay, dry_run)

    def _process_user(self, user, today, current_time,
                      is_sunday, is_essay_hour, force_essay, dry_run):
        # 1. 检查/创建今日时段
        existing_slots = list(ProactiveSchedule.objects.filter(
            user=user, date=today, is_weekly_essay=False))
        if not existing_slots:
            slots = _generate_slots(today)
            for idx, tm in slots:
                ProactiveSchedule.objects.create(
                    user=user, date=today, slot_index=idx, slot_time=tm)
            existing_slots = list(ProactiveSchedule.objects.filter(
                user=user, date=today, is_weekly_essay=False))
            self.stdout.write(f"  [{user.username}] 生成 {len(slots)} 个时段")

        # 2. 执行到期的主动消息时段
        for slot in existing_slots:
            if slot.executed:
                continue
            if slot.slot_time > current_time:
                continue
            if dry_run:
                self.stdout.write(f"  [{user.username}] 将发送 slot={slot.slot_index} "
                                  f"({slot.slot_time.strftime('%H:%M')}) [DRY RUN]")
                continue
            self._send_proactive(user, slot)

        # 3. 每周小结（周日 22:00）
        if is_sunday and is_essay_hour:
            # 本周日 0 点
            week_start = dt.datetime.combine(today, dt.time.min)
            week_end = week_start + dt.timedelta(days=7)
            week_start_aware = timezone.make_aware(week_start)
            week_end_aware = timezone.make_aware(week_end)

            existing_essay = ChatMessage.objects.filter(
                user=user, is_weekly_essay=True,
                created_at__gte=week_start_aware,
                created_at__lt=week_end_aware,
            ).exists()
            if not existing_essay or force_essay:
                if dry_run:
                    self.stdout.write(f"  [{user.username}] 将发送每周小结 [DRY RUN]")
                    return
                self._send_weekly_essay(user)

    def _send_proactive(self, user, slot):
        """给用户发送一条主动消息。"""
        mood_ctx = _build_mood_context(user)
        chat_ctx = _build_chat_context(user)

        history = []
        if mood_ctx:
            history.append({"role": "system", "content": mood_ctx})
        if chat_ctx:
            history.append({"role": "system", "content": chat_ctx})
        history.append({"role": "user",
                        "content": "（时间到了，主动和用户打个招呼吧）"})

        reply, err = deepseek.chat(
            history,
            prompt=PROACTIVE_PROMPT,
            max_tokens=300,
            temperature=0.8,
        )
        if reply is None:
            self.stdout.write(f"  [{user.username}] 主动消息失败: {err}")
            return

        ChatMessage.objects.create(
            user=user, role="assistant", content=reply,
            is_proactive=True)
        slot.executed = True
        slot.save(update_fields=["executed"])
        self.stdout.write(f"  [{user.username}] 主动消息 slot={slot.slot_index} OK")

    def _send_weekly_essay(self, user):
        """给用户发送每周小结。"""
        mood_ctx = _build_mood_context(user)

        history = []
        if mood_ctx:
            history.append({"role": "system", "content": mood_ctx})
        history.append({"role": "user",
                        "content": "请为我写一篇本周心情小结小作文。"})

        reply, err = deepseek.chat(
            history,
            prompt=WEEKLY_ESSAY_PROMPT,
            max_tokens=2000,
            temperature=0.85,
        )
        if reply is None:
            self.stdout.write(f"  [{user.username}] 每周小结失败: {err}")
            return

        ChatMessage.objects.create(
            user=user, role="assistant", content=reply,
            is_proactive=True, is_weekly_essay=True)
        self.stdout.write(f"  [{user.username}] 每周小结 OK")