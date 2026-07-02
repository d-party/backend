"""Pydantic models describing the WebSocket message protocol.

These models define the exact shape of every message the streamer consumer
emits. The wire format is part of the public contract shared with the Chrome
extension and the front-end, so field names, ``action`` values and nesting must
not change.

Note: ``SerializeAsAny`` is required on the ``response`` field so that, under
pydantic v2, subclass-specific fields are kept when serializing a field typed
as the ``ResponseBaseFormat`` base class (this matched pydantic v1's default
``.dict()`` behaviour).
"""

from uuid import UUID

from pydantic import BaseModel, SerializeAsAny, field_validator


class User(BaseModel):
    """A participant.

    Attributes:
        user_id: UUID identifying the user.
        user_name: display name chosen by the user.
        user_icon: react-icons (Font Awesome 6) key string chosen by the user.
            Defaults to ``FaRegUser`` so older clients/data that omit it fall back
            to the plain user icon.
        is_host: whether this participant is the room host (owner).
    """

    user_id: UUID
    user_name: str
    user_icon: str = "FaRegUser"
    is_host: bool = False


class ResponseBaseFormat(BaseModel):
    """Base class for messages.

    Received data is dispatched by its ``action`` field; outgoing data
    subclasses this to describe its payload.
    """

    action: str


class Join(ResponseBaseFormat):
    action: str = "join"
    room_id: UUID
    user: User


class Leave(ResponseBaseFormat):
    action: str = "leave"
    user: User


class Create(ResponseBaseFormat):
    action: str = "create"
    room_id: UUID
    user: User


class Option(BaseModel):
    time: float
    src: str | None
    paused: str
    rate: str
    part_id: str

    @field_validator("paused", "rate", mode="before")
    @classmethod
    def _coerce_to_str(cls, value):
        # The extension sends `paused` as a bool and `rate` as a number; pydantic
        # v1 stringified these (e.g. False -> "False"), and the client relies on
        # that exact form (`option["paused"] === "False"`). Preserve it under v2.
        if value is None or isinstance(value, str):
            return value
        return str(value)


class VideoOperation(ResponseBaseFormat):
    action: str = "video_operation"
    room_id: UUID
    operation: str
    user: User
    option: Option
    # 現在視聴中のエピソードタイトル（拡張機能がページ DOM から取得して同梱）。タイマー画面が
    # エピソード切替に追従して表示するために使う。旧クライアントは送らないため任意（None）。
    title: str | None = None


class OperationNotification(ResponseBaseFormat):
    action: str = "operation_notification"
    room_id: UUID
    operation: str
    user: User


class Reaction(ResponseBaseFormat):
    action: str = "reaction"
    reaction_type: str
    # 送信者。拡張機能の「バッジ表示」等で「ユーザー名 : リアクション」を出すため
    # に同梱する。旧クライアントは無視する。
    user: User


class SyncRequest(ResponseBaseFormat):
    action: str = "sync_request"
    user: User


class SyncResponse(ResponseBaseFormat):
    action: str = "sync_response"
    option: Option


class UserAdd(ResponseBaseFormat):
    action: str = "user_add"
    user: User


class ServerMessage(ResponseBaseFormat):
    action: str = "server_message"
    message_type: str


class UserList(ResponseBaseFormat):
    action: str = "user_list"
    user_list: list[User]


class SpectateAck(ResponseBaseFormat):
    """観覧専用（spectator）参加の受理応答。

    タイマー画面（拡張機能なしのユーザー）が最初の video_operation ブロードキャストを
    受け取る前に、現在の視聴対象（part_id / title）を把握できるよう初期状態を返す。
    """

    action: str = "spectate"
    room_id: UUID
    part_id: str
    title: str = ""


class BaseGroupSend(BaseModel):
    type: str
    sender_channel_name: str
    response: SerializeAsAny[ResponseBaseFormat]


class GroupSend(BaseGroupSend):
    type: str = "group_send"


class RoomSend(BaseGroupSend):
    type: str = "room_send"


class HostSend(BaseGroupSend):
    type: str = "host_send"


class UserSend(BaseGroupSend):
    type: str = "user_send"
    to_user: User
