from django.contrib.auth import get_user_model

User = get_user_model()


def make_user(**overrides):
    defaults = dict(
        username="student1",
        full_name="Test Student",
        global_role=User.GlobalRole.STUDENT,
    )
    defaults.update(overrides)
    password = defaults.pop("password", "sensible-password-1")
    must_reset = defaults.pop("must_reset_password", False)
    user = User(**defaults)
    user.set_password(password)
    user.must_reset_password = must_reset
    user.save()
    return user
