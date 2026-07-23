"""填充示例数据：舒缓行为 + 心理学小知识。
用法：python manage.py seed_data
心理学条目为通识科普，仅作示例，可在 /admin/ 自行增删改。
"""
from django.core.management.base import BaseCommand
from core.models import Activity, PsychologyTip, SiteSettings

ACTIVITIES = [
    ("出门散步 15 分钟，专注感受脚步和呼吸", "anxious,sad,tired,numb"),
    ("写下三件今天还算顺利的小事", "anxious,sad,lonely"),
    ("给一个信任的人发条消息", "lonely,sad"),
    ("用温水慢慢洗个手或洗把脸，把注意力拉回当下", "anxious,numb"),
    ("做 10 个深蹲或拉伸，让身体动起来", "angry,tired,numb"),
    ("把烦心事写在纸上，然后撕掉", "angry,anxious"),
    ("听一段白噪音或雨声，闭眼休息", "tired,anxious"),
    ("整理一小块桌面或房间，获得一点掌控感", "numb,anxious"),
    ("喝一杯温水，慢慢喝完", "angry,tired"),
    ("看看窗外的远处，让眼睛和大脑放松", ""),
]

TIPS = [
    ("情绪有「半衰期」",
     "大多数强烈情绪的生理高峰只会持续几分钟到十几分钟。当下觉得过不去时，"
     "提醒自己「再等一会儿」，往往强度自己就会下降。", "情绪 ABC / 神经科学常识"),
    ("命名情绪能降低它的强度",
     "把感受具体说出来——「我现在很焦虑」「我有点失望」——会激活大脑前额叶、抑制杏仁核反应，"
     "这叫 affect labeling。说出来，情绪就没那么吓人了。", "Lieberman 等情绪标注研究"),
    ("正面情绪要主动「延长」",
     "开心的时候多停留几秒、刻意回味，能让好心情在记忆里扎得更深。"
     "心理学家称之为 savoring（细品）。", "积极心理学"),
    ("助人会反过来提升自己",
     "做一件帮助别人的小事会带来 helper's high，提升幸福感。"
     "心情好的时候，是做善事、攒好心情的好时机。", "亲社会行为研究"),
    ("感恩练习有累积效应",
     "每天记下几件值得感激的小事，坚持几周后整体幸福感会上升。"
     "趁着心情好，把今天的好事记下来吧。", "Emmons 感恩研究"),
    ("社交连接是幸福最稳的预测因子",
     "长期研究发现，决定一个人是否幸福、健康的最强因素之一是关系质量，而不是收入或成就。"
     "心情好时，别忘了维系那些重要的人。", "哈佛成人发展研究"),
]


class Command(BaseCommand):
    help = "填充示例的舒缓行为和心理学小知识"

    def handle(self, *args, **opts):
        for text, moods in ACTIVITIES:
            Activity.objects.get_or_create(text=text, defaults={"moods": moods})
        for title, content, source in TIPS:
            PsychologyTip.objects.get_or_create(title=title, defaults={"content": content, "source": source})

        # 预置网站设置：联系方式 + 关于我们起始内容（之后可在 /manage/site/ 修改）
        s = SiteSettings.load()
        if not s.contact_email:
            s.contact_email = "huaziqian40@gmail.com"
            s.contact_phone = "13675821816"
            s.contact_wechat = "int_32_2147483647"
            s.crisis_hotline = "12356"
            s.about_content = (
                "# 关于我们\n\n"
                "你好，这里是 **心情树洞** —— 一个用来记录心情、被温柔接住的小角落。\n\n"
                "我会在 B 站发布 ASMR 与心理学小知识的视频，也会作为「树洞」倾听陌生人的情绪。\n\n"
                "这个网站里有：\n\n"
                "- 📅 **心情日历**：记录每天的感受，按心情推荐舒缓的音乐和方法\n"
                "- 🌙 **AI 树洞**：随时找它说说话\n\n"
                "> 这里的内容只是陪伴，不能替代专业心理帮助。如果你很难受，记得也向身边信任的人求助。\n\n"
                "（这段内容可以在管理后台「关于我们」里随时修改。）"
            )
            s.save()

        self.stdout.write(self.style.SUCCESS(
            f"完成：行为 {Activity.objects.count()} 条，小知识 {PsychologyTip.objects.count()} 条。"))
