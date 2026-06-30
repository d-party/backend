"""Logical (soft) deletion support.

This module is a self-contained replacement for the now-unmaintained
``django_boost`` ``LogicalDeletionMixin``. The public behaviour is kept
identical so the streamer core logic does not have to change:

* ``Model.objects.alive()`` / ``.dead()`` filter by the ``deleted_at`` flag.
* ``instance.delete()`` performs a *logical* delete (sets ``deleted_at``)
  while ``instance.delete(hard=True)`` performs a real delete.
* ``queryset.delete()`` / ``queryset.delete(hard=True)`` mirror the same
  semantics at the queryset level.
"""

from __future__ import annotations

from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

DELETE_FLAG_FIELD = "deleted_at"


class LogicalDeletionQuerySet(models.QuerySet):
    def delete(self, hard: bool = False):
        if hard:
            return super().delete()
        return super().update(**{DELETE_FLAG_FIELD: now()})

    def alive(self):
        return self.filter(**{DELETE_FLAG_FIELD: None})

    def dead(self):
        return self.exclude(**{DELETE_FLAG_FIELD: None})

    def revive(self):
        return self.update(**{DELETE_FLAG_FIELD: None})


class LogicalDeletionManager(models.Manager.from_queryset(LogicalDeletionQuerySet)):
    """Manager exposing the logical-deletion queryset helpers."""


class LogicalDeletionMixin(models.Model):
    """Abstract base model providing logical deletion."""

    deleted_at = models.DateTimeField(
        verbose_name=_("deleted date"),
        blank=True,
        null=True,
        default=None,
        editable=False,
    )

    objects = LogicalDeletionManager()

    class Meta:
        abstract = True

    @classmethod
    def get_deleted_value(cls):
        return now()

    def delete(self, using=None, keep_parents=False, hard=False):
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.deleted_at = self.get_deleted_value()
        self.save(using=using, update_fields=[DELETE_FLAG_FIELD])
        return (1, {self._meta.label: 1})

    def revive(self, force_update=False, using=None):
        self.deleted_at = None
        return self.save()

    def is_dead(self) -> bool:
        return self.deleted_at is not None

    def is_alive(self) -> bool:
        return self.deleted_at is None
