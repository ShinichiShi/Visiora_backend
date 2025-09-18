from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import uuid

class Website(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    domain = models.URLField()
    tracking_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.domain})"

class Visitor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.ForeignKey(Website, on_delete=models.CASCADE)
    visitor_id = models.CharField(max_length=255, db_index=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_returning = models.BooleanField(default=False)
    started_at = models.DateTimeField(default=timezone.now,db_index=True) 
    device_type = models.CharField(max_length=50, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    class Meta:
        unique_together = ['website', 'visitor_id']
        indexes = [
            models.Index(fields=['website', 'started_at']),
            models.Index(fields=['visitor_id', 'started_at']),
            models.Index(fields=['device_type', 'started_at']),
            models.Index(fields=['country', 'started_at']),
        ]

class Session(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.ForeignKey(Website, on_delete=models.CASCADE)
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE)
    session_id = models.CharField(max_length=255, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(default=0)
    page_views = models.IntegerField(default=0)
    
    # Device & Browser Info
    user_agent = models.TextField()
    device_type = models.CharField(max_length=50)  # desktop, mobile, tablet
    browser_name = models.CharField(max_length=100)
    browser_version = models.CharField(max_length=50)
    os_name = models.CharField(max_length=100)
    os_version = models.CharField(max_length=50)
    
    # Location Info
    ip_address = models.GenericIPAddressField()
    country = models.CharField(max_length=100, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)  
    
    class Meta:
        unique_together = ['website', 'session_id']

class PageView(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.ForeignKey(Website, on_delete=models.CASCADE)
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE)
    
    # Page Info
    page_url = models.URLField()
    page_title = models.CharField(max_length=255)
    page_path = models.CharField(max_length=500, db_index=True)
    
    # Referrer Info
    referrer_url = models.URLField(null=True, blank=True)
    referrer_domain = models.CharField(max_length=255, null=True, blank=True)
    traffic_source = models.CharField(max_length=100, null=True, blank=True)  # organic, social, direct, etc.
    
    # UTM Parameters
    utm_source = models.CharField(max_length=255, null=True, blank=True)
    utm_medium = models.CharField(max_length=255, null=True, blank=True)
    utm_campaign = models.CharField(max_length=255, null=True, blank=True)
    utm_term = models.CharField(max_length=255, null=True, blank=True)
    utm_content = models.CharField(max_length=255, null=True, blank=True)
    
    # Timing
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    time_on_page = models.IntegerField(null=True, blank=True)  # seconds

    # Screen Info
    screen_width = models.IntegerField(null=True, blank=True)
    screen_height = models.IntegerField(null=True, blank=True)
    viewport_width = models.IntegerField(null=True, blank=True)
    viewport_height = models.IntegerField(null=True, blank=True)
    class Meta:
        indexes = [
            models.Index(fields=['website', 'timestamp']),
            models.Index(fields=['visitor_id', 'timestamp']), 
            models.Index(fields=['session', 'timestamp']),
            models.Index(fields=['page_path', 'timestamp']),
            models.Index(fields=['traffic_source', 'timestamp']),
        ]

class CustomEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.ForeignKey(Website, on_delete=models.CASCADE)
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE)
    
    event_name = models.CharField(max_length=255, db_index=True)
    event_category = models.CharField(max_length=100, null=True, blank=True)
    event_action = models.CharField(max_length=100, null=True, blank=True)
    event_label = models.CharField(max_length=255, null=True, blank=True)
    event_value = models.FloatField(null=True, blank=True)
    
    # Custom properties (JSON field)
    properties = models.JSONField(default=dict, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

# Analytics aggregation models
class DailyStats(models.Model):
    website = models.ForeignKey(Website, on_delete=models.CASCADE)
    date = models.DateField(db_index=True)
    
    # Page views
    page_views = models.IntegerField(default=0)
    unique_page_views = models.IntegerField(default=0)
    
    # Sessions
    sessions = models.IntegerField(default=0)
    avg_session_duration = models.FloatField(default=0.0)
    bounce_rate = models.FloatField(default=0.0)
    
    # Users
    unique_visitors = models.IntegerField(default=0)
    new_visitors = models.IntegerField(default=0)
    returning_visitors = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['website', 'date']
