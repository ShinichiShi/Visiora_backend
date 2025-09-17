from django.core.management.base import BaseCommand
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from analytics.models import Website, PageView, Session, Visitor, DailyStats

class Command(BaseCommand):
    help = 'Aggregate daily statistics for all websites'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Date to aggregate (YYYY-MM-DD format). Defaults to yesterday.',
        )
    
    def handle(self, *args, **options):
        if options['date']:
            from datetime import datetime
            target_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
        else:
            target_date = (timezone.now() - timedelta(days=1)).date()
        
        self.stdout.write(f'Aggregating stats for {target_date}')
        
        websites = Website.objects.filter(is_active=True)
        
        for website in websites:
            self.aggregate_website_stats(website, target_date)
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully aggregated stats for {websites.count()} websites')
        )
    
    def aggregate_website_stats(self, website, date):
        # Page views
        page_views = PageView.objects.filter(
            website=website,
            timestamp__date=date
        ).count()
        
        unique_page_views = PageView.objects.filter(
            website=website,
            timestamp__date=date
        ).values('page_path').distinct().count()
        
        # Sessions
        sessions_qs = Session.objects.filter(
            website=website,
            started_at__date=date
        )
        
        sessions_count = sessions_qs.count()
        avg_duration = sessions_qs.aggregate(
            avg=Avg('duration_seconds')
        )['avg'] or 0.0
        
        bounce_sessions = sessions_qs.filter(page_views=1).count()
        bounce_rate = (bounce_sessions / sessions_count * 100) if sessions_count > 0 else 0.0
        
        # Unique visitors
        unique_visitors = Visitor.objects.filter(
            website=website,
            first_seen__date=date
        ).count()
        
        new_visitors = Visitor.objects.filter(
            website=website,
            first_seen__date=date,
            is_returning=False
        ).count()
        
        returning_visitors = unique_visitors - new_visitors
        
        # Create or update daily stats
        daily_stats, created = DailyStats.objects.get_or_create(
            website=website,
            date=date,
            defaults={
                'page_views': page_views,
                'unique_page_views': unique_page_views,
                'sessions': sessions_count,
                'avg_session_duration': avg_duration,
                'bounce_rate': bounce_rate,
                'unique_visitors': unique_visitors,
                'new_visitors': new_visitors,
                'returning_visitors': returning_visitors,
            }
        )
        
        if not created:
            daily_stats.page_views = page_views
            daily_stats.unique_page_views = unique_page_views
            daily_stats.sessions = sessions_count
            daily_stats.avg_session_duration = avg_duration
            daily_stats.bounce_rate = bounce_rate
            daily_stats.unique_visitors = unique_visitors
            daily_stats.new_visitors = new_visitors
            daily_stats.returning_visitors = returning_visitors
            daily_stats.save()
