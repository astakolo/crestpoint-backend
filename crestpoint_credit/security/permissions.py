"""Custom DRF permission classes for role-based access control."""

import logging

from rest_framework.permissions import BasePermission

logger = logging.getLogger("crestpoint_credit")


class IsAdminRole(BasePermission):
    """Only users with the ``admin`` role are permitted."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "admin"
        )


class IsCustomerRole(BasePermission):
    """Only users with the ``customer`` role are permitted."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "customer"
        )


class IsSupportRole(BasePermission):
    """Only ``admin`` or ``support`` roles are permitted."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ("admin", "support")
        )


class IsAuditorRole(BasePermission):
    """Only ``admin`` or ``auditor`` roles are permitted."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ("admin", "auditor")
        )


class IsOwnerOrAdmin(BasePermission):
    """Object-level permission: the requesting user must own the object **or**
    have the ``admin`` role.

    The target object must expose a ``user`` foreign-key / one-to-one field.
    """

    def has_object_permission(self, request, view, obj):
        return bool(
            getattr(obj, "user", None) == request.user
            or (request.user and request.user.role == "admin")
        )


class HasVerifiedKYC(BasePermission):
    """Only users whose ``is_verified`` flag is ``True`` are permitted."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_verified", False)
        )
