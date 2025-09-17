from celery import shared_task
from django.core.management import call_command
from .models import Session
from django.utils import timezone
from datetime import timedelta

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
