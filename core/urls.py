from django.contrib.auth import views as auth_views
from django.urls import path
from . import views, admin_views, auth_views as my_auth, feature_views

urlpatterns = [
    path("", views.home, name="home"),
    path("save/", views.save_mood, name="save_mood"),
    path("day/", views.day_entries, name="day_entries"),
    path("calendar-data/", views.calendar_data, name="calendar_data"),

    # ---- 用户主页 / 徽章 / 头像 ----
    path("badges/", feature_views.badges_page, name="badges"),
    path("me/", feature_views.profile, name="profile"),
    path("me/edit/", feature_views.profile_edit, name="profile_edit"),
    path("u/<str:username>/", feature_views.profile_public, name="profile_public"),

    # ---- 用户上传内容 + AI 审核 ----
    path("contribute/", feature_views.contribute, name="contribute"),
    path("manage/review/", feature_views.review_queue, name="review_queue"),

    # ---- 多语言 ----
    path("set-language/", feature_views.set_language, name="set_language"),
    path("result/", views.result, name="result"),
    path("about/", views.about, name="about"),
    path("disclaimer/", views.disclaimer, name="disclaimer"),
    path("api/import-local/", views.import_local, name="import_local"),

    path("confidant/", views.confidant, name="confidant"),
    path("confidant/send/", views.confidant_send, name="confidant_send"),
    path("confidant/clear/", views.confidant_clear, name="confidant_clear"),
    path("confidant/tts/", views.tts_speak, name="tts_speak"),

    # ---- 用户认证（极简：账号+密码）----
    path("login/", auth_views.LoginView.as_view(
        template_name="registration/login.html", redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", my_auth.register, name="register"),

    # ---- 管理后台（仅 is_staff）----
    path("manage/", admin_views.dashboard, name="manage_home"),
    path("manage/songs/", admin_views.songs, name="manage_songs"),
    path("manage/tips/", admin_views.tips, name="manage_tips"),
    path("manage/activities/", admin_views.activities, name="manage_activities"),
    path("manage/videos/", admin_views.videos, name="manage_videos"),
    path("manage/site/", admin_views.site, name="manage_site"),
    path("manage/users/", admin_views.users, name="manage_users"),
]
