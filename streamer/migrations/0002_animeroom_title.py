from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("streamer", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="animeroom",
            name="title",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
