import json
import logging
from datetime import datetime, timedelta
from django.core.cache import cache
from django.db import transaction, connections
from django.utils import timezone
from redis import Redis
from .models import Website, Visitor, Session, PageView, CustomEvent
from .utils import parse_user_agent, get_traffic_source, get_location_from_ip

logger = logging.getLogger(__name__)

class BatchEventProcessor:
    """
    Handles batch processing of analytics events to reduce database load
    """
    def __init__(self):
        self.redis_client = Redis.from_url('redis://localhost:6379/0')
        self.batch_size = 100
        self.event_queue_key = 'analytics:event_queue'
        self.processing_lock_key = 'analytics:processing_lock'
    
    def queue_event(self, event_data):
        """Queue an event for batch processing"""
        try:
            # Add timestamp if not present
            if 'queued_at' not in event_data:
                event_data['queued_at'] = timezone.now().isoformat()
            
            # Push to Redis queue
            self.redis_client.lpush(
                self.event_queue_key, 
                json.dumps(event_data, default=str)
            )
            
            # Trigger processing if queue is getting full
            queue_length = self.redis_client.llen(self.event_queue_key)
            if queue_length >= self.batch_size:
                self.process_batch()
                
            return True
        except Exception as e:
            logger.error(f"Failed to queue event: {e}")
            # Fallback to immediate processing
            return self.process_single_event(event_data)
    
    def process_batch(self):
        """Process a batch of events"""
        # Acquire processing lock to prevent concurrent processing
        if not self.redis_client.set(self.processing_lock_key, '1', nx=True, ex=30):
            return False
        
        try:
            events = []
            # Get batch of events
            for _ in range(self.batch_size):
                event_data = self.redis_client.rpop(self.event_queue_key)
                if not event_data:
                    break
                events.append(json.loads(event_data))
            
            if not events:
                return True
            
            # Process events in batches by website
            events_by_website = {}
            for event in events:
                tracking_id = event.get('tracking_id')
                if tracking_id not in events_by_website:
                    events_by_website[tracking_id] = []
                events_by_website[tracking_id].append(event)
            
            # Process each website's events in a transaction
            for tracking_id, website_events in events_by_website.items():
                self.process_website_batch(tracking_id, website_events)
            
            logger.info(f"Processed batch of {len(events)} events")
            return True
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            # Put events back in queue
            for event in events:
                self.redis_client.lpush(self.event_queue_key, json.dumps(event, default=str))
            return False
        finally:
            self.redis_client.delete(self.processing_lock_key)
    
    @transaction.atomic
    def process_website_batch(self, tracking_id, events):
        """Process events for a single website in a transaction"""
        try:
            website = Website.objects.select_related().get(
                tracking_id=tracking_id, is_active=True
            )
        except Website.DoesNotExist:
            logger.warning(f"Website not found for tracking_id: {tracking_id}")
            return
        
        # Bulk create/update visitors, sessions, and events
        self.bulk_process_events(website, events)
    
    def bulk_process_events(self, website, events):
        """Bulk process events to minimize database queries"""
        visitors_to_create = []
        visitors_to_update = []
        sessions_to_create = []
        pageviews_to_create = []
        custom_events_to_create = []
        
        # Cache for visitor and session lookups
        visitor_cache = {}
        session_cache = {}
        
        for event_data in events:
            visitor_id = event_data.get('visitor_id')
            session_id = event_data.get('session_id')
            
            # Handle visitor
            if visitor_id not in visitor_cache:
                visitor, created = self.get_or_prepare_visitor(
                    website, visitor_id, visitors_to_create, visitors_to_update
                )
                visitor_cache[visitor_id] = visitor
            else:
                visitor = visitor_cache[visitor_id]
            
            # Handle session
            session_key = f"{visitor_id}:{session_id}"
            if session_key not in session_cache:
                session = self.get_or_prepare_session(
                    website, visitor, session_id, event_data, sessions_to_create
                )
                session_cache[session_key] = session
            else:
                session = session_cache[session_key]
            
            # Handle event
            if event_data.get('event_type') == 'pageview':
                pageview = self.prepare_pageview(website, session, visitor, event_data)
                pageviews_to_create.append(pageview)
            elif event_data.get('event_type') == 'custom':
                custom_event = self.prepare_custom_event(website, session, visitor, event_data)
                custom_events_to_create.append(custom_event)
        
        # Bulk create/update
        if visitors_to_create:
            Visitor.objects.bulk_create(visitors_to_create, ignore_conflicts=True)
        
        if visitors_to_update:
            Visitor.objects.bulk_update(visitors_to_update, ['last_seen', 'is_returning'])
        
        if sessions_to_create:
            Session.objects.bulk_create(sessions_to_create, ignore_conflicts=True)
        
        if pageviews_to_create:
            PageView.objects.bulk_create(pageviews_to_create)
        
        if custom_events_to_create:
            CustomEvent.objects.bulk_create(custom_events_to_create)
    
    def get_or_prepare_visitor(self, website, visitor_id, to_create, to_update):
        """Get existing visitor or prepare for bulk create/update"""
        try:
            visitor = Visitor.objects.get(website=website, visitor_id=visitor_id)
            visitor.last_seen = timezone.now()
            visitor.is_returning = True
            to_update.append(visitor)
            return visitor, False
        except Visitor.DoesNotExist:
            visitor = Visitor(
                website=website,
                visitor_id=visitor_id,
                first_seen=timezone.now(),
                is_returning=False
            )
            to_create.append(visitor)
            return visitor, True
    
    def prepare_pageview(self, website, session, visitor, event_data):
        """Prepare PageView object for bulk creation"""
        page_path = event_data.get('page_url', '/').split('?')[0]
        
        return PageView(
            website=website,
            session=session,
            visitor=visitor,
            page_url=event_data.get('page_url', ''),
            page_title=event_data.get('page_title', ''),
            page_path=page_path,
            referrer_url=event_data.get('referrer_url'),
            traffic_source=get_traffic_source(
                event_data.get('referrer_url'),
                event_data.get('utm_source'),
                event_data.get('utm_medium')
            ),
            utm_source=event_data.get('utm_source'),
            utm_medium=event_data.get('utm_medium'),
            utm_campaign=event_data.get('utm_campaign'),
            utm_term=event_data.get('utm_term'),
            utm_content=event_data.get('utm_content'),
            screen_width=event_data.get('screen_width'),
            screen_height=event_data.get('screen_height'),
            viewport_width=event_data.get('viewport_width'),
            viewport_height=event_data.get('viewport_height'),
            timestamp=datetime.fromisoformat(event_data.get('timestamp').replace('Z', '+00:00'))
        )
