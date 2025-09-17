from rest_framework import serializers
from .models import Website, PageView, Session, CustomEvent, DailyStats

class WebsiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Website
        fields = ['id', 'name', 'domain', 'tracking_id', 'created_at', 'is_active']
        read_only_fields = ['id', 'tracking_id', 'created_at']

class EventIngestionSerializer(serializers.Serializer):
    tracking_id = serializers.UUIDField()
    visitor_id = serializers.CharField(max_length=255)
    session_id = serializers.CharField(max_length=255)
    
    # Event data
    event_type = serializers.ChoiceField(choices=['pageview', 'custom'])
    timestamp = serializers.DateTimeField()
    
    # Page view specific
    page_url = serializers.URLField(required=False)
    page_title = serializers.CharField(max_length=255, required=False)
    referrer_url = serializers.URLField(required=False, allow_blank=True)
    
    # UTM parameters
    utm_source = serializers.CharField(max_length=255, required=False, allow_blank=True)
    utm_medium = serializers.CharField(max_length=255, required=False, allow_blank=True)
    utm_campaign = serializers.CharField(max_length=255, required=False, allow_blank=True)
    utm_term = serializers.CharField(max_length=255, required=False, allow_blank=True)
    utm_content = serializers.CharField(max_length=255, required=False, allow_blank=True)
    
    # Device info
    user_agent = serializers.CharField(required=False, allow_blank=True)
    screen_width = serializers.IntegerField(required=False)
    screen_height = serializers.IntegerField(required=False)
    viewport_width = serializers.IntegerField(required=False)
    viewport_height = serializers.IntegerField(required=False)
    
    # Custom event specific
    event_name = serializers.CharField(max_length=255, required=False)
    event_category = serializers.CharField(max_length=100, required=False, allow_blank=True)
    event_action = serializers.CharField(max_length=100, required=False, allow_blank=True)
    event_label = serializers.CharField(max_length=255, required=False, allow_blank=True)
    event_value = serializers.FloatField(required=False)
    properties = serializers.JSONField(required=False)

class PageViewAnalyticsSerializer(serializers.Serializer):
    date = serializers.DateField()
    page_views = serializers.IntegerField()
    unique_page_views = serializers.IntegerField()

class SessionAnalyticsSerializer(serializers.Serializer):
    date = serializers.DateField()
    sessions = serializers.IntegerField()
    avg_duration = serializers.FloatField()
    bounce_rate = serializers.FloatField()

class TrafficSourceSerializer(serializers.Serializer):
    source = serializers.CharField()
    sessions = serializers.IntegerField()
    percentage = serializers.FloatField()

class DeviceStatsSerializer(serializers.Serializer):
    device_type = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()

class BrowserStatsSerializer(serializers.Serializer):
    browser = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()

class GeographyStatsSerializer(serializers.Serializer):
    country = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()
