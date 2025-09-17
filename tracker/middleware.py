from django.utils import timezone
from .models import Session
import logging

logger = logging.getLogger(__name__)

class EventProcessingMiddleware:
    """Middleware for processing analytics events"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Process any pending session updates
        if hasattr(request, '_analytics_session_id'):
            try:
                self.update_session_duration(request._analytics_session_id)
            except Exception as e:
                logger.error(f"Error updating session duration: {e}")
        
        return response
    
    def update_session_duration(self, session_id):
        """Update session duration and end time"""
        try:
            session = Session.objects.get(session_id=session_id)
            now = timezone.now()
            session.ended_at = now
            
            if session.started_at:
                duration = (now - session.started_at).total_seconds()
                session.duration_seconds = int(duration)
            
            session.save()
        except Session.DoesNotExist:
            pass