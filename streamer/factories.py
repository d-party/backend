import factory
import factory.fuzzy

from .models import AnimeRoom, AnimeUser, DmmRoom, DmmSetting, DmmUser, Setting


class AnimeRoomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnimeRoom

    num_people = factory.fuzzy.FuzzyInteger(5, 10)
    sum_people = factory.fuzzy.FuzzyInteger(10, 20)
    part_id = "123456"
    title = factory.Faker("sentence", nb_words=3)
    updated_at = factory.Faker("date")
    created_at = factory.Faker("date")


class AnimeUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnimeUser

    user_name = factory.Faker("name")
    user_icon = "FaRegUser"
    room_id = factory.SubFactory(AnimeRoomFactory)
    is_host = False
    updated_at = factory.Faker("date")
    created_at = factory.Faker("date")


class SettingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Setting

    room = factory.SubFactory(AnimeRoomFactory)
    one_way = False
    owner_leave_delete = False
    disable_reaction = False


class DmmRoomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DmmRoom

    num_people = factory.fuzzy.FuzzyInteger(5, 10)
    sum_people = factory.fuzzy.FuzzyInteger(10, 20)
    part_id = "c7tzzizzvhuj53zhmpf9aa2c0"
    title = factory.Faker("sentence", nb_words=3)
    updated_at = factory.Faker("date")
    created_at = factory.Faker("date")


class DmmUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DmmUser

    user_name = factory.Faker("name")
    user_icon = "FaRegUser"
    room_id = factory.SubFactory(DmmRoomFactory)
    is_host = False
    updated_at = factory.Faker("date")
    created_at = factory.Faker("date")


class DmmSettingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DmmSetting

    room = factory.SubFactory(DmmRoomFactory)
    one_way = False
    owner_leave_delete = False
    disable_reaction = False
