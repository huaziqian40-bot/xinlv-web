from django.contrib import admin
from .models import MoodEntry, Song, Activity, PsychologyTip, ChatMessage


@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    list_display = ("title", "artist", "moods")
    search_fields = ("title", "artist")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("text", "moods")


@admin.register(PsychologyTip)
class PsychologyTipAdmin(admin.ModelAdmin):
    list_display = ("title", "source")
    search_fields = ("title", "content")


@admin.register(MoodEntry)
class MoodEntryAdmin(admin.ModelAdmin):
    list_display = ("date", "mood", "session_key", "created_at")
    list_filter = ("mood",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "role", "session_key")
    list_filter = ("role",)
