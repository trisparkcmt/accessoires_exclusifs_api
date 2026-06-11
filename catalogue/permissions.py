from rest_framework import permissions
from utilisateur.permissions import is_active_serveuse

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

class IsAdminOrServeuseOrReadOnly(permissions.BasePermission):
    """
    - Autorise tout le monde à lire (GET, HEAD, OPTIONS).
    - Réserve la modification (POST, PUT, PATCH, DELETE) aux admins (is_staff)
      OU aux serveuses actives.
    """
    def has_permission(self, request, view):
        # Lecture seule autorisée pour tous
        if request.method in permissions.SAFE_METHODS:
            return True

        # Pour toute modification, l'utilisateur doit être authentifié
        if not (request.user and request.user.is_authenticated):
            return False

        # Les administrateurs (is_staff) ont toujours les droits d'écriture
        if request.user.is_staff:
            return True

        # Vérification si l'utilisateur est une serveuse active
        try:
            return hasattr(request.user, 'client') and hasattr(request.user.client, 'serveuse') and request.user.client.serveuse.actif
        except Exception:
            return False


class IsAdmin(permissions.BasePermission):
    """
    Permission stricte: Admin seulement.
    Aucun accès public, même en lecture.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


class IsAdminOrServeuse(permissions.BasePermission):
    """
    - Autorise la modification (POST, PUT, PATCH, DELETE) et la lecture (GET, HEAD, OPTIONS)
      aux admins (is_staff) OU aux serveuses actives.
    - Les autres utilisateurs n'auront aucun accès.
    """
    def has_permission(self, request, view):
        # Pour toute méthode, l'utilisateur doit être authentifié
        if not (request.user and request.user.is_authenticated):
            return False

        # Les administrateurs (is_staff) ont toujours les droits complets
        if request.user.is_staff:
            return True

        # Vérification si l'utilisateur est une serveuse active
        return is_active_serveuse(request.user)