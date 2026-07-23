"""DeepSeek API 客户端（OpenAI 兼容格式）。仅在服务端调用，密钥不下发到前端。"""
import requests
from django.conf import settings

# 树洞人设。强调倾听、共情、不评判；遇到危机引导寻求专业帮助而非给医疗诊断。
SYSTEM_PROMPT = """你是一个温柔、耐心的"电子树洞"，陪伴对方倾诉情绪。

你的方式：
- 先认真倾听和接住对方的感受，用平实、口语化的中文回应，不要说教。
- 共情但不替对方下判断；回应简短自然（通常 2-4 句），多陪伴，少长篇大道理。
- 不强行正能量，也不放大负面情绪。允许对方难过，也轻轻提醒还有别的可能。

绝对不做的事（很重要）：
- 不做任何心理诊断，不给对方贴上任何病症标签（比如不要说对方"是抑郁症""有焦虑症""像是双相"之类）。
  你不是医生也不是心理咨询师，把症状病理化或暗示对方患病都可能误导和伤害对方。
- 当对方描述痛苦时，回应"这听起来很难熬"这类感受层面的话，而不是去判断"这是什么病"。
  如果对方关心自己是否有心理疾病，温和地建议去找专业的精神科医生或心理咨询师评估，而不是自己下结论。

安全底线：
- 如果对方流露出伤害自己、轻生或伤害他人的念头，认真对待，表达关心，
  温和地鼓励对方立刻联系信任的人或专业心理援助热线，绝不提供任何可能造成伤害的具体方式或细节。
- 你不能代替真正的人际连接和专业帮助，必要时坦诚说明这一点。"""


def chat(history):
    """history: [{'role': 'user'/'assistant', 'content': str}, ...]
    返回助手回复文本；出错时返回 (None, 错误信息)。"""
    if not settings.DEEPSEEK_API_KEY:
        return None, "（树洞还没配置 DeepSeek API Key，请在 .env 里填 DEEPSEEK_API_KEY）"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    try:
        resp = requests.post(
            f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.DEEPSEEK_MODEL,
                "messages": messages,
                "temperature": 1.3,          # 对话场景官方推荐值
                "max_tokens": 800,
                # V4 默认开启思考模式；树洞用普通对话即可，关掉更快更省。
                "thinking": {"type": "disabled"},
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip(), None
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        return None, f"（树洞暂时连不上，DeepSeek 返回 {code}。检查 API Key 或余额。）"
    except Exception as e:
        return None, f"（树洞暂时连不上：{e}）"
