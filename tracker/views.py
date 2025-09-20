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
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import Website
from django.http import HttpResponseForbidden
from django.http import JsonResponse

class WebsiteViewSet(viewsets.ModelViewSet):
    serializer_class = WebsiteSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Website.objects.filter(owner=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
@csrf_exempt
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
        if not session_created and not session.country:
            session.country = location_info.get('country')
            session.region = location_info.get('region') 
            session.city = location_info.get('city')
            session.save()
        
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

# @login_required
def website_detail_dashboard(request, website_id):
    """
    Dashboard view for displaying website tracking code and setup instructions
    """
    website = get_object_or_404(Website, id=website_id)
    
    # Ensure user owns the website
    # if website.owner != request.user:
    #     return HttpResponseForbidden("You don't have permission to view this website.")
    
    return render(request, 'tracker/website_detail.html', {
        'website': website
    })


@csrf_exempt
@api_view(['POST', 'GET'])
@permission_classes([AllowAny])
def debug_ingest(request):
    """
    Debug endpoint to test ingestion without validation
    """
    if request.method == 'GET':
        return JsonResponse({
            'status': 'Debug endpoint is working',
            'tracking_id': '3eb68919-b515-4fa1-b00e-975a3f0eb8e8',
            'api_url': request.build_absolute_uri('/api/tracker/ingest/'),
            'debug_url': request.build_absolute_uri('/api/tracker/debug-ingest/')
        })
    
    try:
        # Log the raw request for debugging
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        print("=== DEBUG INGEST REQUEST ===")
        print(f"Content-Type: {request.content_type}")
        print(f"Request Data: {data}")
        print("=== END DEBUG ===")
        
        # Basic validation
        required_fields = ['tracking_id', 'visitor_id', 'session_id', 'event_type', 'timestamp']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return JsonResponse({
                'error': 'Missing required fields',
                'missing_fields': missing_fields,
                'received_data': data
            }, status=400)
        
        # Check if tracking_id exists
        try:
            website = Website.objects.get(tracking_id=data['tracking_id'])
        except Website.DoesNotExist:
            return JsonResponse({
                'error': 'Invalid tracking ID',
                'received_tracking_id': data['tracking_id'],
                'valid_tracking_ids': list(Website.objects.values_list('tracking_id', flat=True))
            }, status=400)
        
        # Success response
        return JsonResponse({
            'success': True,
            'message': 'Debug validation passed',
            'website': website.name,
            'event_type': data.get('event_type'),
            'received_fields': list(data.keys())
        }, status=200)
        
    except json.JSONDecodeError as e:
        return JsonResponse({
            'error': 'Invalid JSON',
            'details': str(e),
            'received_body': request.body.decode('utf-8', errors='replace')[:500]
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': 'Unexpected error',
            'details': str(e)
        }, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def comprehensive_analytics(request, website_id):
    """
    Get comprehensive analytics data for a website including:
    - Overview stats
    - Page views trend and top pages
    - Sessions count and duration
    - New vs returning users
    - Traffic sources
    - Device distribution
    - Browser distribution
    - Geography distribution
    """
    website = get_object_or_404(Website, id=website_id, owner=request.user)
    
    # Get date range from query parameters (default to last 30 days)
    days = int(request.GET.get('days', 30))
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    
    # Base querysets with date filtering
    pageviews_qs = PageView.objects.filter(
        website=website,
        timestamp__gte=start_date,
        timestamp__lte=end_date
    )
    
    sessions_qs = Session.objects.filter(
        website=website,
        started_at__gte=start_date,
        started_at__lte=end_date
    )
    
    visitors_qs = Visitor.objects.filter(
        website=website,
        first_seen__gte=start_date,
        first_seen__lte=end_date
    )
    
    custom_events_qs = CustomEvent.objects.filter(
        website=website,
        timestamp__gte=start_date,
        timestamp__lte=end_date
    )
    
    # 1. OVERVIEW STATS
    total_pageviews = pageviews_qs.count()
    total_sessions = sessions_qs.count()
    total_visitors = visitors_qs.count()
    total_custom_events = custom_events_qs.count()
    
    avg_session_duration = sessions_qs.aggregate(
        avg_duration=Avg('duration_seconds')
    )['avg_duration'] or 0
    
    # Bounce rate (sessions with only 1 pageview)
    bounced_sessions = sessions_qs.filter(page_views=1).count()
    bounce_rate = (bounced_sessions / total_sessions * 100) if total_sessions > 0 else 0
    
    # 2. PAGE VIEWS TREND AND TOP PAGES
    # Daily pageview trend
    pageviews_trend = (
        pageviews_qs
        .extra({'date': "date(timestamp)"})
        .values('date')
        .annotate(
            views=Count('id'),
            unique_views=Count('visitor', distinct=True)
        )
        .order_by('date')
    )
    
    # Top pages
    top_pages = (
        pageviews_qs
        .values('page_path', 'page_title')
        .annotate(
            views=Count('id'),
            unique_views=Count('visitor', distinct=True)
        )
        .order_by('-views')[:10]
    )
    
    # 3. SESSIONS TREND AND DURATION
    sessions_trend = (
    sessions_qs
    .annotate(date=TruncDate('started_at'))
    .values('date')
    .annotate(
        sessions=Count('id'),
        avg_duration=Avg('duration_seconds')
    )
    .order_by('date')   
    )
  
    # Session duration distribution
    duration_ranges = [
        ('0-30s', 0, 30),
        ('30s-1m', 31, 60),
        ('1-3m', 61, 180),
        ('3-10m', 181, 600),
        ('10m+', 601, float('inf'))
    ]
    
    duration_distribution = []
    for label, min_duration, max_duration in duration_ranges:
        if max_duration == float('inf'):
            count = sessions_qs.filter(duration_seconds__gte=min_duration).count()
        else:
            count = sessions_qs.filter(
                duration_seconds__gte=min_duration,
                duration_seconds__lte=max_duration
            ).count()
        
        percentage = (count / total_sessions * 100) if total_sessions > 0 else 0
        duration_distribution.append({
            'range': label,
            'count': count,
            'percentage': round(percentage, 1)
        })
    
    # 4. NEW VS RETURNING USERS
    # Users by type
    new_users = sessions_qs.filter(visitor__is_returning=False).values('visitor').distinct().count()
    returning_users = sessions_qs.filter(visitor__is_returning=True).values('visitor').distinct().count()
    # Daily new vs returning trend
    
    users_trend = (
    sessions_qs
    .annotate(date=TruncDate('started_at'))
    .values('date')
    .annotate(
        new_users=Count('visitor', filter=Q(visitor__is_returning=False), distinct=True),
        returning_users=Count('visitor', filter=Q(visitor__is_returning=True), distinct=True)
    )
    .order_by('date')
    )
    users_trend = list(users_trend)
    
    # 5. TRAFFIC SOURCES
    traffic_sources = (
        pageviews_qs
        .values('traffic_source')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    
    # UTM sources
    utm_sources = (
        pageviews_qs
        .exclude(utm_source='')
        .exclude(utm_source__isnull=True)
        .values('utm_source', 'utm_medium', 'utm_campaign')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    # Referrer domains
    referrer_domains = (
        pageviews_qs
        .exclude(referrer_domain='')
        .exclude(referrer_domain__isnull=True)
        .values('referrer_domain')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    # 6. DEVICE DISTRIBUTION
    device_stats = (
        sessions_qs
        .values('device_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    
    # OS distribution
    os_stats = (
        sessions_qs
        .values('os_name')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    # 7. BROWSER DISTRIBUTION
    browser_stats = (
        sessions_qs
        .values('browser_name', 'browser_version')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    # Browser families (without version)
    browser_families = (
        sessions_qs
        .values('browser_name')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    # 8. GEOGRAPHY DISTRIBUTION
    countries = (
        sessions_qs
        .exclude(country='')
        .exclude(country__isnull=True)
        .values('country')
        .annotate(count=Count('id'))
        .order_by('-count')[:20]
    )
    
    regions = (
        sessions_qs
        .exclude(region='')
        .exclude(region__isnull=True)
        .values('country', 'region')
        .annotate(count=Count('id'))
        .order_by('-count')[:15]
    )
    
    cities = (
        sessions_qs
        .exclude(city='')
        .exclude(city__isnull=True)
        .values('country', 'region', 'city')
        .annotate(count=Count('id'))
        .order_by('-count')[:15]
    )
    
    # 9. REAL-TIME DATA (last hour)
    last_hour = timezone.now() - timedelta(hours=1)
    realtime_data = {
        'active_users': sessions_qs.filter(started_at__gte=last_hour).count(),
        'current_pageviews': pageviews_qs.filter(timestamp__gte=last_hour).count(),
        'recent_events': custom_events_qs.filter(timestamp__gte=last_hour).count()
    }
    
    # 10. CUSTOM EVENTS
    popular_events = (
        custom_events_qs
        .values('event_name', 'event_category')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    # Calculate percentages for pie charts
    def add_percentages(data_list, count_field='count'):
        total = sum(item[count_field] for item in data_list)
        for item in data_list:
            item['percentage'] = round((item[count_field] / total * 100) if total > 0 else 0, 1)
        return data_list
    
    # Build comprehensive response
    analytics_data = {
        'website': {
            'id': str(website.id),
            'name': website.name,
            'domain': website.domain,
            'tracking_id': str(website.tracking_id)
        },
        'date_range': {
            'start': start_date.date().isoformat(),
            'end': end_date.date().isoformat(),
            'days': days
        },
        'overview': {
            'total_pageviews': total_pageviews,
            'total_sessions': total_sessions,
            'total_visitors': total_visitors,
            'total_custom_events': total_custom_events,
            'avg_session_duration': round(avg_session_duration, 2),
            'bounce_rate': round(bounce_rate, 1),
            'pages_per_session': round((total_pageviews / total_sessions) if total_sessions > 0 else 0, 2)
        },
        'pageviews': {
            'trend': list(pageviews_trend),
            'top_pages': list(top_pages)
        },
        'sessions': {
            'trend': list(sessions_trend),
            'duration_distribution': duration_distribution
        },
        'users': {
            'new_users': new_users,
            'returning_users': returning_users,
            'new_vs_returning_percentage': {
                'new': round((new_users / total_visitors * 100) if total_visitors > 0 else 0, 1),
                'returning': round((returning_users / total_visitors * 100) if total_visitors > 0 else 0, 1)
            },
            'trend': users_trend
        },
        'traffic_sources': {
            'sources': add_percentages(list(traffic_sources)),
            'utm_campaigns': list(utm_sources),
            'referrer_domains': list(referrer_domains)
        },
        'devices': {
            'device_types': add_percentages(list(device_stats)),
            'operating_systems': add_percentages(list(os_stats))
        },
        'browsers': {
            'browser_versions': list(browser_stats),
            'browser_families': add_percentages(list(browser_families))
        },
        'geography': {
            'countries': add_percentages(list(countries)),
            'regions': list(regions),
            'cities': list(cities)
        },
        'realtime': realtime_data,
        'custom_events': {
            'popular_events': list(popular_events)
        }
    }
    
    return Response(analytics_data)