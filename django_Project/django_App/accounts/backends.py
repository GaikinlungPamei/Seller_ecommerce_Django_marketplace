"""Custom authentication backend allowing login with either username or email."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

User = get_user_model()


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate a user using either their username or their email address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or not password:
            return None

        # Look up by case-insensitive username or case-insensitive email
        try:
            user = User.objects.filter(
                Q(username__iexact=username.strip()) | Q(email__iexact=username.strip())
            ).first()
        except Exception:
            return None

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
