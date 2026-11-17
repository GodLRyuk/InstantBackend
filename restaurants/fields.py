"""Small Fernet-backed model field for beneficiary account numbers."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


class EncryptedTextField(models.TextField):
    prefix = 'fernet$'

    @staticmethod
    def _fernet():
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
        return Fernet(key)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value.startswith(self.prefix):
            return value
        token = self._fernet().encrypt(value.encode()).decode()
        return self.prefix + token

    def from_db_value(self, value, expression, connection):
        if value is None or not value.startswith(self.prefix):
            return value
        try:
            return self._fernet().decrypt(value[len(self.prefix):].encode()).decode()
        except InvalidToken as exc:
            raise ValueError('Unable to decrypt restaurant vendor bank account.') from exc
