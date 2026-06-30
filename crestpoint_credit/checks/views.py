import logging

from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.cache import never_cache
from rest_framework import status, generics, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crestpoint_credit.security.permissions import IsAdminRole
from .models import CheckDeposit, CheckDepositStatus
from .serializers import (
    CheckDepositCreateSerializer,
    CheckDepositSerializer,
    CheckDepositDetailSerializer,
    CheckDepositAdminSerializer,
    AdminProcessCheckDepositSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User-facing views
# ---------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class CheckDepositCreateView(APIView):
    """
    POST /checks/deposit/
    Upload check images for deposit (multipart/form-data).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckDepositCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        account = serializer._account
        data = serializer.validated_data

        deposit = CheckDeposit.objects.create(
            user=request.user,
            account=account,
            check_number=data.get("check_number", ""),
            amount=data["amount"],
            front_image=data["front_image"],
            back_image=data["back_image"],
            status=CheckDepositStatus.PENDING,
        )

        logger.info(
            "Check deposit %s submitted by user %s for %s",
            deposit.reference,
            request.user.email,
            data["amount"],
        )

        return Response(
            CheckDepositSerializer(deposit).data,
            status=status.HTTP_201_CREATED,
        )


class CheckDepositListView(generics.ListAPIView):
    """
    GET /checks/
    List the authenticated user's check deposits.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CheckDepositSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return CheckDeposit.objects.filter(
            user=self.request.user
        ).select_related("account")


class CheckDepositDetailView(generics.RetrieveAPIView):
    """
    GET /checks/<pk>/
    Retrieve a single check deposit (own deposits only).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CheckDepositDetailSerializer

    def get_queryset(self):
        return CheckDeposit.objects.filter(
            user=self.request.user
        ).select_related("account")


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------


class AdminCheckDepositListView(generics.ListAPIView):
    """
    GET /checks/admin/
    Admin view: list all check deposits.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = CheckDepositAdminSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["user__email", "reference", "check_number"]
    ordering_fields = ["created_at", "amount", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = CheckDeposit.objects.select_related("user", "account")

        dep_status = self.request.query_params.get("status")
        if dep_status:
            qs = qs.filter(status=dep_status)

        return qs


@method_decorator(never_cache, name="dispatch")
class AdminProcessCheckDepositView(APIView):
    """
    POST /checks/admin/<pk>/process/
    Admin approves or rejects a check deposit.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        try:
            deposit = CheckDeposit.objects.select_related("account", "user").get(pk=pk)
        except CheckDeposit.DoesNotExist:
            return Response(
                {"detail": "Check deposit not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if deposit.status != CheckDepositStatus.PENDING:
            return Response(
                {"detail": f"Check deposit is already {deposit.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminProcessCheckDepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]

        if action == "reject":
            deposit.status = CheckDepositStatus.REJECTED
            deposit.failure_reason = serializer.validated_data["rejection_reason"]
            deposit.processed_at = timezone.now()
            deposit.save(
                update_fields=["status", "failure_reason", "processed_at", "updated_at"]
            )

            logger.info(
                "Check deposit %s rejected by admin %s",
                deposit.reference,
                request.user.email,
            )

            return Response(
                CheckDepositAdminSerializer(deposit).data,
                status=status.HTTP_200_OK,
            )

        # Approve: credit the bank account
        deposit.status = CheckDepositStatus.COMPLETED
        deposit.processed_at = timezone.now()

        account = deposit.account
        account.balance += deposit.amount
        account.save(update_fields=["balance", "updated_at"])

        deposit.save(
            update_fields=["status", "processed_at", "updated_at"]
        )

        logger.info(
            "Check deposit %s approved by admin %s. %s credited to account %s.",
            deposit.reference,
            request.user.email,
            deposit.amount,
            account.account_number,
        )

        return Response(
            CheckDepositAdminSerializer(deposit).data,
            status=status.HTTP_200_OK,
        )