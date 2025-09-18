from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.db.models import Count, Avg, Q, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import datetime, timedelta
import json
from django.core.cache import cache
from .models import Website, PageView, Session, Visitor, CustomEvent, DailyStats
from .serializers import (
    WebsiteSerializer, EventIngestionSerializer, PageViewAnalyticsSerializer,
    SessionAnalyticsSerializer, TrafficSourceSerializer, DeviceStatsSerializer,
    BrowserStatsSerializer, GeographyStatsSerializer
)
from .utils import parse_user_agent, get_traffic_source, get_location_from_ip
from .batch_processor import BatchEventProcessor

class WebsiteViewSet(viewsets.ModelViewSet):
    serializer_class = WebsiteSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Website.objects.filter(owner=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

@api_view(['POST'])
@permission_classes([AllowAny])
def ingest_event(request):
    """
    Event ingestion endpoint with validation and basic protections
    """
    serializer = EventIngestionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    
    try:
        # Get website
        website = Website.objects.get(
            tracking_id=data['tracking_id'],
            is_active=True
        )
        
        # Get or create visitor
        visitor, visitor_created = Visitor.objects.get_or_create(
            website=website,
            visitor_id=data['visitor_id'],
            defaults={'is_returning': False}
        )
        
        if not visitor_created:
            visitor.is_returning = True
            visitor.last_seen = timezone.now()
            visitor.save()
        
        # Parse user agent for device/browser info
        device_info = parse_user_agent(data.get('user_agent', ''))
        
        # Get location from IP
        client_ip = get_client_ip(request)
        location_info = get_location_from_ip(client_ip)
        
        # Get or create session
        session, session_created = Session.objects.get_or_create(
            website=website,
            session_id=data['session_id'],
            defaults={
                'visitor': visitor,
                'user_agent': data.get('user_agent', ''),
                'device_type': device_info.get('device_type', 'unknown'),
                'browser_name': device_info.get('browser_name', 'unknown'),
                'browser_version': device_info.get('browser_version', 'unknown'),
                'os_name': device_info.get('os_name', 'unknown'),
                'os_version': device_info.get('os_version', 'unknown'),
                'ip_address': client_ip,
                'country': location_info.get('country'),
                'region': location_info.get('region'),
                'city': location_info.get('city'),
            }
        )
        
        # Process event based on type
        if data['event_type'] == 'pageview':
            create_pageview(website, session, visitor, data, location_info)
        elif data['event_type'] == 'custom':
            create_custom_event(website, session, visitor, data)
        
        return Response({'status': 'success'}, status=status.HTTP_201_CREATED)
        
    except Website.DoesNotExist:
        return Response(
            {'error': 'Invalid tracking ID'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def create_pageview(website, session, visitor, data, location_info):
    """Create a page view record"""
    page_path = data['page_url'].split('?')[0] if data.get('page_url') else '/'
    
    # Determine traffic source
    traffic_source = get_traffic_source(
        data.get('referrer_url'),
        data.get('utm_source'),
        data.get('utm_medium')
    )
    
    pageview = PageView.objects.create(
        website=website,
        session=session,
        visitor=visitor,
        page_url=data.get('page_url', ''),
        page_title=data.get('page_title', ''),
        page_path=page_path,
        referrer_url=data.get('referrer_url'),
        referrer_domain=get_domain_from_url(data.get('referrer_url')),
        traffic_source=traffic_source,
        utm_source=data.get('utm_source'),
        utm_medium=data.get('utm_medium'),
        utm_campaign=data.get('utm_campaign'),
        utm_term=data.get('utm_term'),
        utm_content=data.get('utm_content'),
        screen_width=data.get('screen_width'),
        screen_height=data.get('screen_height'),
        viewport_width=data.get('viewport_width'),
        viewport_height=data.get('viewport_height'),
    )
    
    # Update session page views count
    session.page_views = F('page_views') + 1
    session.save()

def create_custom_event(website, session, visitor, data):
    """Create a custom event record"""
    CustomEvent.objects.create(
        website=website,
        session=session,
        visitor=visitor,
        event_name=data.get('event_name', ''),
        event_category=data.get('event_category'),
        event_action=data.get('event_action'),
        event_label=data.get('event_label'),
        event_value=data.get('event_value'),
        properties=data.get('properties', {}),
    )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def analytics_overview(request, website_id):
    """Get overview analytics for a website"""
    try:
        website = Website.objects.get(id=website_id, owner=request.user)
        
        # Date range filtering
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Basic metrics
        total_page_views = PageView.objects.filter(
            website=website,
            timestamp__date__range=[start_date, end_date]
        ).count()
        
        unique_visitors = Visitor.objects.filter(
            website=website,
            first_seen__date__range=[start_date, end_date]
        ).count()
        
        total_sessions = Session.objects.filter(
            website=website,
            started_at__date__range=[start_date, end_date]
        ).count()
        
        avg_session_duration = Session.objects.filter(
            website=website,
            started_at__date__range=[start_date, end_date],
            duration_seconds__gt=0
        ).aggregate(avg_duration=Avg('duration_seconds'))['avg_duration'] or 0
        
        return Response({
            'total_page_views': total_page_views,
            'unique_visitors': unique_visitors,
            'total_sessions': total_sessions,
            'avg_session_duration': round(avg_session_duration, 2),
            'date_range': {
                'start_date': start_date,
                'end_date': end_date
            }
        })
        
    except Website.DoesNotExist:
        return Response(
            {'error': 'Website not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def page_views_analytics(request, website_id):
    """Get page views analytics"""
    try:
        website = Website.objects.get(id=website_id, owner=request.user)
        
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Daily page views trend
        daily_stats = PageView.objects.filter(
            website=website,
            timestamp__date__range=[start_date, end_date]
        ).extra(
            select={'date': 'DATE(timestamp)'}
        ).values('date').annotate(
            page_views=Count('id'),
            unique_page_views=Count('page_path', distinct=True)
        ).order_by('date')
        
        # Top pages
        top_pages = PageView.objects.filter(
            website=website,
            timestamp__date__range=[start_date, end_date]
        ).values('page_path', 'page_title').annotate(
            views=Count('id'),
            unique_views=Count('visitor', distinct=True)
        ).order_by('-views')[:10]
        
        return Response({
            'daily_stats': list(daily_stats),
            'top_pages': list(top_pages)
        })
        
    except Website.DoesNotExist:
        return Response(
            {'error': 'Website not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sessions_analytics(request, website_id):
    """Get sessions analytics"""
    try:
        website = Website.objects.get(id=website_id, owner=request.user)
        
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Daily sessions
        daily_sessions = Session.objects.filter(
            website=website,
            started_at__date__range=[start_date, end_date]
        ).extra(
            select={'date': 'DATE(started_at)'}
        ).values('date').annotate(
            sessions=Count('id'),
            avg_duration=Avg('duration_seconds'),
            bounce_rate=Count('id', filter=Q(page_views=1)) * 100.0 / Count('id')
        ).order_by('date')
        
        return Response({
            'daily_sessions': list(daily_sessions)
        })
        
    except Website.DoesNotExist:
        return Response(
            {'error': 'Website not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def users_analytics(request, website_id):
    """Get new vs returning users analytics"""
    try:
        website = Website.objects.get(id=website_id, owner=request.user)
        
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Daily new vs returning users
        daily_users = Session.objects.filter(
            website=website,
            started_at__date__range=[start_date, end_date]
        ).extra(
            select={'date': 'DATE(started_at)'}
        ).values('date').annotate(
            new_users=Count('visitor', filter=Q(visitor__is_returning=False)),
            returning_users=Count('visitor', filter=Q(visitor__is_returning=True))
        ).order_by('date')
        
        return Response({
            'daily_users': list(daily_users)
        })
        
    except Website.DoesNotExist:
        return Response(
            {'error': 'Website not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def traffic_sources_analytics(request, website_id):
    """Get traffic sources analytics"""
    try:
        website = Website.objects.get(id=website_id, owner=request.user)
        
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Traffic sources
        sources = PageView.objects.filter(
            website=website,
            timestamp__date__range=[start_date, end_date]
        ).values('traffic_source').annotate(
            sessions=Count('session', distinct=True)
        ).order_by('-sessions')
        
        total_sessions = sum(item['sessions'] for item in sources)
        
        # Add percentage
        for source in sources:
            source['percentage'] = (source['sessions'] / total_sessions * 100) if total_sessions > 0 else 0
        
        return Response({
            'traffic_sources': list(sources)
        })
        
    except Website.DoesNotExist:
        return Response(
            {'error': 'Website not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def devices_analytics(request, website_id):
    """Get device analytics"""
    try:
        website = Website.objects.get(id=website_id, owner=request.user)
        
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Device types
        devices = Session.objects.filter(
            website=website,
            started_at__date__range=[start_date, end_date]
        ).values('device_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # OS distribution
        os_stats = Session.objects.filter(
            website=website,
            started_at__date__range=[start_date, end_date]
        ).values('os_name').annotate(
            count=Count('id')
        ).order_by('-count')
        
        total_sessions = sum(item['count'] for item in devices)
        
        # Add percentage
        for device in devices:
            device['percentage'] = (device['count'] / total_sessions * 100) if total_sessions > 0 else 0
        
        for os in os_stats:
            os['percentage'] = (os['count'] / total_sessions * 100) if total_sessions > 0 else 0
        
        return Response({
            'devices': list(devices),
            'operating_systems': list(os_stats)
        })
        
    except Website.DoesNotExist:
        return Response(
            {'error': 'Website not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def browsers_analytics(request, website_id):
    """Get browser analytics"""
    try:
        website = Website.objects.get(id=website_id, owner=request.user)
        
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Browser distribution
        browsers = Session.objects.filter(
            website=website,
            started_at__date__range=[start_date, end_date]
        ).values('browser_name').annotate(
            count=Count('id')
        ).order_by('-count')
        
        total_sessions = sum(item['count'] for item in browsers)
        
        # Add percentage
        for browser in browsers:
            browser['percentage'] = (browser['count'] / total_sessions * 100) if total_sessions > 0 else 0
        
        return Response({
            'browsers': list(browsers)
        })
        
    except Website.DoesNotExist:
        return Response(
            {'error': 'Website not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def geography_analytics(request, website_id):
    """Get geography analytics"""
    try:
        website = Website.objects.get(id=website_id, owner=request.user)
        
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Countries
        countries = Session.objects.filter(
            website=website,
            started_at__date__range=[start_date, end_date]
        ).exclude(country__isnull=True).values('country').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Regions/Cities
        regions = Session.objects.filter(
            website=website,
            started_at__date__range=[start_date, end_date]
        ).exclude(region__isnull=True).values('country', 'region').annotate(
            count=Count('id')
        ).order_by('-count')[:20]
        
        total_sessions = sum(item['count'] for item in countries)
        
        # Add percentage
        for country in countries:
            country['percentage'] = (country['count'] / total_sessions * 100) if total_sessions > 0 else 0
        
        return Response({
            'countries': list(countries),
            'regions': list(regions)
        })
        
    except Website.DoesNotExist:
        return Response(
            {'error': 'Website not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


# Helper functions
def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_domain_from_url(url):
    """Extract domain from URL"""
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except:
        return None
@api_view(['POST'])
@permission_classes([AllowAny])
def ingest_event_optimized(request):
    """
    Optimized event ingestion with batching and caching
    """
    serializer = EventIngestionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    
    # Validate tracking ID from cache first
    cache_key = f"website:{data['tracking_id']}"
    website_exists = cache.get(cache_key)
    if website_exists is None:
        try:
            Website.objects.get(tracking_id=data['tracking_id'], is_active=True)
            cache.set(cache_key, True, timeout=3600)  # Cache for 1 hour
        except Website.DoesNotExist:
            cache.set(cache_key, False, timeout=300)  # Cache negative result for 5 minutes
            return Response({'error': 'Invalid tracking ID'}, status=status.HTTP_400_BAD_REQUEST)
    elif website_exists is False:
        return Response({'error': 'Invalid tracking ID'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'error': 'Invalid tracking ID'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Add client IP and processing metadata
    data['client_ip'] = get_client_ip(request)
    data['received_at'] = timezone.now().isoformat()
    processor = BatchEventProcessor()
    success = processor.queue_event(data)
    
    if success:
        return Response({'status': 'queued'}, status=status.HTTP_202_ACCEPTED)
    else:
        return Response({'error': 'Processing failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)