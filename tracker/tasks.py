from celery import shared_task
from django.core.management import call_command
from .models import Session
from django.utils import timezone
from datetime import timedelta
from .batch_processor import BatchEventProcessor
from .monitoring import WebsiteMonitor
@shared_task
def aggregate_daily_stats():
    """Background task to aggregate daily statistics"""
    call_command('aggregate_daily_stats')

@shared_task
def cleanup_old_sessions():
    """Cleanup sessions that haven't been updated in a while"""
    cutoff_time = timezone.now() - timedelta(minutes=30)
    
    old_sessions = Session.objects.filter(
        ended_at__isnull=True,
        started_at__lt=cutoff_time
    )
    
    for session in old_sessions:
        session.ended_at = session.started_at + timedelta(minutes=30)
        session.duration_seconds = 1800  # 30 minutes
        session.save()
@shared_task
def process_event_batches():
    """Process queued analytics events"""
    processor = BatchEventProcessor()
    return processor.process_batch()

@shared_task
def monitor_websites():
    """Monitor all websites"""
    monitor = WebsiteMonitor()
    monitor.monitor_all_websites()
    return "Website monitoring completed"

@shared_task
def cleanup_old_data():
    """Cleanup old analytics data"""
    from django.utils import timezone
    from datetime import timedelta
    from .models import PageView, CustomEvent, Session
    
    # Delete data older than 2 years
    cutoff_date = timezone.now() - timedelta(days=730)
    
    deleted_pageviews = PageView.objects.filter(timestamp__lt=cutoff_date).delete()[0]
    deleted_events = CustomEvent.objects.filter(timestamp__lt=cutoff_date).delete()[0]
    deleted_sessions = Session.objects.filter(started_at__lt=cutoff_date).delete()[0]
    
    return f"Deleted {deleted_pageviews} pageviews, {deleted_events} events, {deleted_sessions} sessions"
