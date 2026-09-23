import json
from dataclasses import asdict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.index_sync import sync_catalog
from catalog.providers import get_catalog_provider


class Command(BaseCommand):
    help = "Synchronize the complete catalog into the local deduplicated index"

    def add_arguments(self, parser):
        parser.add_argument("--max-pages", type=int, default=settings.CATALOG_SYNC_MAX_PAGES)
        parser.add_argument("--per-page", type=int, default=settings.CATALOG_SYNC_PER_PAGE)

    def handle(self, *args, **options):
        provider = get_catalog_provider()
        result = sync_catalog(
            provider=provider,
            index_path=settings.CATALOG_INDEX_PATH,
            status_path=settings.CATALOG_SYNC_STATUS_PATH,
            max_pages=options["max_pages"],
            per_page=options["per_page"],
        )
        self.stdout.write(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
        if not result.success:
            raise CommandError(result.warning or f"Catalog synchronization failed: {result.stop_reason}")
