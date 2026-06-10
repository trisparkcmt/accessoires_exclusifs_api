from rest_framework import permissions


def is_serveuse(user):
    """Vérifie si l'utilisateur est une serveuse active."""
    return (
        user and
        user.is_authenticated and
        hasattr(user, 'client') and
        hasattr(user.client, 'serveuse') and
        user.client.serveuse.statut not in ['inactif', 'suspendu']
    )


class IsAdminOnly(permissions.BasePermission):
    """
    Accès STRICTEMENT réservé aux administrateurs (is_staff).
    Les serveuses n'ont aucun accès, même en lecture.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


class IsAdminOrServeuseReadOnly(permissions.BasePermission):
    """
    - Admin (is_staff) : accès complet (lecture + écriture).
    - Serveuse active : lecture seule (SAFE_METHODS uniquement).
    - Autres utilisateurs : aucun accès.

    Utilisé pour les routes de gestion des utilisateurs (prestataires, livreurs, clients)
    où la serveuse peut consulter mais pas modifier.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        # Admin : accès complet
        if user.is_staff:
            return True
        # Serveuse : lecture seule
        if request.method in permissions.SAFE_METHODS and is_serveuse(user):
            return True
        return False


class IsAdminOrServeuse(permissions.BasePermission):
    """
    - Admin (is_staff) : accès complet.
    - Serveuse active : accès complet (même droits que l'admin).
    - Autres utilisateurs : aucun accès.

    Utilisé pour les routes de gestion du catalogue, des commandes, des livraisons,
    des stats globales, des notifications, etc.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        # Admin : accès complet
        if user.is_staff:
            return True
        # Serveuse active : accès complet
        if is_serveuse(user):
            return True
        return False


class DepensePermission(permissions.BasePermission):
    """
    Permission d'accès à la table Dépense :
    - Admin (is_staff) : accès complet (CRUD).
    - Serveuse active : accès complet (CRUD).
    - Autres rôles : aucun accès.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or is_serveuse(user):
            return True
        return False

