from django.db import models


class TimestampedModel(models.Model):
    """Abstract base model that provides created_at and updated_at timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class SoftDeleteModel(TimestampedModel):
    """Abstract base model that provides soft-delete functionality.

    Extends TimestampedModel with is_deleted flag and deleted_at timestamp.
    Records are never truly deleted; instead they are marked as deleted.
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def soft_delete(self):
        """Mark this record as deleted without removing it from the database."""
        from django.utils import timezone

        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def restore(self):
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
