from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0003_sections_and_manual_start"),
    ]

    operations = [
        migrations.AddField(
            model_name="test",
            name="is_makeup",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="test",
            name="allowed_students",
            field=models.ManyToManyField(
                blank=True, related_name="makeup_tests", to=settings.AUTH_USER_MODEL
            ),
        ),
    ]
