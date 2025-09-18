(function () {
    // === CONFIG ===
    const scriptTag = document.currentScript;
    const TRACKING_ID = scriptTag.getAttribute("data-tracking-id");
    const API_URL = scriptTag.getAttribute("data-api-url");
    const DEBUG = scriptTag.getAttribute("data-debug") === "true";

    if (!TRACKING_ID || !API_URL) {
        console.error("[Visiora] Missing tracking-id or api-url in script tag");
        return;
    }

    // === UTILITIES ===
    function logDebug(...args) {
        if (DEBUG) console.log("[Visiora]", ...args);
    }

    function generateId(key) {
        let id = localStorage.getItem(key);
        if (!id) {
            id = Math.random().toString(36).substring(2) + Date.now().toString(36);
            localStorage.setItem(key, id);
        }
        return id;
    }

    function getSessionId() {
        // Persist session until 30 minutes of inactivity
        const now = Date.now();
        let session = JSON.parse(sessionStorage.getItem("visiora_session"));
        if (!session || now - session.lastActivity > 30 * 60 * 1000) {
            session = { id: generateId("visiora_session_id"), lastActivity: now };
        }
        session.lastActivity = now;
        sessionStorage.setItem("visiora_session", JSON.stringify(session));
        return session.id;
    }

    function getClientInfo() {
        return {
            user_agent: navigator.userAgent,
            screen_width: window.screen.width,
            screen_height: window.screen.height,
            viewport_width: window.innerWidth,
            viewport_height: window.innerHeight,
        };
    }

    function sendEvent(eventType, payload) {
        const data = {
            tracking_id: TRACKING_ID,
            visitor_id: generateId("visiora_visitor_id"),
            session_id: getSessionId(),
            event_type: eventType,
            timestamp: new Date().toISOString(),
            ...getClientInfo(),
            ...payload,
        };

        logDebug("Sending event:", data);

        // Use sendBeacon if available for reliability
        const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
        if (navigator.sendBeacon) {
            navigator.sendBeacon(API_URL, blob);
        } else {
            fetch(API_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
                keepalive: true,
            }).catch((err) => console.error("[Visiora] Event failed:", err));
        }
    }

    // === AUTO TRACKING ===
    function trackPageView() {
        sendEvent("pageview", {
            page_url: window.location.href,
            page_title: document.title,
            referrer_url: document.referrer || null,
        });
    }

    // Track clicks
    function trackClicks() {
        document.addEventListener("click", (e) => {
            const target = e.target.closest("a, button, input[type=submit]");
            if (target) {
                sendEvent("custom", {
                    event_name: "click",
                    event_category: target.tagName.toLowerCase(),
                    event_label: target.innerText || target.value || target.href,
                });
            }
        });
    }

    // Track form submissions
    function trackForms() {
        document.addEventListener("submit", (e) => {
            const form = e.target;
            sendEvent("custom", {
                event_name: "form_submit",
                event_category: "form",
                event_label: form.getAttribute("name") || form.id || "unnamed_form",
            });
        });
    }

    // === PUBLIC API ===
    window.visiora = {
        track: function (eventName, props = {}) {
            sendEvent("custom", {
                event_name: eventName,
                ...props,
            });
        },
    };

    // === INIT ===
    logDebug("Visiora Analytics initialized with ID:", TRACKING_ID);
    trackPageView();
    trackClicks();
    trackForms();
})();
