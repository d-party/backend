from django.contrib import admin
from django.utils.timezone import now

from .models import AnimeReaction, AnimeRoom, AnimeUser, Setting


@admin.action(description="Logically delete selected items")
def logically_delete(modeladmin, request, queryset):
    queryset.update(deleted_at=now())


@admin.action(description="Revive selected items")
def revive(modeladmin, request, queryset):
    queryset.update(deleted_at=None)


class LogicalDeletionModelAdmin(admin.ModelAdmin):
    """Admin base for models using logical deletion."""

    actions = [logically_delete, revive]
    readonly_fields = ("deleted_at",)

    def get_queryset(self, request):
        # Show every row (including logically deleted) in the admin.
        return self.model.objects.get_queryset()


@admin.register(AnimeRoom)
class AnimeRoomAdmin(LogicalDeletionModelAdmin):
    list_display = (
        "room_id",
        "title",
        "part_id",
        "num_people",
        "created_at",
        "deleted_at",
    )


@admin.register(AnimeUser)
class AnimeUserAdmin(LogicalDeletionModelAdmin):
    list_display = ("user_id", "is_host", "created_at", "deleted_at")


@admin.register(AnimeReaction)
class AnimeReactionAdmin(LogicalDeletionModelAdmin):
    list_display = ("reaction_id", "reaction_type", "created_at", "deleted_at")


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = (
        "room",
        "one_way",
        "owner_leave_delete",
        "disable_reaction",
        "updated_at",
    )
