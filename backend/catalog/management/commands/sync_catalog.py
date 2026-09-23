import json
from dataclasses import asdict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.index_sync import sync_catalog
from catalog.providers import get_catalog_provider
from config.observability import observe_latency, record_event, record_metric


class Command(BaseCommand):
    help = "Synchronize the complete catalog into the local deduplicated index"

    def add_arguments(self, parser):
        parser.add_argument("--max-pages", type=int, default=settings.CATALOG_SYNC_MAX_PAGES)
        parser.add_argument("--per-page", type=int, default=settings.CATALOG_SYNC_PER_PAGE)
        parser.add_argument(
            "--include-details",
            action="store_true",
            default=settings.CATALOG_SYNC_INCLUDE_DETAILS,
            help="Enrich every indexed item with its detail fields for semantic search",
        )

    def handle(self, *args, **options):
        provider = get_catalog_provider()
        result = sync_catalog(
            provider=provider,
            index_path=settings.CATALOG_INDEX_PATH,
            status_path=settings.CATALOG_SYNC_STATUS_PATH,
            max_pages=options["max_pages"],
            per_page=options["per_page"],
            include_details=options["include_details"],
        )
        record_metric("catalog_sync_runs_total")
        record_metric("catalog_sync_success_total" if result.success else "catalog_sync_failures_total")
        observe_latency("catalog_sync", result.duration_seconds * 1000)
        record_event(
            "catalog.sync.completed",
            success=result.success,
            stop_reason=result.stop_reason,
            pages=result.pages,
            products=result.products,
            errors=result.errors,
            duration_ms=round(result.duration_seconds * 1000, 3),
        )
        self.stdout.write(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
        if not result.success:
            raise CommandError(result.warning or f"Catalog synchronization failed: {result.stop_reason}")
