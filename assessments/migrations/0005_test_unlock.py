import django.db.models.deletion

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0004_makeup_tests"),
    ]

    operations = [
        migrations.CreateModel(
            name="TestUnlock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("student", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="test_unlocks", to=settings.AUTH_USER_MODEL)),
                ("test", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="unlocks", to="assessments.test")),
            ],
            options={
                "constraints": [models.UniqueConstraint(
                    fields=("test", "student"), name="uniq_test_unlock")],
            },
        ),
    ]
