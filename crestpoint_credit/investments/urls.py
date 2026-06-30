from django.urls import path

from . import views

urlpatterns = [
    path("market/", views.MarketListView.as_view(), name="market-list"),
    path("market/<int:pk>/", views.StockDetailView.as_view(), name="stock-detail"),
    path("account/", views.InvestmentAccountView.as_view(), name="investment-account"),
    path("portfolio/", views.PortfolioListView.as_view(), name="portfolio-list"),
    path("buy/", views.BuyStockView.as_view(), name="buy-stock"),
    path("sell/", views.SellStockView.as_view(), name="sell-stock"),
    path("history/", views.InvestmentHistoryView.as_view(), name="investment-history"),
]