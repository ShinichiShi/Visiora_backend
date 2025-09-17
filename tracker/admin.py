from django.contrib import admin
from .models import Website, Visitor, Session, PageView, CustomEvent, DailyStats

@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = ['name', 'domain', 'owner', 'tracking_id', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'domain', 'owner__username']
    readonly_fields = ['tracking_id', 'created_at', 'updated_at']

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'website', 'device_type', 'browser_name', 'country', 'started_at']
    list_filter = ['device_type', 'browser_name', 'country', 'started_at']
    search_fields = ['session_id', 'visitor__visitor_id']
    readonly_fields = ['started_at']

@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ['page_path', 'website', 'traffic_source', 'timestamp']
    list_filter = ['traffic_source', 'timestamp', 'website']
    search_fields = ['page_path', 'page_title', 'referrer_url']

@admin.register(CustomEvent)
class CustomEventAdmin(admin.ModelAdmin):
    list_display = ['event_name', 'event_category', 'website', 'timestamp']
    list_filter = ['event_name', 'event_category', 'timestamp']
    search_fields = ['event_name', 'event_category', 'event_action']
