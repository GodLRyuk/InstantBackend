import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
from django.core.files.storage import Storage
from django.conf import settings
import os

cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

class CloudinaryStorage(Storage):
    def _save(self, name, content):
        result = cloudinary.uploader.upload(content, public_id=name.split('.')[0], overwrite=True)
        return result['secure_url']

    def url(self, name):
        return name

    def exists(self, name):
        return False

    def _open(self, name, mode='rb'):
        pass