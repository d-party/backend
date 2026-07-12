from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
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
    # 既定は作成日時の降順（新しいものが先頭）で並べる。
    ordering = ("-created_at",)

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
    # user_name は EncryptedCharField（保存時暗号化）だが from_db_value で
    # ORM 読み込み時に透過的に復号されるため、そのまま平文で表示できる。
    # 暗号化列のため DB 側での並べ替え・検索はできない（表示のみ）。
    list_display = ("user_name", "user_id", "is_host", "created_at", "deleted_at")


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
    # 既定は作成日時の降順（新しいものが先頭）で並べる。
    ordering = ("-created_at",)


# django.contrib.auth の User / Group を unfold 仕様で再登録し、フォーム・変更画面の
# 見た目も管理画面テーマに揃える（unfold.forms が Tailwind スタイルのウィジェットを提供）。
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    # 一覧からも姓名列（既定の first_name / last_name）を外す。
    list_display = ("username", "email", "is_staff")

    # d-party の参加者は AnimeUser.user_name（表示名）で管理し、管理者アカウント
    # （auth.User）の姓名（first_name / last_name）は一切使わない。カラム自体は
    # Django 組み込みのため残るが、編集画面には出さないよう "Personal info" から
    # 姓名を除いて email のみ残す。
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("email",)}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
