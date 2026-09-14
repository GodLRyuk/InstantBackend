from rest_framework.permissions import SAFE_METHODS, BasePermission


class PublicCatalogPermission(BasePermission):
    """Allow anyone to read catalog data, but require login to change it."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or request.user.is_authenticated
