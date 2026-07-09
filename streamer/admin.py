from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.utils.timezone import now
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import AnimeReaction, AnimeRoom, AnimeUser, Setting


@admin.action(description="Logically delete selected items")
def logically_delete(modeladmin, request, queryset):
    queryset.update(deleted_at=now())


@admin.action(description="Revive selected items")
def revive(modeladmin, request, queryset):
    queryset.update(deleted_at=None)


class LogicalDeletionModelAdmin(ModelAdmin):
    """Admin base for models using logical deletion (django-unfold themed)."""

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
class SettingAdmin(ModelAdmin):
    list_display = (
        "room",
        "one_way",
        "owner_leave_delete",
        "disable_reaction",
        "updated_at",
    )


# django.contrib.auth の User / Group を unfold 仕様で再登録し、フォーム・変更画面の
# 見た目も管理画面テーマに揃える（unfold.forms が Tailwind スタイルのウィジェットを提供）。
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
