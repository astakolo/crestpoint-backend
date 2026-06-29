import logging

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crestpoint_credit.security.throttling import BurstRateThrottle, LoginRateThrottle, TransactionRateThrottle
from .models import BankAccount, KYCDocument, User
from .permissions import (
    IsAccountOwner,
    IsAdmin,
    IsAdminOrSupport,
    IsKYCPending,
)
from .serializers import (
    AdminNotificationSerializer,
    BalanceAdjustmentSerializer,
    BankAccountDetailSerializer,
    BankAccountSerializer,
    BatchActionSerializer,
    ChangePasswordSerializer,
    CreateAccountSerializer,
    KYCDocumentSerializer,
    KYCReviewSerializer,
    RegisterSerializer,
    UserAdminSerializer,
    UserSerializer,
)

logger = logging.getLogger("crestpoint_credit")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class RegisterView(APIView):
    """Create a new user account.

    On success the response includes user data and a pair of JWT tokens.
    A verification email is enqueued asynchronously.
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # --- Generate JWT tokens ---
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)

        # --- Enqueue verification email (fire-and-forget) ---
        try:
            from crestpoint_credit.notifications.tasks import send_verification_email

            send_verification_email.delay(user.id)
        except Exception:
            logger.exception("Failed to enqueue verification email for user %s", user.email)

        return Response(
            {
                "message": "Registration successful. Please verify your email.",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class UserDetailView(RetrieveUpdateAPIView):
    """Retrieve or update the authenticated user's own profile."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return UserSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Change Password
# ---------------------------------------------------------------------------


