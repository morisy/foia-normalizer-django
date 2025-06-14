from django.core.management.base import BaseCommand
from django.conf import settings
from normalizer.models import ColumnSynonym, StatusSynonym
from normalizer.utils import SynonymLoader
import os


class Command(BaseCommand):
    help = 'Load synonyms from text files into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--synonyms-path',
            type=str,
            help='Path to synonyms.txt file',
        )
        parser.add_argument(
            '--status-synonyms-path',
            type=str,
            help='Path to status_synonyms.txt file',
        )

    def handle(self, *args, **options):
        # Default paths - look in the parent directory of the Django project
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(settings.BASE_DIR)))
        
        synonyms_path = options.get('synonyms_path') or os.path.join(base_path, 'synonyms.txt')
        status_synonyms_path = options.get('status_synonyms_path') or os.path.join(base_path, 'status_synonyms.txt')
        
        self.stdout.write('Loading column synonyms...')
        if os.path.exists(synonyms_path):
            initial_count = ColumnSynonym.objects.count()
            SynonymLoader.load_synonyms_from_file(synonyms_path, ColumnSynonym)
            final_count = ColumnSynonym.objects.count()
            self.stdout.write(
                self.style.SUCCESS(
                    f'Loaded {final_count - initial_count} column synonyms from {synonyms_path}'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Column synonyms file not found: {synonyms_path}')
            )
        
        self.stdout.write('Loading status synonyms...')
        if os.path.exists(status_synonyms_path):
            initial_count = StatusSynonym.objects.count()
            SynonymLoader.load_synonyms_from_file(status_synonyms_path, StatusSynonym)
            final_count = StatusSynonym.objects.count()
            self.stdout.write(
                self.style.SUCCESS(
                    f'Loaded {final_count - initial_count} status synonyms from {status_synonyms_path}'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Status synonyms file not found: {status_synonyms_path}')
            )
        
        self.stdout.write(self.style.SUCCESS('Synonym loading complete!'))