from decimal import Decimal

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from utilisateur.throttles import IARecommandationThrottle
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import ParfumPersonnalise, EssencePersonnalisee, IAConversation, IAConversationMessage, IAConversationSummary
from .serializers import (
    ParfumPersonnaliseSerializer,
    EssencePersonnaliseeSerializer,
    ParfumLabSerializer,
    EssenceLabSerializer,
    AccessoireLabSerializer,
)
from .permissions import IsCreatorOrReadOnly
from catalogue.pagination import StandardPagination
from catalogue.models import Parfum, Essence, Accessoire, Flacon, Ingredient
from .utils_ia import demander_recommandation_ia, generer_resume_conversation



class ParfumPersonnaliseViewSet(viewsets.ModelViewSet):
    serializer_class = ParfumPersonnaliseSerializer
    permission_classes = [IsAuthenticated, IsCreatorOrReadOnly]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'statut',
        'flacon',
        'client__user__email',
        'nom',
        'date_creation',
        'date_modification',
        'prix_total',
    ]
    search_fields = [
        'nom',
        'description',
        'client__user__email',
        'lignes__essence__essence__nom',
        'lignes__essence_personnalisee__nom',
    ]
    ordering_fields = ['prix_total', 'date_creation', 'nom']
    ordering = ['-date_creation']

    def get_queryset(self):
        queryset = ParfumPersonnalise.objects.all().select_related(
            'flacon', 'client', 'client__user'
        ).prefetch_related(
            'lignes__essence__essence',
            'lignes__essence_personnalisee',
            'lignes__essence_personnalisee__lignes',
            'lignes__essence_personnalisee__lignes__ingredient',
        ).distinct()

        from utilisateur.permissions import is_privileged_dashboard_user

        if is_privileged_dashboard_user(self.request):
            return queryset

        if hasattr(self.request.user, 'client'):
            if self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
                return queryset.filter(client=self.request.user.client)
            return queryset.filter(client=self.request.user.client, enregistre=True)

        return queryset.none()

    @action(detail=True, methods=['post'], url_path='recalculer')
    def recalculer(self, request, pk=None):
        parfum = self.get_object()
        parfum.recalculer_prix()
        serializer = self.get_serializer(parfum)
        return Response(serializer.data)


class EssencePersonnaliseeViewSet(viewsets.ModelViewSet):
    serializer_class = EssencePersonnaliseeSerializer
    permission_classes = [IsAuthenticated, IsCreatorOrReadOnly]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'nom',
        'client__user__email',
        'date_creation',
        'prix_par_ml_calcule',
    ]
    search_fields = ['nom', 'client__user__email', 'lignes__ingredient__nom']
    ordering_fields = ['prix_par_ml_calcule', 'date_creation', 'nom']
    ordering = ['-date_creation']

    def get_queryset(self):
        queryset = EssencePersonnalisee.objects.all().select_related(
            'client', 'client__user'
        ).prefetch_related('lignes__ingredient').distinct()

        from utilisateur.permissions import is_privileged_dashboard_user

        if is_privileged_dashboard_user(self.request):
            return queryset

        if hasattr(self.request.user, 'client'):
            return queryset.filter(client=self.request.user.client)

        return queryset.none()


