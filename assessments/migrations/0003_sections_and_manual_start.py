from django.db import migrations, models


def fill_section_data(apps, schema_editor):
    """Existing tests draw their whole pool per section; existing attempts
    keep their old single deadline on every section they touched."""
    Test = apps.get_model("assessments", "Test")
    Question = apps.get_model("assessments", "Question")
    Attempt = apps.get_model("assessments", "Attempt")
    for t in Test.objects.all():
        t.n_objective = Question.objects.filter(test=t, kind="mcq").count()
        t.n_tf = Question.objects.filter(test=t, kind="tf").count()
        t.n_subjective = Question.objects.filter(test=t, kind="short").count()
        t.save(update_fields=["n_objective", "n_tf", "n_subjective"])
    field_by_kind = {"mcq": "expires_objective", "tf": "expires_tf", "short": "expires_subjective"}
    section_by_kind = {"mcq": "objective", "tf": "tf", "short": "subjective"}
    for a in Attempt.objects.all():
        kinds = set(
            Question.objects.filter(
                id__in=[int(i) for i in a.drawn_ids.split(",") if i]
            ).values_list("kind", flat=True)
        )
        for kind in kinds:
            setattr(a, field_by_kind[kind], a.expires_at)
        a.current_section = "objective"
        for kind in ("tf", "short"):
            if kind in kinds:
                a.current_section = section_by_kind[kind]
        a.section_started_at = a.started_at
        a.save()


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0002_alter_test_join_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="test",
            name="n_objective",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="test",
            name="n_tf",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="test",
            name="n_subjective",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="test",
            name="seconds_tf",
            field=models.PositiveIntegerField(default=20),
        ),
        migrations.AddField(
            model_name="test",
            name="started_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="test",
            name="closed_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="attempt",
            name="current_section",
            field=models.CharField(
                choices=[
                    ("objective", "Objective"),
                    ("tf", "True / False"),
                    ("subjective", "Subjective"),
                ],
                default="objective",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="attempt",
            name="section_started_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="attempt",
            name="expires_objective",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="attempt",
            name="expires_tf",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="attempt",
            name="expires_subjective",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.RunPython(fill_section_data, migrations.RunPython.noop),
        migrations.RemoveField(model_name="test", name="open_at"),
        migrations.RemoveField(model_name="test", name="close_at"),
        migrations.RemoveField(model_name="test", name="n_to_answer"),
        migrations.RemoveField(model_name="attempt", name="expires_at"),
        migrations.AlterModelOptions(
            name="test",
            options={"ordering": ["-created_at"]},
        ),
    ]
