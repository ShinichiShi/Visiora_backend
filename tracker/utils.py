from user_agents import parse
import requests
from urllib.parse import urlparse

def parse_user_agent(user_agent_string):
    """Parse user agent string to extract device/browser info"""
    user_agent = parse(user_agent_string)
    
    return {
        'device_type': get_device_type(user_agent),
        'browser_name': user_agent.browser.family,
        'browser_version': user_agent.browser.version_string,
        'os_name': user_agent.os.family,
        'os_version': user_agent.os.version_string,
    }

def get_device_type(user_agent):
    """Determine device type from user agent"""
    if user_agent.is_mobile:
        return 'mobile'
    elif user_agent.is_tablet:
        return 'tablet'
    elif user_agent.is_pc:
        return 'desktop'
    else:
        return 'unknown'

def get_traffic_source(referrer_url, utm_source, utm_medium):
    """Determine traffic source"""
    if utm_source:
        return utm_source
    
    if not referrer_url:
        return 'direct'
    
    try:
        domain = urlparse(referrer_url).netloc.lower()
        
        # Social media sources
        social_domains = [
            'facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com',
            'youtube.com', 'tiktok.com', 'pinterest.com', 'reddit.com'
        ]
        for social in social_domains:
            if social in domain:
                return 'social'
        
        # Search engines
        search_domains = [
            'google.com', 'bing.com', 'yahoo.com', 'duckduckgo.com',
            'baidu.com', 'yandex.com'
        ]
        for search in search_domains:
            if search in domain:
                return 'organic'
        
        return 'referral'
    except:
        return 'unknown'

def get_location_from_ip(ip_address):
    """Get location information from IP address"""
    # This is a basic implementation. In production, use a proper IP geolocation service
    # like MaxMind GeoIP2, IPStack, or similar
    try:
        # Using a free service for demo (replace with paid service in production)
        response = requests.get(f'http://ip-api.com/json/{ip_address}', timeout=2)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success':
                return {
                    'country': data.get('country'),
                    'region': data.get('regionName'),
                    'city': data.get('city'),
                    'latitude': data.get('lat'),
                    'longitude': data.get('lon'),
                }
    except:
        pass
    
    return {}
