from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    - Autorise tout le monde à lire (GET, HEAD, OPTIONS).
    - Réserve la modification (POST, PUT, DELETE, etc.) aux admins (is_staff).
    """
    def has_permission(self, request, view):
        # Si la méthode est SAFE (lecture seule), on autorise
        if request.method in permissions.SAFE_METHODS:
            return True

        # Pour les autres méthodes (écriture), l'utilisateur doit être admin
        return bool(request.user and request.user.is_staff)


class IsAdmin(permissions.BasePermission):
    """
    Permission stricte: Admin seulement.
    Aucun accès public, même en lecture.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)