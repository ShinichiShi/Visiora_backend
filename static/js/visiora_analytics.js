/**
 * Visiora Analytics - Client-side tracking script
 * Embeddable web analytics tracking for websites
 * 
 * Usage: <script src="https://yourapi.com/static/js/visiora-analytics.js" 
 *                data-tracking-id="your-tracking-id" 
 *                data-api-url="https://yourapi.com/api/tracker/ingest/"
 *                data-debug="false"></script>
 */

(function() {
    'use strict';
    
    // Auto-detect script configuration from the script tag
    const getCurrentScript = () => {
        // For modern browsers
        if (document.currentScript) {
            return document.currentScript;
        }
        
        // Fallback for older browsers
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            if (scripts[i].src && scripts[i].src.includes('visiora_analytics')) {
                return scripts[i];
            }
        }
        
        // Final fallback - look for any script with data-tracking-id
        return document.querySelector('script[data-tracking-id]');
    };
    
    const script = getCurrentScript();
    if (!script) {
        console.warn('Visiora Analytics: Script tag not found');
        return;
    }
    
    // Extract configuration from script attributes
    const TRACKING_ID = script.getAttribute('data-tracking-id');
    const API_URL = script.getAttribute('data-api-url');
    const DEBUG = script.getAttribute('data-debug') === 'true';
    
    if (!TRACKING_ID || !API_URL) {
        console.error('Visiora Analytics: Missing required data-tracking-id or data-api-url attributes');
        return;
    }
    
    // Rest of your existing script remains the same...
    const CONFIG = {
        BATCH_SIZE: 10,
        SEND_INTERVAL: 5000,
        SESSION_TIMEOUT: 30 * 60 * 1000,
        HEARTBEAT_INTERVAL: 30000,
        SCROLL_THRESHOLD: 250,
        PERFORMANCE_SAMPLE_RATE: 0.1
    };
    // Global state
    let eventQueue = [];
    let isInitialized = false;
    let sessionStartTime = Date.now();
    let lastActivityTime = Date.now();
    let scrollDepthMarkers = {25: false, 50: false, 75: false, 100: false};
    let performanceTracked = false;
       
    // Debug logging
    function debug(...args) {
        if (DEBUG) {
            console.log('[Visiora Analytics]', ...args);
        }
    }
    
    // Utility functions
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }
    
    function getStorageItem(key, storage) {
        try {
            return storage.getItem(key);
        } catch (e) {
            debug('Storage access failed:', e);
            return null;
        }
    }
    
    function setStorageItem(key, value, storage) {
        try {
            storage.setItem(key, value);
        } catch (e) {
            debug('Storage write failed:', e);
        }
    }
    
    // Session and visitor management
    function getOrCreateVisitorId() {
        let visitorId = getStorageItem('visiora_visitor_id', localStorage);
        if (!visitorId) {
            visitorId = generateUUID();
            setStorageItem('visiora_visitor_id', visitorId, localStorage);
            debug('Created new visitor ID:', visitorId);
        }
        return visitorId;
    }
    
    function getOrCreateSessionId() {
        const now = Date.now();
        const sessionData = getStorageItem('visiora_session', sessionStorage);
        
        if (sessionData) {
            try {
                const parsed = JSON.parse(sessionData);
                if (now - parsed.lastActivity < CONFIG.SESSION_TIMEOUT) {
                    // Update last activity
                    parsed.lastActivity = now;
                    setStorageItem('visiora_session', JSON.stringify(parsed), sessionStorage);
                    debug('Continuing session:', parsed.sessionId);
                    return parsed.sessionId;
                }
            } catch (e) {
                debug('Invalid session data, creating new session');
            }
        }
        
        // Create new session
        const sessionId = generateUUID();
        const newSessionData = {
            sessionId: sessionId,
            startTime: now,
            lastActivity: now
        };
        setStorageItem('visiora_session', JSON.stringify(newSessionData), sessionStorage);
        debug('Created new session:', sessionId);
        return sessionId;
    }
    
    // Device and browser detection
    function getDeviceInfo() {
        const ua = navigator.userAgent;
        let deviceType = 'desktop';
        
        if (/tablet|ipad|playbook|silk/i.test(ua)) {
            deviceType = 'tablet';
        } else if (/mobile|iphone|ipod|android|blackberry|opera|mini|windows\sce|palm|smartphone|iemobile/i.test(ua)) {
            deviceType = 'mobile';
        }
        
        // Browser detection
        let browserName = 'unknown';
        let browserVersion = '';
        
        if (ua.indexOf('Firefox') > -1) {
            browserName = 'Firefox';
            browserVersion = ua.match(/Firefox\/([0-9]+)/)?.[1] || '';
        } else if (ua.indexOf('Chrome') > -1) {
            browserName = 'Chrome';
            browserVersion = ua.match(/Chrome\/([0-9]+)/)?.[1] || '';
        } else if (ua.indexOf('Safari') > -1) {
            browserName = 'Safari';
            browserVersion = ua.match(/Version\/([0-9]+)/)?.[1] || '';
        } else if (ua.indexOf('Edge') > -1) {
            browserName = 'Edge';
            browserVersion = ua.match(/Edge\/([0-9]+)/)?.[1] || '';
        }
        
        // OS detection
        let osName = 'unknown';
        let osVersion = '';
        
        if (ua.indexOf('Windows NT') > -1) {
            osName = 'Windows';
            osVersion = ua.match(/Windows NT ([0-9.]+)/)?.[1] || '';
        } else if (ua.indexOf('Mac OS X') > -1) {
            osName = 'macOS';
            osVersion = ua.match(/Mac OS X ([0-9_]+)/)?.[1]?.replace(/_/g, '.') || '';
        } else if (ua.indexOf('Linux') > -1) {
            osName = 'Linux';
        } else if (ua.indexOf('Android') > -1) {
            osName = 'Android';
            osVersion = ua.match(/Android ([0-9.]+)/)?.[1] || '';
        } else if (ua.indexOf('iOS') > -1) {
            osName = 'iOS';
            osVersion = ua.match(/OS ([0-9_]+)/)?.[1]?.replace(/_/g, '.') || '';
        }
        
        return {
            deviceType,
            browserName,
            browserVersion,
            osName,
            osVersion,
            userAgent: ua,
            screenWidth: screen.width,
            screenHeight: screen.height,
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
        };
    }
    
    // UTM and referrer parsing
    function parseUTMParams() {
        const params = new URLSearchParams(window.location.search);
        return {
            utm_source: params.get('utm_source'),
            utm_medium: params.get('utm_medium'),
            utm_campaign: params.get('utm_campaign'),
            utm_term: params.get('utm_term'),
            utm_content: params.get('utm_content')
        };
    }
    
    function getReferrerInfo() {
        const referrer = document.referrer;
        if (!referrer) return { referrer_url: null, referrer_domain: null, traffic_source: 'direct' };
        
        try {
            const referrerUrl = new URL(referrer);
            const currentDomain = window.location.hostname;
            const referrerDomain = referrerUrl.hostname;
            
            if (referrerDomain === currentDomain) {
                return { referrer_url: referrer, referrer_domain: referrerDomain, traffic_source: 'internal' };
            }
            
            // Categorize traffic source
            let trafficSource = 'referral';
            if (referrerDomain.includes('google.')) trafficSource = 'organic';
            else if (referrerDomain.includes('facebook.') || referrerDomain.includes('twitter.') || 
                     referrerDomain.includes('linkedin.') || referrerDomain.includes('instagram.')) {
                trafficSource = 'social';
            }
            
            return { referrer_url: referrer, referrer_domain: referrerDomain, traffic_source: trafficSource };
        } catch (e) {
            return { referrer_url: referrer, referrer_domain: null, traffic_source: 'referral' };
        }
    }
    
    // Event creation and queuing
    function createBaseEvent() {
        const deviceInfo = getDeviceInfo();
        const referrerInfo = getReferrerInfo();
        const utmParams = parseUTMParams();
        
        return {
            tracking_id: TRACKING_ID,
            visitor_id: getOrCreateVisitorId(),
            session_id: getOrCreateSessionId(),
            timestamp: new Date().toISOString(),
            page_url: window.location.href,
            page_title: document.title,
            page_path: window.location.pathname + window.location.search,
            ...deviceInfo,
            ...referrerInfo,
            ...utmParams
        };
    }
    
    function queueEvent(eventData) {
        eventQueue.push({
            ...createBaseEvent(),
            ...eventData
        });
        
        debug('Event queued:', eventData);
        
        if (eventQueue.length >= CONFIG.BATCH_SIZE) {
            sendEvents();
        }
    }
    
    // Event sending with beacon and fetch fallback
    function sendEvents() {
        if (eventQueue.length === 0) return;
        
        const events = [...eventQueue];
        eventQueue = [];
        
        const payload = JSON.stringify({ events });
        
        debug('Sending events:', events);
        
        // Try sendBeacon first (reliable for page unload)
        if (navigator.sendBeacon && navigator.sendBeacon(API_URL, new Blob([payload], {type: 'application/json'}))) {
            debug('Events sent via sendBeacon');
            return;
        }
        
        // Fallback to fetch
        fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: payload,
            keepalive: true
        }).then(response => {
            if (response.ok) {
                debug('Events sent via fetch');
            } else {
                debug('Failed to send events:', response.status);
                // Re-queue events on failure
                eventQueue.unshift(...events);
            }
        }).catch(error => {
            debug('Network error sending events:', error);
            // Re-queue events on error
            eventQueue.unshift(...events);
        });
    }
    
    // Scroll depth tracking
    function trackScrollDepth() {
        const scrollPercent = Math.round((window.scrollY + window.innerHeight) / document.body.scrollHeight * 100);
        
        for (const [threshold, tracked] of Object.entries(scrollDepthMarkers)) {
            if (scrollPercent >= parseInt(threshold) && !tracked) {
                scrollDepthMarkers[threshold] = true;
                queueEvent({
                    event_type: 'scroll_depth',
                    event_name: 'scroll_depth',
                    event_category: 'engagement',
                    event_action: 'scroll',
                    event_label: `${threshold}%`,
                    event_value: parseInt(threshold),
                    properties: { scroll_percent: scrollPercent }
                });
            }
        }
    }
    
    // Performance metrics tracking
    function trackPerformance() {
        if (performanceTracked || Math.random() > CONFIG.PERFORMANCE_SAMPLE_RATE) return;
        
        // Wait for load event
        if (document.readyState !== 'complete') {
            window.addEventListener('load', trackPerformance, { once: true });
            return;
        }
        
        performanceTracked = true;
        
        try {
            const navigation = performance.getEntriesByType('navigation')[0];
            if (navigation) {
                queueEvent({
                    event_type: 'performance',
                    event_name: 'page_performance',
                    event_category: 'performance',
                    properties: {
                        dns_time: Math.round(navigation.domainLookupEnd - navigation.domainLookupStart),
                        connect_time: Math.round(navigation.connectEnd - navigation.connectStart),
                        response_time: Math.round(navigation.responseEnd - navigation.requestStart),
                        dom_load_time: Math.round(navigation.domContentLoadedEventEnd - navigation.navigationStart),
                        load_time: Math.round(navigation.loadEventEnd - navigation.navigationStart)
                    }
                });
            }
        } catch (e) {
            debug('Performance tracking failed:', e);
        }
    }
    
    // Event listeners setup
    function setupEventListeners() {
        // Track clicks on links and buttons
        document.addEventListener('click', function(e) {
            if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON' || e.target.closest('a, button')) {
                const element = e.target.closest('a, button') || e.target;
                queueEvent({
                    event_type: 'click',
                    event_name: 'click',
                    event_category: 'interaction',
                    event_action: 'click',
                    event_label: element.textContent?.trim() || element.getAttribute('aria-label') || element.tagName.toLowerCase(),
                    properties: {
                        element_tag: element.tagName.toLowerCase(),
                        element_href: element.href || null,
                        element_text: element.textContent?.trim().substring(0, 100) || null
                    }
                });
            }
        });
        
        // Track form submissions
        document.addEventListener('submit', function(e) {
            const form = e.target;
            queueEvent({
                event_type: 'form_submit',
                event_name: 'form_submit',
                event_category: 'interaction',
                event_action: 'submit',
                event_label: form.getAttribute('name') || form.getAttribute('id') || 'unnamed_form',
                properties: {
                    form_action: form.action || null,
                    form_method: form.method || 'get'
                }
            });
        });
        
        // Track scroll depth
        let scrollTimeout;
        window.addEventListener('scroll', function() {
            clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(trackScrollDepth, 100);
        });
        
        // Track page visibility changes
        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                sendEvents(); // Send pending events when page becomes hidden
            }
        });
        
        // Send events before page unload
        window.addEventListener('beforeunload', function() {
            sendEvents();
        });
        
        // Heartbeat to keep session alive
        setInterval(function() {
            const now = Date.now();
            if (now - lastActivityTime < CONFIG.SESSION_TIMEOUT) {
                queueEvent({
                    event_type: 'heartbeat',
                    event_name: 'heartbeat',
                    event_category: 'system',
                    properties: { session_duration: now - sessionStartTime }
                });
            }
        }, CONFIG.HEARTBEAT_INTERVAL);
        
        // Update last activity time on user interaction
        ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'].forEach(event => {
            document.addEventListener(event, function() {
                lastActivityTime = Date.now();
            }, { passive: true });
        });
    }
    
    // Public API
    window.visiora = {
        /**
         * Track custom event
         * @param {string} eventName - Name of the event
         * @param {object} properties - Additional event properties
         */
        track: function(eventName, properties = {}) {
            queueEvent({
                event_type: 'custom',
                event_name: eventName,
                event_category: properties.category || 'custom',
                event_action: properties.action || eventName,
                event_label: properties.label || null,
                event_value: properties.value || null,
                properties: properties
            });
            debug('Custom event tracked:', eventName, properties);
        },
        
        /**
         * Identify user with additional traits
         * @param {string} userId - User identifier
         * @param {object} traits - User traits/properties
         */
        identify: function(userId, traits = {}) {
            queueEvent({
                event_type: 'identify',
                event_name: 'identify',
                event_category: 'user',
                properties: {
                    user_id: userId,
                    ...traits
                }
            });
            debug('User identified:', userId, traits);
        },
        
        /**
         * Manually send queued events
         */
        flush: function() {
            sendEvents();
        },
        
        /**
         * Get current visitor and session IDs
         */
        getIds: function() {
            return {
                visitorId: getOrCreateVisitorId(),
                sessionId: getOrCreateSessionId()
            };
        }
    };
    
    // Initialize tracking
    function initialize() {
        if (isInitialized) return;
        isInitialized = true;
        
        debug('Initializing Visiora Analytics', { trackingId: TRACKING_ID, apiUrl: API_URL });
        
        // Track initial pageview
        queueEvent({
            event_type: 'pageview',
            event_name: 'pageview',
            event_category: 'navigation'
        });
        
        // Setup event listeners
        setupEventListeners();
        
        // Track performance metrics
        trackPerformance();
        
        // Start periodic event sending
        setInterval(sendEvents, CONFIG.SEND_INTERVAL);
        
        debug('Visiora Analytics initialized');
    }
    
    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize);
    } else {
        initialize();
    }
    
})();