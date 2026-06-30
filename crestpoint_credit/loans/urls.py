from django.urls import path

from . import views

urlpatterns = [
    path("types/", views.LoanTypesListView.as_view(), name="loan-types-list"),
    path("apply/", views.LoanApplicationCreateView.as_view(), name="loan-application-create"),
    path("applications/", views.LoanApplicationListView.as_view(), name="loan-application-list"),
    path("applications/<int:pk>/", views.LoanApplicationDetailView.as_view(), name="loan-application-detail"),
    path("", views.LoanListView.as_view(), name="loan-list"),
    path("<int:pk>/", views.LoanDetailView.as_view(), name="loan-detail"),
    path("<int:pk>/repay/", views.LoanRepaymentCreateView.as_view(), name="loan-repayment-create"),
    # Admin
    path("admin/applications/", views.AdminLoanApplicationListView.as_view(), name="admin-loan-application-list"),
    path("admin/applications/<int:pk>/review/", views.AdminReviewLoanApplicationView.as_view(), name="admin-review-loan-application"),
    path("admin/", views.AdminLoanListView.as_view(), name="admin-loan-list"),
]