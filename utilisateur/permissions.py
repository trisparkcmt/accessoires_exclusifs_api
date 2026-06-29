from rest_framework import permissions


def is_active_serveuse(user):
    """Vérifie si l'utilisateur est une serveuse active."""
    return (
        user and
        user.is_authenticated and
        hasattr(user, 'client') and
        hasattr(user.client, 'serveuse') and
        user.client.serveuse.actif
    )


def is_active_prestataire(user):
    """Vérifie si l'utilisateur est un prestataire actif."""
    return (
        user and
        user.is_authenticated and
        hasattr(user, 'client') and
        hasattr(user.client, 'prestataire') and
        user.client.prestataire.statut == 'actif'
    )


def is_active_livreur(user):
    """Vérifie si l'utilisateur est un livreur actif."""
    return (
        user and
        user.is_authenticated and
        hasattr(user, 'client') and
        hasattr(user.client, 'livreur') and
        user.client.livreur.statut != 'inactif'
    )


def is_active_client(user):
    """Vérifie si l'utilisateur est un client actif (n'importe quel statut sauf inactif/suspendu)."""
    return (
        user and
        user.is_authenticated and
        user.is_active
    )


class IsSuperadmin(permissions.BasePermission):
    """Accès STRICTEMENT réservé aux superadmins (is_superuser)."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


class IsActiveSuperadmin(permissions.BasePermission):
    """Accès superadmin actif uniquement."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser and request.user.is_active)


class IsActiveServeuse(permissions.BasePermission):
    """Accès réservé aux serveuses actives."""
    def has_permission(self, request, view):
        return is_active_serveuse(request.user)


class IsSuperadminOrActiveServeuse(permissions.BasePermission):
    """Accès superadmin ou serveuse active (accès complet)."""
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return is_active_serveuse(user)


class IsActivePrestataire(permissions.BasePermission):
    """Accès réservé aux prestataires actifs."""
    def has_permission(self, request, view):
        return is_active_prestataire(request.user)


class IsActiveLivreur(permissions.BasePermission):
    """Accès réservé aux livreurs actifs."""
    def has_permission(self, request, view):
        return is_active_livreur(request.user)


class IsActiveClient(permissions.BasePermission):
    """Accès réservé aux clients actifs."""
    def has_permission(self, request, view):
        return is_active_client(request.user)


class IsSuperadminOrServeuseReadOnly(permissions.BasePermission):
    """Superadmin accès complet, Serveuse active lecture seule."""
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if request.method in permissions.SAFE_METHODS and is_active_serveuse(user):
            return True
        return False


class IsSuperadminOnly(permissions.BasePermission):
    """Accès STRICTEMENT réservé aux superadmins - aucun accès Serveuse."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


class DepensePermission(permissions.BasePermission):
    """
    Dépenses :
    - GET (list/detail) : superadmin voit tout ; serveuse active voit ses dépenses (queryset).
    - POST : serveuse active uniquement.
    - PUT/PATCH : serveuse active, uniquement sur ses propres dépenses.
    - DELETE : superadmin uniquement (pas de modification admin).
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        action = view.action

        if user.is_superuser:
            if action in ('create', 'update', 'partial_update'):
                return False
            return action in ('list', 'retrieve', 'destroy')

        if is_active_serveuse(user):
            return action in ('list', 'retrieve', 'create', 'update', 'partial_update')

        return False

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return view.action in ('retrieve', 'destroy')
        if is_active_serveuse(user):
            if view.action in ('retrieve', 'update', 'partial_update'):
                return obj.cree_par_id == user.id
        return False


class CommandePermission(permissions.BasePermission):
    """
    Permissions pour les Commandes :
    - Admin et Serveuse active : accès complet (lecture, assignation livreur, modification statuts commande/livraison).
    - Livreur actif : accès en lecture à ses commandes assignées, et modification uniquement du statut de paiement vers 'payé' ou 'échoué'.
    - Client actif : accès en lecture à ses propres commandes.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Superadmin
        if user.is_superuser:
            return True
            
        # Serveuse active
        if is_active_serveuse(user):
            return True
            
        # Livreur actif
        if is_active_livreur(user):
            # Doit être le livreur assigné à cette commande
            return bool(obj.livreur and obj.livreur.user == user)
            
        # Client actif
        if is_active_client(user):
            # Uniquement lecture/actions sur ses propres commandes
            return bool(obj.client and obj.client.user == user)
                
        return False


