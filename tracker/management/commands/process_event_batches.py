from django.core.management.base import BaseCommand
from tracker.batch_processor import BatchEventProcessor

class Command(BaseCommand):
    help = 'Process queued analytics events in batches'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--continuous',
            action='store_true',
            help='Run continuously, processing batches every few seconds',
        )
    
    def handle(self, *args, **options):
        processor = BatchEventProcessor()
        
        if options['continuous']:
            import time
            self.stdout.write("Starting continuous batch processing...")
            while True:
                try:
                    processor.process_batch()
                    time.sleep(5)  # Process every 5 seconds
                except KeyboardInterrupt:
                    self.stdout.write("Stopping batch processor...")
                    break
                except Exception as e:
                    self.stderr.write(f"Error in batch processing: {e}")
                    time.sleep(10)
        else:
            processor.process_batch()
            self.stdout.write("Batch processing completed")
