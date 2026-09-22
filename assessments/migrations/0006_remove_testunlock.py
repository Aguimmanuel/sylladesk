from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0005_test_unlock"),
    ]

    operations = [
        migrations.DeleteModel(name="TestUnlock"),
    ]
