import factory
import factory.fuzzy

from .models import AnimeRoom, AnimeUser, Setting


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
