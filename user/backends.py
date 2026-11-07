from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UserNoOrEmailBackend(ModelBackend):
    UserModel = get_user_model()

    def authenticate(self,
                     request,
                     username:str | None =None,
                     password:str | None =None,
                     **kwargs):

        user_id: str = self.UserModel.USERNAME_FIELD #type: ignore

        # username 可能是 user_id 或 email
        if username is None:
            username = kwargs.get(user_id)
        if username is None or password is None:
            return None

        query = Q(email__iexact=username) | Q(
            **{user_id: username}
        )

        try:
            user = self.UserModel._default_manager.get(query)

        except self.UserModel.DoesNotExist:
            # 防时序攻击
            self.UserModel().set_password(password)
            return None

        except self.UserModel.MultipleObjectsReturned:
            user = (
                self.UserModel._default_manager
                .filter(**{user_id: username})
                .first()

                or self.UserModel._default_manager.filter(email__iexact=username).first()
            )

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None