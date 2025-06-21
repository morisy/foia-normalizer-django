from django.core.management.base import BaseCommand
import subprocess
import sys
import os
from pathlib import Path


class Command(BaseCommand):
    help = 'Launch the Gradio interface for FOIA Log Normalizer'

    def add_arguments(self, parser):
        parser.add_argument(
            '--port',
            type=int,
            default=7860,
            help='Port to run Gradio on (default: 7860)',
        )
        parser.add_argument(
            '--share',
            action='store_true',
            help='Create a shareable public link',
        )
        parser.add_argument(
            '--no-share',
            action='store_true',
            help='Disable shareable link (local only)',
        )

    def handle(self, *args, **options):
        port = options['port']
        share = options['share'] and not options['no_share']
        
        self.stdout.write('🚀 Starting FOIA Log Normalizer Gradio Interface...')
        self.stdout.write(f'📡 Port: {port}')
        self.stdout.write(f'🌐 Shareable link: {"Yes" if share else "No"}')
        
        # Path to the Gradio app
        gradio_app_path = Path(__file__).parent.parent.parent.parent / 'gradio_app.py'
        
        if not gradio_app_path.exists():
            self.stdout.write(
                self.style.ERROR('❌ gradio_app.py not found. Please ensure it exists in the project root.')
            )
            return
        
        # Set environment variables for the Gradio app
        env = os.environ.copy()
        env['GRADIO_PORT'] = str(port)
        env['GRADIO_SHARE'] = str(share).lower()
        
        try:
            # Run the Gradio app
            subprocess.run([
                sys.executable, 
                str(gradio_app_path)
            ], env=env, check=True)
            
        except KeyboardInterrupt:
            self.stdout.write('\n👋 Gradio interface stopped.')
        except subprocess.CalledProcessError as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error running Gradio app: {e}')
            )