class ChangePasswordView(APIView):
    """Allow an authenticated user to change their password.

    On success all existing refresh tokens are blacklisted.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [BurstRateThrottle]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # --- Blacklist all existing refresh tokens ---
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                OutstandingToken,
            )

            tokens = OutstandingToken.objects.filter(user=request.user)
            for token in tokens:
                try:
                    token.blacklistedtoken  # noqa: B018 – access related to check existence
                except Exception:
                    pass
            # Revoke all by deleting outstanding tokens for this user
            tokens.delete()
            logger.info("All tokens blacklisted for user %s", request.user.email)
        except Exception:
            logger.exception("Failed to blacklist tokens for user %s", request.user.email)

        return Response(
            {"message": "Password changed successfully."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Bank Account
# ---------------------------------------------------------------------------


class BankAccountViewSet(viewsets.ModelViewSet):
    """ViewSet for managing the authenticated user's bank accounts.

    * ``list`` / ``retrieve`` – restricted to the account owner.
    * ``create`` – uses :class:`CreateAccountSerializer`.
    * ``freeze`` / ``unfreeze`` – admin/support only.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [TransactionRateThrottle]

    def get_queryset(self):
        """Non-admin users only see their own accounts."""
        user = self.request.user
        if user.role in ("admin", "support"):
            return BankAccount.objects.select_related("user").all()
        return BankAccount.objects.filter(user=user).select_related("user")

    def get_serializer_class(self):
        if self.action == "create":
            return CreateAccountSerializer
        if self.action == "retrieve":
            return BankAccountDetailSerializer
        return BankAccountSerializer

    def get_permissions(self):
        if self.action in ("freeze", "unfreeze"):
            return [IsAuthenticated(), IsAdminOrSupport()]
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated(), IsAccountOwner()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save()

    # ----- Custom actions -----

    @action(detail=True, methods=["post"])
    def freeze(self, request, pk=None):
        """Freeze a bank account. Admin/support only."""
        account = self.get_object()
        if account.is_frozen:
            return Response(
                {"message": "Account is already frozen."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        account.is_frozen = True
        account.save(update_fields=["is_frozen", "updated_at"])
        logger.info("Account %s frozen by %s", account.account_number, request.user.email)
        return Response({"message": "Account frozen successfully."})

    @action(detail=True, methods=["post"])
    def unfreeze(self, request, pk=None):
        """Unfreeze a bank account. Admin/support only."""
        account = self.get_object()
        if not account.is_frozen:
            return Response(
                {"message": "Account is not frozen."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        account.is_frozen = False
        account.save(update_fields=["is_frozen", "updated_at"])
        logger.info("Account %s unfrozen by %s", account.account_number, request.user.email)
        return Response({"message": "Account unfrozen successfully."})




# ---------------------------------------------------------------------------
# KYC Upload
# ---------------------------------------------------------------------------


class KYCUploadView(CreateAPIView):
    """Upload a KYC document for the authenticated user.

    * User can only have one pending KYC at a time.
    * User must not already have an approved KYC.
    """

    serializer_class = KYCDocumentSerializer
    permission_classes = [IsAuthenticated, IsKYCPending]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        # If the user has a rejected KYC, delete it before creating a new one
        user = self.request.user
        if hasattr(user, "kyc_document"):
            old_kyc = user.kyc_document
            old_kyc.delete()
        serializer.save(user=user)


# ---------------------------------------------------------------------------
# KYC Review (Admin / Support)
# ---------------------------------------------------------------------------


class KYCReviewView(APIView):
    """Approve or reject a KYC document.

    Restricted to admin and support roles.
    """

    permission_classes = [IsAuthenticated, IsAdminOrSupport]

    def post(self, request):
        serializer = KYCReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        kyc_id = request.data.get("kyc_id")
        if not kyc_id:
            return Response(
                {"error": "kyc_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            kyc = KYCDocument.objects.select_related("user").get(pk=kyc_id)
        except KYCDocument.DoesNotExist:
            return Response(
                {"error": "KYC document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        new_status = serializer.validated_data["status"]
        rejection_reason = serializer.validated_data.get("rejection_reason", "")

        kyc.status = new_status
        kyc.reviewed_by = request.user
        kyc.reviewed_at = timezone.now()
        kyc.rejection_reason = rejection_reason
        kyc.save()

        # Log the review action
        logger.info(
            "KYC document %d for user %s reviewed by %s – status: %s",
            kyc.id,
            kyc.user.email,
            request.user.email,
            new_status,
        )

        # Send notification to user about KYC decision
        try:
            from crestpoint_credit.notifications.services import NotificationService
            NotificationService.send_kyc_notification(
                kyc.user, new_status, rejection_reason
            )
        except Exception:
            logger.exception("Failed to send KYC notification for user %s", kyc.user.email)

        return Response(
            {
                "message": f"KYC document {new_status}.",
                "kyc_id": kyc.id,
                "status": new_status,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Admin User Management
# ---------------------------------------------------------------------------


class AdminUserViewSet(viewsets.ModelViewSet):
    """Full CRUD for admin to manage users.

    Additional actions: ``lock_user``, ``unlock_user``, ``verify_user``.
    """

    queryset = User.objects.all().order_by("-id")
    serializer_class = UserAdminSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_serializer_class(self):
        return UserAdminSerializer

    # ----- Custom actions -----

    @action(detail=True, methods=["post"])
    def lock_user(self, request, pk=None):
        """Lock a user account."""
        user = self.get_object()
        minutes = request.data.get("minutes", None)
        user.lock_account(minutes=minutes)
        logger.info("User %s locked by admin %s", user.email, request.user.email)
        return Response({"message": f"User {user.email} has been locked."})

    @action(detail=True, methods=["post"])
    def unlock_user(self, request, pk=None):
        """Unlock a user account."""
        user = self.get_object()
        user.unlock_account()
        logger.info("User %s unlocked by admin %s", user.email, request.user.email)
        return Response({"message": f"User {user.email} has been unlocked."})

    @action(detail=True, methods=["post"])
    def verify_user(self, request, pk=None):
        """Manually verify a user's email."""
        user = self.get_object()
        user.is_verified = True
        user.save(update_fields=["is_verified", "updated_at"])
        logger.info("User %s verified by admin %s", user.email, request.user.email)
        return Response({"message": f"User {user.email} has been verified."})

    @action(detail=True, methods=["post"])
    def adjust_balance(self, request, pk=None):
        """Adjust a user's bank account balance.

        Accepts ``account_id``, ``amount`` (positive=credit, negative=debit),
        and ``reason``.  Creates a corresponding transaction record for
        audit trail.
        """
        user = self.get_object()
        serializer = BalanceAdjustmentSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        account = serializer._account
        if account.user_id != user.id:
            return Response(
                {"error": "This account does not belong to this user."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = serializer.validated_data["amount"]
        reason = serializer.validated_data["reason"]

        from crestpoint_credit.transactions.services import execute_deposit, execute_withdrawal

        admin_tag = f"[Admin {request.user.email}] "
        description = f"{admin_tag}{reason}"

        try:
            if amount > 0:
                txn = execute_deposit(account, amount, description)
            else:
                txn = execute_withdrawal(account, abs(amount), description)
        except Exception as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Balance adjusted for account %s by %s: %s%s (reason: %s)",
            account.account_number,
            request.user.email,
            "+" if amount > 0 else "",
            amount,
            reason,
        )

        from crestpoint_credit.transactions.serializers import TransactionSerializer
        return Response(
            {
                "message": f"Balance adjusted by {amount:+.2f}",
                "transaction": TransactionSerializer(txn).data,
            }
        )

    @action(detail=False, methods=["post"])
    def batch_lock(self, request):
        """Lock multiple user accounts at once."""
        serializer = BatchActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_ids = serializer.validated_data["user_ids"]

        users = User.objects.filter(id__in=user_ids)
        locked_count = 0
        for u in users:
            u.lock_account()
            locked_count += 1

        logger.info("Batch lock: %d users locked by %s", locked_count, request.user.email)
        return Response({"message": f"{locked_count} user(s) locked."})

    @action(detail=False, methods=["post"])
    def batch_unlock(self, request):
        """Unlock multiple user accounts at once."""
        serializer = BatchActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_ids = serializer.validated_data["user_ids"]

        users = User.objects.filter(id__in=user_ids)
        unlocked_count = 0
        for u in users:
            u.unlock_account()
            unlocked_count += 1

        logger.info("Batch unlock: %d users unlocked by %s", unlocked_count, request.user.email)
        return Response({"message": f"{unlocked_count} user(s) unlocked."})


# ---------------------------------------------------------------------------
# Admin Send Notification
# ---------------------------------------------------------------------------


class AdminSendNotificationView(APIView):
    """Allow admin to send notifications to one or more users."""

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        serializer = AdminNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_ids = serializer.validated_data["user_ids"]
        title = serializer.validated_data["title"]
        message = serializer.validated_data["message"]
        notif_type = serializer.validated_data["notification_type"]

        sent_count = 0
        for uid in user_ids:
            try:
                from crestpoint_credit.notifications.services import NotificationService

                NotificationService.create_notification(
                    user=uid,
                    title=title,
                    message=message,
                    notification_type=notif_type,
                    channel="in_app",
                    data={"sent_by_admin": request.user.id, "admin_email": request.user.email},
                )
                sent_count += 1
            except Exception:
                logger.exception("Failed to send admin notification to user %s", uid)

        return Response(
            {"message": f"Notification sent to {sent_count} user(s)."},
            status=status.HTTP_200_OK,
        )
