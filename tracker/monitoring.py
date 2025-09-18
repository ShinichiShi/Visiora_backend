import requests
import time
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.db.models import Count, Avg
from tracker.models import Website, PageView, Session
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class WebsiteMonitor:
    """
    Monitor websites for analytics collection and health
    """
    def __init__(self):
        self.check_interval = 300  # 5 minutes
        self.alert_thresholds = {
            'no_data_hours': 2,  # Alert if no data for 2 hours
            'traffic_drop_percent': 50,  # Alert if traffic drops by 50%
            'error_rate_percent': 10,  # Alert if error rate > 10%
        }
    
    def monitor_all_websites(self):
        """Monitor all active websites"""
        websites = Website.objects.filter(is_active=True).select_related('owner')
        
        for website in websites:
            try:
                self.check_website_health(website)
                self.check_analytics_flow(website)
                self.check_traffic_anomalies(website)
            except Exception as e:
                logger.error(f"Monitoring failed for website {website.id}: {e}")
    
    def check_website_health(self, website):
        """Check if website is accessible"""
        try:
            response = requests.get(website.domain, timeout=10)
            is_healthy = response.status_code == 200
            
            # Cache health status
            cache.set(f"website_health:{website.id}", {
                'healthy': is_healthy,
                'status_code': response.status_code,
                'response_time': response.elapsed.total_seconds(),
                'checked_at': datetime.now().isoformat()
            }, timeout=600)
            
            return is_healthy
        except Exception as e:
            logger.warning(f"Health check failed for {website.domain}: {e}")
            cache.set(f"website_health:{website.id}", {
                'healthy': False,
                'error': str(e),
                'checked_at': datetime.now().isoformat()
            }, timeout=600)
            return False
    
    def check_analytics_flow(self, website):
        """Check if analytics data is flowing"""
        now = timezone.now()
        cutoff = now - timedelta(hours=self.alert_thresholds['no_data_hours'])
        
        recent_events = PageView.objects.filter(
            website=website,
            timestamp__gte=cutoff
        ).count()
        
        if recent_events == 0:
            self.send_alert(
                website, 
                'No Analytics Data', 
                f"No analytics data received for {self.alert_thresholds['no_data_hours']} hours"
            )
        
        return recent_events > 0
    
    def check_traffic_anomalies(self, website):
        """Check for traffic anomalies"""
        now = timezone.now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        
        # Get today's traffic
        today_traffic = PageView.objects.filter(
            website=website,
            timestamp__date=today
        ).count()
        
        # Get average traffic for the past week
        avg_weekly_traffic = PageView.objects.filter(
            website=website,
            timestamp__date__range=[week_ago, yesterday]
        ).count() / 7
        
        if avg_weekly_traffic > 0:
            drop_percent = ((avg_weekly_traffic - today_traffic) / avg_weekly_traffic) * 100
            
            if drop_percent >= self.alert_thresholds['traffic_drop_percent']:
                self.send_alert(
                    website,
                    'Traffic Drop Alert',
                    f"Traffic dropped by {drop_percent:.1f}% compared to weekly average"
                )
    
    def send_alert(self, website, subject, message):
        """Send alert to website owner"""
        try:
            send_mail(
                subject=f"[Analytics Alert] {subject} - {website.name}",
                message=f"Website: {website.name} ({website.domain})\n\n{message}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[website.owner.email],
                fail_silently=False
            )
            logger.info(f"Alert sent to {website.owner.email}: {subject}")
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
