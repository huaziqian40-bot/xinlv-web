"""自定义中间件：无尾斜杠请求在内部改写为带斜杠，避免 301 重定向循环。

背景：Cloudflare 边缘的 URL 规范化会把 /login/、/about/ 的尾部斜杠删掉再转发给源站，
而 Django 的 APPEND_SLASH 又对无斜杠路径返回 301 补斜杠 —— 两者冲突，
浏览器请求带斜杠路径时永远拿到 301 指向同一路径，报 ERR_TOO_MANY_REDIRECTS。

此中间件在 CommonMiddleware 之前运行：若某无斜杠路径补上斜杠后能匹配路由，
就直接内部改写 path_info，让视图正常渲染并返回 200，不再产生 301。
"""
from django.urls import Resolver404, resolve


class InternalAppendSlashMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        # 无尾斜杠且非静态资源：尝试在内部补斜杠
        if path and not path.endswith("/") and not path.startswith("/static/"):
            try:
                resolve(path + "/")
            except Resolver404:
                pass  # 补斜杠也匹配不到路由，保持原样（走正常 404）
            else:
                request.path_info = path + "/"
        return self.get_response(request)
