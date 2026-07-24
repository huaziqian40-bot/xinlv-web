from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]

# 媒体文件（用户上传的音乐）始终由 Django 提供，DEBUG=False 时也能播放。
# 适合本项目这种小规模站点；若日后流量大，再交给反向代理托管 media/。
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]

# 静态文件：DEBUG 模式由 Django 提供；生产由 whitenoise 提供（collectstatic 后）。
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
