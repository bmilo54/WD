import requests
from django.core.management.base import BaseCommand
from apps.country.models import Country
from apps.sms_providers.models import SMSProvider, ProviderCountryMapping
from apps.users.models import UserConfig
from apps.jobs.models import AutomationJob
from core.services.sms_hub import PROVIDER_MAP

class Command(BaseCommand):
    help = 'Fetches all supported countries from a specific SMS provider via the Hub.'

    def add_arguments(self, parser):
        parser.add_argument('--provider', type=str, help='The slug of the provider to sync (e.g., hero-sms, claude-otp)')
        parser.add_argument('--api-key', type=str, default='DUMMY_KEY', help='API Key if required by the provider to fetch countries')
        parser.add_argument(
            '--no-prune', action='store_true',
            help="Don't remove mappings for this provider that the API no longer returns (e.g. after a "
                 "naming/ID scheme change upstream). By default a full sync is treated as authoritative "
                 "and stale mappings are cleaned up automatically.",
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be pruned without actually deleting anything.',
        )

    def handle(self, *args, **options):
        provider_slug = options['provider']
        api_key = options['api_key']
        prune = not options['no_prune']
        dry_run = options['dry_run']

        if not provider_slug:
            self.stdout.write(self.style.ERROR("Please specify a provider, e.g. --provider hero-sms"))
            self.stdout.write("Available providers: " + ", ".join(PROVIDER_MAP.keys()))
            return

        if provider_slug not in PROVIDER_MAP:
            self.stdout.write(self.style.ERROR(f"Provider {provider_slug} not found in the Hub."))
            return

        self.stdout.write(f"Fetching countries for {provider_slug}...")
        
        # 1. Get or Create the Provider Record in DB
        provider_obj, _ = SMSProvider.objects.get_or_create(
            slug=provider_slug,
            defaults={
                "name": provider_slug.replace("-", " ").title(),
                "is_active": True
            }
        )

        # 2. Instantiate the Provider Class from the Hub
        provider_class = PROVIDER_MAP[provider_slug]
        client = provider_class(api_key=api_key)

        # 3. Fetch countries using the new universal method!
        try:
            countries_data = client.get_countries()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch countries: {e}"))
            return

        created_count = 0
        mapping_count = 0
        seen_mapping_ids = set()

        for c_data in countries_data:
            c_id = c_data["provider_country_id"]
            name = c_data["name"]
            
            # Create or update the universal Country
            country_obj, created = Country.objects.update_or_create(
                name=name,
                defaults={'is_active': True}
            )

            # Create or update the Provider mapping
            mapping_obj, mapping_created = ProviderCountryMapping.objects.update_or_create(
                provider=provider_obj,
                country=country_obj,
                defaults={'provider_country_id': c_id}
            )
            seen_mapping_ids.add(mapping_obj.id)

            if created:
                created_count += 1
            if mapping_created:
                mapping_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully synced {len(countries_data)} countries for {provider_slug}.\n"
            f"Created {created_count} new Universal Countries.\n"
            f"Created {mapping_count} new Provider Mappings."
        ))

        if prune:
            self._prune_stale(provider_obj, seen_mapping_ids, dry_run)

    def _prune_stale(self, provider_obj, seen_mapping_ids, dry_run):
        """
        Removes mappings for this provider that weren't returned by the API in
        this run. Without this, entries left over from a previous naming/ID
        scheme (e.g. ClaudeOTP country names that didn't used to include the
        operator/price) just pile up forever, quietly reusing the same
        provider_country_id as a newer, differently-named entry.
        """
        stale = ProviderCountryMapping.objects.filter(provider=provider_obj).exclude(id__in=seen_mapping_ids).select_related('country')
        if not stale.exists():
            self.stdout.write("No stale mappings to prune.")
            return

        verb = "Would prune" if dry_run else "Pruning"
        self.stdout.write(self.style.WARNING(f"{verb} {stale.count()} stale mapping(s) no longer returned by the API:"))

        countries_to_check_for_orphan = []
        for mapping in stale:
            country = mapping.country
            used_by_config = UserConfig.objects.filter(default_country=country).exists()
            used_by_job = AutomationJob.objects.filter(country=country).exists()
            flag = ""
            if used_by_config or used_by_job:
                flag = "  [WARNING: still referenced by a saved UserConfig or AutomationJob - will fall back to that provider's other defaults once removed]"
            self.stdout.write(f"  - {country.name!r} (provider_country_id={mapping.provider_country_id}){flag}")
            countries_to_check_for_orphan.append(country.id)

        if dry_run:
            self.stdout.write("Dry run - nothing deleted.")
            return

        stale.delete()

        # A Country left with no provider mappings at all is just clutter -
        # remove it too, but only if nothing still points at it directly.
        orphan_countries = Country.objects.filter(id__in=countries_to_check_for_orphan, provider_mappings__isnull=True)
        orphan_countries = orphan_countries.exclude(id__in=UserConfig.objects.exclude(default_country=None).values('default_country_id'))
        orphan_countries = orphan_countries.exclude(id__in=AutomationJob.objects.exclude(country=None).values('country_id'))
        orphan_count = orphan_countries.count()
        if orphan_count:
            orphan_countries.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Pruned {stale.count()} stale mapping(s) and {orphan_count} now-orphaned Country row(s)."
        ))
