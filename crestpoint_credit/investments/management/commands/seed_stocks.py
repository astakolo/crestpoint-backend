"""Management command to seed mock stock data."""

from decimal import Decimal

from django.core.management.base import BaseCommand

from crestpoint_credit.investments.models import Stock


MOCK_STOCKS = [
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "current_price": Decimal("198.11"),
        "previous_close": Decimal("195.83"),
        "change_percent": Decimal("1.1640"),
        "market_cap": Decimal("3080000000000.00"),
        "volume": 54321678,
    },
    {
        "symbol": "GOOGL",
        "name": "Alphabet Inc.",
        "current_price": Decimal("176.42"),
        "previous_close": Decimal("174.91"),
        "change_percent": Decimal("0.8630"),
        "market_cap": Decimal("2180000000000.00"),
        "volume": 23456789,
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft Corporation",
        "current_price": Decimal("448.20"),
        "previous_close": Decimal("445.52"),
        "change_percent": Decimal("0.6015"),
        "market_cap": Decimal("3330000000000.00"),
        "volume": 19876543,
    },
    {
        "symbol": "AMZN",
        "name": "Amazon.com, Inc.",
        "current_price": Decimal("201.35"),
        "previous_close": Decimal("198.67"),
        "change_percent": Decimal("1.3490"),
        "market_cap": Decimal("2090000000000.00"),
        "volume": 45678901,
    },
    {
        "symbol": "TSLA",
        "name": "Tesla, Inc.",
        "current_price": Decimal("248.91"),
        "previous_close": Decimal("252.30"),
        "change_percent": Decimal("-1.3430"),
        "market_cap": Decimal("792000000000.00"),
        "volume": 87654321,
    },
    {
        "symbol": "NVDA",
        "name": "NVIDIA Corporation",
        "current_price": Decimal("140.76"),
        "previous_close": Decimal("137.42"),
        "change_percent": Decimal("2.4300"),
        "market_cap": Decimal("3450000000000.00"),
        "volume": 34567890,
    },
    {
        "symbol": "META",
        "name": "Meta Platforms, Inc.",
        "current_price": Decimal("598.23"),
        "previous_close": Decimal("590.11"),
        "change_percent": Decimal("1.3760"),
        "market_cap": Decimal("1520000000000.00"),
        "volume": 16543210,
    },
    {
        "symbol": "NFLX",
        "name": "Netflix, Inc.",
        "current_price": Decimal("1012.45"),
        "previous_close": Decimal("1005.33"),
        "change_percent": Decimal("0.7080"),
        "market_cap": Decimal("438000000000.00"),
        "volume": 7654321,
    },
]


class Command(BaseCommand):
    help = "Seed the database with mock stock data (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, NFLX)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing stock data before seeding.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            count = Stock.objects.count()
            Stock.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {count} existing stock(s)."))

        created_count = 0
        updated_count = 0

        for stock_data in MOCK_STOCKS:
            stock, created = Stock.objects.update_or_create(
                symbol=stock_data["symbol"],
                defaults={
                    "name": stock_data["name"],
                    "current_price": stock_data["current_price"],
                    "previous_close": stock_data["previous_close"],
                    "change_percent": stock_data["change_percent"],
                    "market_cap": stock_data["market_cap"],
                    "volume": stock_data["volume"],
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded stocks: {created_count} created, {updated_count} updated."
            )
        )