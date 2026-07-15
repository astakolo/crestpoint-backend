from rest_framework.permissions import BasePermission, IsAuthenticated


class IsAccountOwner(BasePermission):
    """Ensure the requesting user owns the object being accessed.

    Intended for :class:`~.models.BankAccount` instances.
    """

    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class IsAdmin(BasePermission):
    """Allow access only to users with the ``admin`` role."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin"


class IsAdminOrSupport(BasePermission):
    """Allow access to users with ``admin`` or ``support`` roles."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ["admin", "support"]


class IsKYCPending(BasePermission):
    """Only allow users who do not already have an approved KYC to upload.

    If the user has no KYC record or their last KYC was rejected, they are
    allowed to proceed.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        user = request.user
        # No KYC document yet → allowed
        if not hasattr(user, "kyc_document"):
            return True

        kyc = user.kyc_document
        # Allowed if the existing document was rejected (user may re-submit)
        if kyc.status == "rejected":
            return True

        # Pending or approved → not allowed to re-upload
        return False


class IsVerifiedUser(BasePermission):
    """Only allow verified users (``is_verified=True``)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_verified
