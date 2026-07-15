"""Django management command to create the initial admin superuser.

Uses environment variables:
    ADMIN_EMAIL  – admin email address (default: admin@crestpointcredit.com)
    ADMIN_PASSWORD – admin password (default: Admin@12345)
"""

import os

from django.core.management.base import BaseCommand, CommandError

from ...models import User


class Command(BaseCommand):
    help = "Creates the initial admin superuser for CrestPoint Credit"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=os.environ.get("ADMIN_EMAIL", "admin@crestpointcredit.com"),
            help="Admin email address (default: ADMIN_EMAIL env var or admin@crestpointcredit.com)",
        )
        parser.add_argument(
            "--password",
            default=os.environ.get("ADMIN_PASSWORD", "Admin@18545"),
            help="Admin password (default: ADMIN_PASSWORD env var or Admin@12345)",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            default=True,
            help="Do not prompt for input (uses defaults/env vars)",
        )

    def handle(self, *args, **options):
        email = options["email"]
        password = options["password"]

        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Admin user with email '{email}' already exists. Skipping."
                )
            )
            return

        try:
            admin = User.objects.create_superuser(
                email=email,
                first_name="Admin",
                last_name="CrestPoint Credit",
                password=password,
                role="admin",
                is_staff=True,
                is_superuser=True,
                is_active=True,
                is_verified=True,
            )
            admin.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Admin user '{email}' created successfully."
                )
            )
        except Exception as exc:
            raise CommandError(f"Failed to create admin user: {exc}") from exc
