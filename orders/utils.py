from orders.models import Panier

def get_or_create_panier(request, panier_id=None):
    """
    Récupère ou crée le panier actif (statut='actif') pour la requête courante.
    
    - Si l'utilisateur est connecté (authentifié) :
      - On cherche son panier actif lié à son profil Client.
      - S'il n'en a pas, mais qu'un panier_id anonyme est fourni (ou présent en session),
        on rattache ce panier anonyme à l'utilisateur connecté.
      - Sinon, on crée un nouveau panier lié à son profil Client.
      
    - Si l'utilisateur est anonyme (non connecté) :
      - On cherche le panier correspondant à l'id fourni en paramètre (`panier_id`).
      - Si non trouvé/non fourni, on cherche dans la session Django.
      - Sinon, on crée un nouveau panier anonyme et on stocke son ID en session.
    """
    if request.user.is_authenticated:
        client = getattr(request.user, 'client', None)
        if client:
            panier = Panier.objects.filter(client=client, statut='actif').first()
            if not panier:
                # Tentative de rattachement d'un panier anonyme existant
                if panier_id:
                    panier = Panier.objects.filter(id=panier_id, client__isnull=True, statut='actif').first()
                if not panier and hasattr(request, 'session'):
                    session_panier_id = request.session.get('panier_id')
                    if session_panier_id:
                        panier = Panier.objects.filter(id=session_panier_id, client__isnull=True, statut='actif').first()
                
                if panier:
                    panier.client = client
                    panier.save(update_fields=['client'])
                    # Nettoyer la session puisque le panier est maintenant associé au compte
                    if hasattr(request, 'session') and 'panier_id' in request.session:
                        del request.session['panier_id']
                else:
                    panier = Panier.objects.create(client=client, statut='actif')
            return panier

    # Utilisateur anonyme
    if panier_id:
        panier = Panier.objects.filter(id=panier_id, statut='actif').first()
        if panier:
            return panier
            
    if hasattr(request, 'session'):
        session_panier_id = request.session.get('panier_id')
        if session_panier_id:
            panier = Panier.objects.filter(id=session_panier_id, statut='actif').first()
            if panier:
                return panier
                
    # Création d'un nouveau panier invité
    panier = Panier.objects.create(statut='actif')
    if hasattr(request, 'session'):
        request.session['panier_id'] = panier.id
    return panier
