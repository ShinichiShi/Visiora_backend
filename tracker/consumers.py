import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache

class AnalyticsConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.website_id = self.scope['url_route']['kwargs']['website_id']
        self.room_group_name = f'analytics_{self.website_id}'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def analytics_update(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'analytics_update',
            'data': event['data']
        }))
