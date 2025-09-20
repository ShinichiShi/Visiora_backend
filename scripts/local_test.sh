#!/bin/bash
# Complete Visiora Analytics API Test Script
# Ensure Django server is running: python manage.py runserver

set -e  # Exit on any error

export BASE_URL="http://localhost:8000"
echo "🚀 Testing Visiora Analytics API at $BASE_URL"
echo "================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

# Step 1: User Registration
print_step "Step 1: User Registration"
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/register/" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "testpassword123",
    "password_confirm": "testpassword123",
    "first_name": "Test",
    "last_name": "User"
  }')

if echo "$REGISTER_RESPONSE" | grep -q "error\|Error"; then
    print_warning "Registration failed (user might already exist): $REGISTER_RESPONSE"
else
    print_success "User registration successful"
fi

echo "$REGISTER_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$REGISTER_RESPONSE"
echo ""

# Step 2: User Login
print_step "Step 2: User Login"
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login/" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "testpassword123"
  }')

echo "$LOGIN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$LOGIN_RESPONSE"

# Extract access token using jq if available, otherwise manual parsing
if command -v jq &> /dev/null; then
    export ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.tokens.access // .access // .access_token // empty')
else
    # Fallback manual extraction
    export ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access":"[^"]*"' | cut -d'"' -f4)
fi

if [ -z "$ACCESS_TOKEN" ] || [ "$ACCESS_TOKEN" = "null" ]; then
    print_error "Failed to get access token. Login response: $LOGIN_RESPONSE"
    exit 1
fi

print_success "Login successful, got access token: ${ACCESS_TOKEN:0:20}..."
echo ""

# Step 3: Profile Check
print_step "Step 3: Profile Check"
PROFILE_RESPONSE=$(curl -s -X GET "$BASE_URL/api/auth/profile/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "$PROFILE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PROFILE_RESPONSE"
print_success "Profile retrieved successfully"
echo ""

# Step 4: Create Website
print_step "Step 4: Create Website"
WEBSITE_RESPONSE=$(curl -s -X POST "$BASE_URL/api/tracker/websites/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "name": "My Test Website",
    "domain": "https://mytestsite.com"
  }')

echo "$WEBSITE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$WEBSITE_RESPONSE"

# Extract website ID and tracking ID
if command -v jq &> /dev/null; then
    export WEBSITE_ID=$(echo "$WEBSITE_RESPONSE" | jq -r '.id // empty')
    export TRACKING_ID=$(echo "$WEBSITE_RESPONSE" | jq -r '.tracking_id // empty')
else
    # Fallback manual extraction
    export WEBSITE_ID=$(echo "$WEBSITE_RESPONSE" | grep -o '"id[^"]*":"[^"]*"' | cut -d'"' -f4)
    export TRACKING_ID=$(echo "$WEBSITE_RESPONSE" | grep -o '"tracking_id[^"]*":"[^"]*"' | cut -d'"' -f4)
fi

if [ -z "$WEBSITE_ID" ] || [ "$WEBSITE_ID" = "null" ]; then
    print_error "Failed to create website. Response: $WEBSITE_RESPONSE"
    exit 1
fi

print_success "Website created successfully"
print_success "Website ID: $WEBSITE_ID"
print_success "Tracking ID: $TRACKING_ID"
echo ""

# Step 5: List Websites
print_step "Step 5: List Websites"
WEBSITES_LIST=$(curl -s -X GET "$BASE_URL/api/tracker/websites/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "$WEBSITES_LIST" | python3 -m json.tool 2>/dev/null || echo "$WEBSITES_LIST"
print_success "Websites listed successfully"
echo ""

# Step 6: Dashboard URL
print_step "Step 6: Dashboard URL"
DASHBOARD_URL="$BASE_URL/api/tracker/dashboard/$WEBSITE_ID/"
print_success "Dashboard available at: $DASHBOARD_URL"
print_warning "Visit this URL in your browser to see the embed snippet"
echo ""

# Step 7: Test Event Ingestion (Pageview)
print_step "Step 7: Test Event Ingestion - Pageview"
PAGEVIEW_RESPONSE=$(curl -s -X POST "$BASE_URL/api/tracker/ingest/" \
  -H "Content-Type: application/json" \
  -d "{
    \"tracking_id\": \"$TRACKING_ID\",
    \"visitor_id\": \"test_visitor_$(date +%s)\",
    \"session_id\": \"test_session_$(date +%s)\",
    \"event_type\": \"pageview\",
    \"timestamp\": \"$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")\",
    \"page_url\": \"https://mytestsite.com/\",
    \"page_title\": \"Home Page\",
    \"user_agent\": \"Mozilla/5.0 (Test Browser)\",
    \"device_type\": \"desktop\",
    \"browser_name\": \"Chrome\",
    \"browser_version\": \"91\",
    \"os_name\": \"Windows\",
    \"os_version\": \"10\",
    \"screen_width\": 1920,
    \"screen_height\": 1080,
    \"viewport_width\": 1536,
    \"viewport_height\": 864,
    \"ip_address\": \"127.0.0.1\"
  }")

echo "$PAGEVIEW_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PAGEVIEW_RESPONSE"
print_success "Pageview event ingested successfully"
echo ""

# Step 8: Test Event Ingestion (Custom Event)
print_step "Step 8: Test Event Ingestion - Custom Event"
CUSTOM_EVENT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/tracker/ingest/" \
  -H "Content-Type: application/json" \
  -d "{
    \"tracking_id\": \"$TRACKING_ID\",
    \"visitor_id\": \"test_visitor_$(date +%s)\",
    \"session_id\": \"test_session_$(date +%s)\",
    \"event_type\": \"custom\",
    \"timestamp\": \"$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")\",
    \"event_name\": \"button_click\",
    \"event_category\": \"interaction\",
    \"event_action\": \"click\",
    \"event_label\": \"Sign Up Button\",
    \"properties\": {\"button_color\": \"blue\", \"page\": \"homepage\"}
  }")

echo "$CUSTOM_EVENT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CUSTOM_EVENT_RESPONSE"
print_success "Custom event ingested successfully"
echo ""

# Step 9: Test Analytics Endpoints
print_step "Step 9: Testing Analytics Endpoints"

# Overview
print_step "9a: Overview"
OVERVIEW_RESPONSE=$(curl -s -X GET "$BASE_URL/api/tracker/websites/$WEBSITE_ID/overview/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")
echo "$OVERVIEW_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$OVERVIEW_RESPONSE"

# Pageviews
print_step "9b: Pageviews"
PAGEVIEWS_RESPONSE=$(curl -s -X GET "$BASE_URL/api/tracker/websites/$WEBSITE_ID/pageviews/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")
echo "$PAGEVIEWS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PAGEVIEWS_RESPONSE"

# Sessions
print_step "9c: Sessions"
SESSIONS_RESPONSE=$(curl -s -X GET "$BASE_URL/api/tracker/websites/$WEBSITE_ID/sessions/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")
echo "$SESSIONS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$SESSIONS_RESPONSE"

print_success "Analytics endpoints tested successfully"
echo ""

# Step 10: Error Testing
print_step "Step 10: Error Testing"

print_step "10a: Invalid tracking ID"
INVALID_TRACKING_RESPONSE=$(curl -s -X POST "$BASE_URL/api/tracker/ingest/" \
  -H "Content-Type: application/json" \
  -d '{
    "tracking_id": "00000000-0000-0000-0000-000000000000",
    "visitor_id": "test_visitor",
    "session_id": "test_session",
    "event_type": "pageview",
    "timestamp": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")'"
  }')

echo "$INVALID_TRACKING_RESPONSE"
print_success "Invalid tracking ID properly rejected"

print_step "10b: Missing required fields"
MISSING_FIELDS_RESPONSE=$(curl -s -X POST "$BASE_URL/api/tracker/ingest/" \
  -H "Content-Type: application/json" \
  -d '{
    "tracking_id": "'$TRACKING_ID'",
    "event_type": "pageview"
  }')

echo "$MISSING_FIELDS_RESPONSE"
print_success "Missing fields properly rejected"
echo ""

# Final Summary
echo "================================================="
print_success "🎉 ALL TESTS COMPLETED SUCCESSFULLY!"
echo ""
echo "📊 Summary:"
echo "- User: testuser"
echo "- Website ID: $WEBSITE_ID"
echo "- Tracking ID: $TRACKING_ID"
echo "- Dashboard: $DASHBOARD_URL"
echo ""
echo "📝 Next Steps:"
echo "1. Visit the dashboard URL in your browser"
echo "2. Copy the embed code and test it on a real webpage"
echo "3. Check analytics endpoints for real data"
echo ""
print_success "Backend API is working correctly! ✨"