"""Management command to seed initial biller categories."""

from django.core.management.base import BaseCommand

from crestpoint_credit.bills.models import BillerCategory

INITIAL_CATEGORIES = [
    {"name": "Utilities", "icon": "zap"},
    {"name": "TV Licence", "icon": "tv"},
    {"name": "Internet", "icon": "wifi"},
    {"name": "Insurance", "icon": "shield"},
    {"name": "Loans", "icon": "banknote"},
    {"name": "Taxes", "icon": "file-text"},
    {"name": "Subscriptions", "icon": "repeat"},
    {"name": "Other", "icon": "more-horizontal"},
]


class Command(BaseCommand):
    help = "Seed the database with initial biller categories (Utilities, TV Licence, Internet, etc.)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing categories before seeding.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            count = BillerCategory.objects.count()
            BillerCategory.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {count} existing categor(ies)."))

        created_count = 0
        updated_count = 0

        for cat_data in INITIAL_CATEGORIES:
            category, created = BillerCategory.objects.update_or_create(
                name=cat_data["name"],
                defaults={
                    "icon": cat_data["icon"],
                    "is_active": True,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded biller categories: {created_count} created, {updated_count} updated."
            )
        )