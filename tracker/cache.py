from django.core.cache import cache
from django.db.models import Count, Avg
from datetime import timedelta
from django.utils import timezone

class AnalyticsCache:
    """Caching layer for analytics queries"""
    
    def __init__(self):
        self.default_timeout = 300  # 5 minutes
    
    def get_overview_stats(self, website, start_date, end_date):
        """Get cached overview stats"""
        cache_key = f"overview:{website.id}:{start_date}:{end_date}"
        stats = cache.get(cache_key)
        
        if stats is None:
            # Calculate stats
            stats = self._calculate_overview_stats(website, start_date, end_date)
            cache.set(cache_key, stats, self.default_timeout)
        
        return stats
    
    def get_top_pages(self, website, start_date, end_date):
        """Get cached top pages"""
        cache_key = f"top_pages:{website.id}:{start_date}:{end_date}"
        pages = cache.get(cache_key)
        
        if pages is None:
            pages = self._calculate_top_pages(website, start_date, end_date)
            cache.set(cache_key, pages, self.default_timeout)
        
        return pages
    
    def invalidate_website_cache(self, website_id):
        """Invalidate all cache entries for a website"""
        # This would require a more sophisticated cache key pattern
        # For now, we can use cache versioning
        cache.set(f"cache_version:{website_id}", timezone.now().timestamp())
