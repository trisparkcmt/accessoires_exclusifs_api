from django.db.models import Count, Q, Case, When, Value, IntegerField


def get_similar_products(instance, model, tag_field='tags', limit=6):
    """
    Sélectionne les produits similaires pour un produit donné :
    - Priorité 1 : Produits ayant les mêmes valeurs de tags (ex: temps=nuit)
    - Priorité 2 : Produits de la même marque (marque)
    - Trier par : Priorité (1 puis 2), nombre de valeurs en commun (décroissant), date de création (-date_creation)
    - Limite : 6 produits max.
    """
    if not instance.pk:
        return model.objects.none()

    # 1. Extraction des sous-tokens (tag_id, valeur) associés au produit
    tokens = []
    if hasattr(instance, 'tags_associes'):
        for ta in instance.tags_associes.all():
            if ta.valeur and str(ta.valeur).strip():
                parts = [p.strip() for p in str(ta.valeur).split(',') if p.strip()]
                for part in parts:
                    tokens.append((ta.tag_id, part))

    # 2. Marque du produit
    marque_val = getattr(instance, 'marque', None)
    has_marque = bool(marque_val and str(marque_val).strip() and str(marque_val).strip().lower() != 'non indiquée')

    if not tokens and not has_marque:
        return model.objects.none()

    qs = model.objects.filter(actif=True).exclude(pk=instance.pk)

    q_tag_valeurs = Q()
    for tag_id, val in tokens:
        q_tag_valeurs |= (Q(tags_associes__tag_id=tag_id) & Q(tags_associes__valeur__icontains=val))

    q_marque = Q(marque__iexact=marque_val.strip()) if has_marque else Q(pk__in=[])

    if tokens:
        qs = qs.filter(q_tag_valeurs | q_marque).annotate(
            communs_valeurs=Count('tags_associes', filter=q_tag_valeurs, distinct=True),
            priority=Case(
                When(communs_valeurs__gt=0, then=Value(1)),
                When(q_marque, then=Value(2)),
                default=Value(3),
                output_field=IntegerField()
            )
        ).order_by('priority', '-communs_valeurs', '-date_creation')
    elif has_marque:
        qs = qs.filter(q_marque).annotate(
            communs_valeurs=Value(0),
            priority=Value(1, output_field=IntegerField())
        ).order_by('-date_creation')

    return qs.distinct()[:limit]