def get_ia_conversation(request):
    if not hasattr(request, 'session'):
        raise RuntimeError('Session middleware is requis pour l’historique IA.')

    if not request.session.session_key:
        request.session.create()

    session_key = request.session.session_key
    client = None
    if getattr(request.user, 'is_authenticated', False) and hasattr(request.user, 'client'):
        client = request.user.client

    if client:
        # Tenter de récupérer la dernière conversation associée à ce client
        conversation = IAConversation.objects.filter(client=client).order_by('-updated_at').first()
        if not conversation:
            import uuid
            s_key = session_key
            if IAConversation.objects.filter(session_key=s_key).exists():
                s_key = f"client-{client.id}-{uuid.uuid4().hex[:8]}"
            conversation = IAConversation.objects.create(session_key=s_key, client=client)
    else:
        conversation, _ = IAConversation.objects.get_or_create(
            session_key=session_key,
            defaults={'client': client}
        )

    if client and conversation.client is None:
        conversation.client = client
        conversation.save(update_fields=['client'])

    return conversation


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([IARecommandationThrottle])
def ia_recommandation(request):
    """
    Reçoit un prompt de l'utilisateur, interroge l'IA et renvoie des produits.
    Utilise le résumé de conversation en DB pour le contexte (plus efficace que l'historique complet).
    Génère et sauvegarde un nouveau résumé après chaque échange.
    """
    prompt = request.data.get('prompt')
    print(f"\n>>> [VIEW ia_recommandation] Requete POST recue avec prompt: '{prompt}'", flush=True)
    if not prompt:
        return Response({"error": "Veuillez fournir un 'prompt'."}, status=status.HTTP_400_BAD_REQUEST)

    conversation = get_ia_conversation(request)
    IAConversationMessage.objects.create(conversation=conversation, role='user', content=prompt)

    # --- Récupération du résumé et des infos client ---
    if getattr(request.user, 'is_authenticated', False) and hasattr(request.user, 'client'):
        client = request.user.client
        prenom = (request.user.first_name or '').strip()
        nom = (request.user.last_name or '').strip()
        nom_complet = f"{prenom} {nom}".strip() or request.user.username
        client_info = {
            'nom': nom_complet,
            'prenom': prenom,
            'nom_famille': nom,
            'email': request.user.email,
        }
    else:
        client = None
        client_info = None

    # Récupérer le résumé existant de la conversation courante
    try:
        summary_obj = conversation.summary
        resume_existant = summary_obj.summary_text or ''
    except IAConversationSummary.DoesNotExist:
        summary_obj = None
        resume_existant = ''

    # Fallback : si pas encore de résumé, envoyer les 6 derniers messages bruts
    history = []
    if not resume_existant:
        history_qs = conversation.messages.order_by('-created_at')[:6].values('role', 'content')
        history = list(reversed(list(history_qs)))

    print(f"[VIEW ia_recommandation] Résumé existant: {bool(resume_existant)} ({len(resume_existant)} chars)", flush=True)

    # --- Appel IA ---
    reponse_ia = demander_recommandation_ia(
        prompt,
        history=history,
        client_info=client_info,
        resume=resume_existant or None,
    )
    if "error" in reponse_ia:
        return Response(reponse_ia, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # --- Sauvegarde du message assistant + JSON complet ---
    assistant_message = reponse_ia.get('message', 'Voici quelques recommandations :')
    # On garde tout le JSON LIA dans metadata (sauf le champ 'message' déjà dans content)
    assistant_metadata = {k: v for k, v in reponse_ia.items() if k != 'message'}
    IAConversationMessage.objects.create(
        conversation=conversation,
        role='assistant',
        content=assistant_message,
        metadata=assistant_metadata,
    )

    # --- Mise à jour du résumé EN ARRIÈRE-PLAN (thread daemon) ---
    # Le client reçoit sa réponse immédiatement.
    # Le résumé est généré et sauvegardé après coup, sans bloquer.
    import threading

    def _mettre_a_jour_resume():
        try:
            from django.db import connection as _conn
            messages_pour_resume = list(
                conversation.messages.order_by('-created_at')[:10].values('role', 'content')
            )
            messages_pour_resume.reverse()
            nouveau_resume = generer_resume_conversation(messages_pour_resume, resume_existant=resume_existant)
            if summary_obj:
                summary_obj.summary_text = nouveau_resume
                summary_obj.save(update_fields=['summary_text', 'updated_at'])
            else:
                IAConversationSummary.objects.create(conversation=conversation, summary_text=nouveau_resume)
            print(f"[RESUME THREAD] Résumé mis à jour en BD pour conv #{conversation.id}.", flush=True)
        except Exception as e:
            print(f"[RESUME THREAD] Erreur (non bloquant): {e}", flush=True)
        finally:
            # Fermer la connexion DB proprement dans le thread secondaire
            from django.db import connections
            connections.close_all()

    t = threading.Thread(target=_mettre_a_jour_resume, daemon=True)
    t.start()

    # --- Nettoyage : ne garder que les 30 derniers messages ---
    total_messages = conversation.messages.count()
    if total_messages > 30:
        ids_a_supprimer = list(
            conversation.messages.order_by('created_at')[:total_messages - 30].values_list('id', flat=True)
        )
        IAConversationMessage.objects.filter(id__in=ids_a_supprimer).delete()

    # --- Construction de la réponse ---
    ids_parfums = reponse_ia.get('parfums_existants_recommandes', [])
    ids_parfums = [p.get('id') if isinstance(p, dict) else p for p in ids_parfums if p is not None]
    essences_data = reponse_ia.get('essences_pre_faites', [])
    ingredients_data = reponse_ia.get('ingredients_sur_mesure', [])
    ids_accessoires = reponse_ia.get('accessoires', [])
    ids_accessoires = [a.get('id') if isinstance(a, dict) else a for a in ids_accessoires if a is not None]
    ids_diffuseurs = reponse_ia.get('diffuseurs', [])
    ids_diffuseurs = [d.get('id') if isinstance(d, dict) else d for d in ids_diffuseurs if d is not None]
    flacon_id = reponse_ia.get('flacon_id')
    quantite_demandee_ml = reponse_ia.get('quantite_demandee_ml', 50)

    parfums = Parfum.objects.filter(id__in=ids_parfums, actif=True, stock_quantite__gt=0)
    accessoires = Accessoire.objects.filter(id__in=ids_accessoires, actif=True, stock_quantite__gt=0)
    from catalogue.models import DiffuseurParfum as DiffuseurModel
    diffuseurs = DiffuseurModel.objects.filter(id__in=ids_diffuseurs, actif=True, stock_quantite__gt=0)
    flacon = None
    essences_recommandees = []
    ingredients_recommandes = []

    if flacon_id:
        try:
            flacon = Flacon.objects.get(id=flacon_id, actif=True)
        except Flacon.DoesNotExist:
            flacon = None

    essence_ids = [e.get('id') for e in essences_data if isinstance(e, dict)]
    if essence_ids and flacon:
        from catalogue.models import LotEssence
        for e_data in essences_data:
            if not isinstance(e_data, dict):
                continue
            essence_id = e_data.get('id')
            quantite_ml = float(e_data.get('quantite_ml', 0) or 0)
            if not essence_id or quantite_ml <= 0:
                continue
            lot = LotEssence.objects.filter(
                essence_id=essence_id, actif=True, stock_ml__gte=quantite_ml
            ).order_by('date_reception').first()
            if not lot:
                continue
            from decimal import Decimal as D
            essences_recommandees.append({
                'id': lot.essence.id,
                'lot_essence_id': lot.id,
                'nom': lot.essence.nom,
                'code_reference': lot.essence.code_reference,
                'prix_par_ml': str(lot.essence.prix_par_ml),
                'quantite_ml': quantite_ml,
                'prix_total_quantite': str(lot.essence.prix_par_ml * D(str(quantite_ml))),
            })

    if ingredients_data and flacon:
        for i_data in ingredients_data:
            if not isinstance(i_data, dict):
                continue
            ingredient_id = i_data.get('id')
            quantite_ml = float(i_data.get('quantite_ml', 0) or 0)
            if not ingredient_id or quantite_ml <= 0:
                continue
            try:
                ingredient = Ingredient.objects.get(id=ingredient_id, actif=True)
                from decimal import Decimal as D
                ingredients_recommandes.append({
                    'id': ingredient.id,
                    'nom': ingredient.nom,
                    'prix_par_ml': str(ingredient.prix_par_ml),
                    'quantite_ml': quantite_ml,
                    'prix_total_quantite': str(ingredient.prix_par_ml * D(str(quantite_ml))),
                })
            except Ingredient.DoesNotExist:
                continue

    afficher_flacon = bool(essences_recommandees or ingredients_recommandes)

    from .serializers import DiffuseurLabSerializer
    response_data = {
        'message': assistant_message,
        'quantite_demandee_ml': quantite_demandee_ml,
        'flacon': {
            'id': flacon.id,
            'nom': flacon.nom,
            'contenance_ml': flacon.contenance_ml,
            'prix_unitaire': str(flacon.prix_unitaire),
        } if flacon and afficher_flacon else None,
        'parfums_existants': ParfumLabSerializer(parfums, many=True).data,
        'essences_pre_faites': essences_recommandees,
        'ingredients_sur_mesure': ingredients_recommandes,
        'accessoires': AccessoireLabSerializer(accessoires, many=True).data,
        'diffuseurs': DiffuseurLabSerializer(diffuseurs, many=True).data,
    }

    print(f"<<< [VIEW ia_recommandation] Succes! Reponse finale envoyee: '{assistant_message[:120]}...'\n", flush=True)
    return Response(response_data)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([IARecommandationThrottle])
def ia_conversations(request):
    """
    Retourne l'historique de chat sous forme de liste plate de messages.
    - Utilisateur connecté : tous ses messages, toutes conversations confondues.
    - Utilisateur anonyme : messages de la session en cours uniquement.
    """
    if getattr(request.user, 'is_authenticated', False) and hasattr(request.user, 'client'):
        # Utilisateur connecté : on récupère tous ses messages, toutes conversations
        client = request.user.client
        messages_qs = IAConversationMessage.objects.filter(
            conversation__client=client
        ).order_by('created_at').values('id', 'role', 'content', 'metadata', 'created_at')
        client_label = request.user.first_name or request.user.username
    else:
        # Utilisateur anonyme : messages de la session en cours uniquement
        session_key = request.session.session_key
        if not session_key:
            return Response({'client': 'Anonyme', 'total_messages': 0, 'messages': []})
        try:
            conversation = IAConversation.objects.get(session_key=session_key)
            messages_qs = conversation.messages.order_by('created_at').values('id', 'role', 'content', 'metadata', 'created_at')
        except IAConversation.DoesNotExist:
            return Response({'client': 'Anonyme', 'total_messages': 0, 'messages': []})
        client_label = 'Anonyme'

    messages_list = [
        {
            'id': m['id'],
            'role': m['role'],
            'content': m['content'],
            'metadata': m['metadata'],
            'created_at': m['created_at'].isoformat(),
        }
        for m in messages_qs
    ]

    return Response({
        'client': client_label,
        'total_messages': len(messages_list),
        'messages': messages_list,
    })


@api_view(['DELETE'])
@permission_classes([AllowAny])
@throttle_classes([IARecommandationThrottle])
def vider_resume(request):
    """
    Vide le résumé IA de la conversation en cours.
    - Utilisateur connecté : vide le résumé de sa conversation active (la plus récente).
    - Utilisateur anonyme : vide le résumé de sa session en cours.
    Un utilisateur ne peut vider QUE son propre résumé.
    """
    # --- Identifier la conversation à cibler ---
    if getattr(request.user, 'is_authenticated', False) and hasattr(request.user, 'client'):
        client = request.user.client
        # On prend la conversation la plus récente du client (celle qu'il utilise en ce moment)
        conversation = IAConversation.objects.filter(client=client).order_by('-updated_at').first()
        if not conversation:
            return Response({'detail': 'Aucune conversation trouvée pour cet utilisateur.'},
                            status=status.HTTP_404_NOT_FOUND)
    else:
        # Anonyme : on cherche via la session
        session_key = request.session.session_key
        if not session_key:
            return Response({'detail': 'Aucune session active. Pas de résumé à vider.'},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            conversation = IAConversation.objects.get(session_key=session_key)
        except IAConversation.DoesNotExist:
            return Response({'detail': 'Aucune conversation trouvée pour cette session.'},
                            status=status.HTTP_404_NOT_FOUND)

    # --- Vider le résumé ---
    try:
        summary = conversation.summary
        ancien_resume = summary.summary_text
        summary.summary_text = ''
        summary.save(update_fields=['summary_text', 'updated_at'])
        print(f"[VIDER RESUME] Résumé vidé pour conv #{conversation.id} "
              f"(était: '{ancien_resume[:80]}...')", flush=True)
        return Response({'detail': 'Résumé vidé avec succès. La prochaine réponse de Lia '
                                   'se basera uniquement sur les messages récents.'})
    except IAConversationSummary.DoesNotExist:
        return Response({'detail': 'Aucun résumé existant pour cette conversation.'},
                        status=status.HTTP_404_NOT_FOUND)
