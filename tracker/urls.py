from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'websites', views.WebsiteViewSet, basename='websites')

urlpatterns = [
    path('', include(router.urls)),
    
    # Event ingestion
    path('ingest/', views.ingest_event, name='ingest_event'),
    path("websites/<uuid:website_id>/", views.website_detail, name="website_detail"),
    # Analytics endpoints
    path('websites/<uuid:website_id>/overview/', views.analytics_overview, name='analytics_overview'),
    path('websites/<uuid:website_id>/pageviews/', views.page_views_analytics, name='page_views_analytics'),
    path('websites/<uuid:website_id>/sessions/', views.sessions_analytics, name='sessions_analytics'),
    path('websites/<uuid:website_id>/users/', views.users_analytics, name='users_analytics'),
    path('websites/<uuid:website_id>/sources/', views.traffic_sources_analytics, name='traffic_sources_analytics'),
    path('websites/<uuid:website_id>/devices/', views.devices_analytics, name='devices_analytics'),
    path('websites/<uuid:website_id>/browsers/', views.browsers_analytics, name='browsers_analytics'),
    path('websites/<uuid:website_id>/geography/', views.geography_analytics, name='geography_analytics'),
]
