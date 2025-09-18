from django.core.management.base import BaseCommand
from tracker.monitoring import WebsiteMonitor
from django.utils import timezone

class Command(BaseCommand):
    help = 'Monitor websites for analytics and health'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--continuous',
            action='store_true',
            help='Run continuously',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=300,
            help='Check interval in seconds (default: 300)',
        )
    
    def handle(self, *args, **options):
        monitor = WebsiteMonitor()
        
        if options['continuous']:
            import time
            self.stdout.write("Starting continuous website monitoring...")
            while True:
                try:
                    monitor.monitor_all_websites()
                    self.stdout.write(f"Monitoring check completed at {timezone.now()}")
                    time.sleep(options['interval'])
                except KeyboardInterrupt:
                    self.stdout.write("Stopping website monitor...")
                    break
                except Exception as e:
                    self.stderr.write(f"Error in monitoring: {e}")
                    time.sleep(60)
        else:
            monitor.monitor_all_websites()
            self.stdout.write("Website monitoring completed")
