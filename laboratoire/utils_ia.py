import json
import logging
import os
import re

import requests
from django.conf import settings
from django.db import models
from google import genai
from google.genai import types

from catalogue.models import Parfum, Essence, Accessoire, Flacon, Ingredient, DiffuseurParfum, LotEssence

logger = logging.getLogger(__name__)


def normaliser_reponse_composition(reponse_dict):
    """Normalise la réponse IA pour respecter la logique métier du laboratoire."""
    if not isinstance(reponse_dict, dict):
        return reponse_dict

    # Normalisation de flacon_id (en entier)
    if 'flacon_id' in reponse_dict:
        try:
            reponse_dict['flacon_id'] = int(reponse_dict['flacon_id']) if reponse_dict['flacon_id'] is not None else 0
        except (ValueError, TypeError):
            reponse_dict['flacon_id'] = 0

    essences = []
    vus_essences = set()
    for item in (reponse_dict.get('essences_pre_faites', []) or []):
        # Fallback : si l'IA retourne un simple entier ou une chaîne numérique (ex: [11, 12] ou ["11", "12"])
        if isinstance(item, (int, float, str)) and not isinstance(item, bool):
            try:
                item_id = int(item)
                item = {'id': item_id, 'quantite_ml': 1.0}
                print(f"[NORMALISE] Essence plain ID/string détectée ({item_id}), convertie en dict.", flush=True)
            except (ValueError, TypeError):
                pass

        if not isinstance(item, dict):
            continue

        item_norm = dict(item)
        raw_id = item_norm.get('id')
        try:
            e_id = int(raw_id) if raw_id is not None else None
        except (ValueError, TypeError):
            continue

        if not e_id or e_id in vus_essences:
            continue

        # Vérifier si l'essence existe réellement en BD et est active
        if not Essence.objects.filter(id=e_id, actif=True).exists():
            print(f"[NORMALISE] Essence ID {e_id} ignorée (inexistante en BD ou inactive).", flush=True)
            continue

        vus_essences.add(e_id)
        item_norm['id'] = e_id

        try:
            item_norm['quantite_ml'] = round(float(item_norm.get('quantite_ml', 0) or 0), 2)
        except (TypeError, ValueError):
            item_norm['quantite_ml'] = 0.0

        if item_norm['quantite_ml'] <= 0:
            item_norm['quantite_ml'] = 1.0
        essences.append(item_norm)

    reponse_dict['essences_pre_faites'] = essences
    reponse_dict['ingredients_sur_mesure'] = []

    def _dedup_ids(valeur):
        valeurs = []
        vus = set()
        for item in valeur or []:
            identifiant = item.get('id') if isinstance(item, dict) else item
            try:
                identifiant = int(identifiant) if identifiant is not None else None
            except (ValueError, TypeError):
                continue

            if identifiant is None or identifiant in vus:
                continue
            vus.add(identifiant)
            valeurs.append(identifiant)
        return valeurs

    reponse_dict['accessoires'] = _dedup_ids(reponse_dict.get('accessoires', []))
    reponse_dict['diffuseurs'] = _dedup_ids(reponse_dict.get('diffuseurs', []))
    reponse_dict['parfums_existants_recommandes'] = _dedup_ids(reponse_dict.get('parfums_existants_recommandes', []))
    return reponse_dict


def ajuster_composition_45_percent(reponse_dict):
    """
    Ajuste de façon 100% déterministe en Python les quantités (en ml) d'une composition sur mesure
    pour que leur somme égale EXACTEMENT 45% de la contenance du flacon choisi.
    Les compositions sur mesure doivent être composées uniquement d'essences.
    """
    if not isinstance(reponse_dict, dict):
        return reponse_dict

    reponse_dict = normaliser_reponse_composition(reponse_dict)

    flacon_id = reponse_dict.get('flacon_id', 0)
    essences = reponse_dict.get('essences_pre_faites', []) or []
    ingredients = reponse_dict.get('ingredients_sur_mesure', []) or []

    print(f"\n[ENGINE 45%] Debut de l'ajustement. Flacon ID: {flacon_id}, Essences: {len(essences)}, Ingredients: {len(ingredients)}", flush=True)

    if not flacon_id or not essences:
        print(f"[ENGINE 45%] Pas de creation sur mesure detectee (flacon_id=0 ou vide).", flush=True)
        reponse_dict['flacon_id'] = 0
        reponse_dict['essences_pre_faites'] = []
        reponse_dict['ingredients_sur_mesure'] = []
        return reponse_dict

    try:
        flacon = Flacon.objects.get(id=flacon_id, actif=True)
    except Flacon.DoesNotExist:
        flacon = Flacon.objects.filter(actif=True).order_by('-contenance_ml').first()
        if not flacon:
            print(f"[ENGINE 45%] Aucun flacon actif en base !", flush=True)
            reponse_dict['flacon_id'] = 0
            reponse_dict['essences_pre_faites'] = []
            reponse_dict['ingredients_sur_mesure'] = []
            return reponse_dict
        reponse_dict['flacon_id'] = flacon.id

    volume_cible = round(float(flacon.contenance_ml) * 0.45, 2)
    total_elements = len(essences)
    print(f"[ENGINE 45%] Flacon trouve: {flacon.nom} ({flacon.contenance_ml}ml). Volume cible (45%): {volume_cible}ml", flush=True)

    if total_elements == 0:
        reponse_dict['flacon_id'] = 0
        return reponse_dict

    somme_fournie = 0.0
    for e in essences:
        if isinstance(e, dict):
            somme_fournie += float(e.get('quantite_ml', 0) or 0)

    print(f"[ENGINE 45%] Volume fourni par l'IA: {somme_fournie}ml", flush=True)

    if somme_fournie <= 0:
        part_egale = round(volume_cible / total_elements, 2)
        total_attribue = 0.0

        for idx, e in enumerate(essences):
            if isinstance(e, dict):
                if idx == total_elements - 1:
                    e['quantite_ml'] = round(volume_cible - total_attribue, 2)
                else:
                    e['quantite_ml'] = part_egale
                    total_attribue += part_egale
    else:
        total_ajuste = 0.0
        for idx, e in enumerate(essences):
            if not isinstance(e, dict):
                continue
            if idx == len(essences) - 1:
                q_ajustee = round(volume_cible - total_ajuste, 2)
            else:
                q_orig = float(e.get('quantite_ml', 0) or 0)
                q_ajustee = round((q_orig / somme_fournie) * volume_cible, 2)
                total_ajuste += q_ajustee
            e['quantite_ml'] = q_ajustee

    print(f"[ENGINE 45%] Ajustement termine avec succes. Essences: {essences}", flush=True)
    return reponse_dict


# --- TOOLS PYTHON POUR FUNCTION CALLING ---

# --- TOOLS PYTHON POUR FUNCTION CALLING ---

def tool_rechercher_parfums(notes=None, budget_max=None, contenance_ml=None, **kwargs):
    """Recherche des parfums dans la base de données."""
    print(f"\n[TOOL CALL] tool_rechercher_parfums - Parametres: notes={notes}, budget_max={budget_max}, contenance_ml={contenance_ml}", flush=True)
    base_qs = Parfum.objects.filter(actif=True, stock_quantite__gt=0)
    queryset = base_qs
    has_filter = False

    GENERIC_WORDS = {'personalized', 'personnalise', 'personnalisé', 'perfume', 'parfum', 'custom', 'sur-mesure', 'sur mesure', 'good', 'morning', '50ml', '100ml', 'want', 'like', 'need'}
    cleaned_notes = notes
    if notes and isinstance(notes, str):
        words = [w for w in notes.lower().split() if w not in GENERIC_WORDS and len(w) > 2]
        cleaned_notes = " ".join(words) if words else None

    if cleaned_notes:
        has_filter = True
        query = (
            models.Q(nom__icontains=cleaned_notes) |
            models.Q(notes_tete__icontains=cleaned_notes) |
            models.Q(notes_coeur__icontains=cleaned_notes) |
            models.Q(notes_fond__icontains=cleaned_notes) |
            models.Q(description_courte__icontains=cleaned_notes) |
            models.Q(description_longue__icontains=cleaned_notes) |
            models.Q(description_ia__icontains=cleaned_notes) |
            models.Q(tags__nom__icontains=cleaned_notes)
        )
        queryset = queryset.filter(query)
    if budget_max is not None:
        has_filter = True
        try:
            queryset = queryset.filter(prix_unitaire__lte=float(budget_max))
        except (ValueError, TypeError):
            pass
    if contenance_ml is not None:
        has_filter = True
        try:
            queryset = queryset.filter(contenance_ml=int(contenance_ml))
        except (ValueError, TypeError):
            pass

    if not queryset.exists():
        print(f"[TOOL FALLBACK] tool_rechercher_parfums: Aucun parfum avec filtres. Fallback sur parfums actifs.", flush=True)
        queryset = base_qs.order_by('?')
    elif not has_filter:
        queryset = queryset.order_by('?')

    results = []
    for p in queryset[:8]:
        results.append({
            'id': p.id,
            'nom': p.nom,
            'contenance_ml': p.contenance_ml,
            'prix_unitaire': float(p.prix_unitaire),
            'description': (p.description_ia or p.description_courte or '')[:150],
        })
    print(f"[TOOL RESULT] tool_rechercher_parfums a retourne {len(results)} parfums: {[r['nom'] for r in results]}\n", flush=True)
    return results


def tool_rechercher_essences_et_ingredients(recherche=None, categorie=None, **kwargs):
    """Recherche des essences et ingrédients du laboratoire."""
    print(f"\n[TOOL CALL] tool_rechercher_essences_et_ingredients - Parametres: recherche={recherche}, categorie={categorie}", flush=True)
    essence_ids_en_stock = LotEssence.objects.filter(
        actif=True, stock_ml__gt=0
    ).values_list('essence_id', flat=True).distinct()

    base_essences_qs = Essence.objects.filter(actif=True, prix_par_ml__gt=0, id__in=essence_ids_en_stock)
    base_ingredients_qs = Ingredient.objects.filter(actif=True)

    essences_qs = base_essences_qs
    ingredients_qs = base_ingredients_qs
    has_filter = False

    GENERIC_WORDS = {'personalized', 'personnalise', 'personnalisé', 'perfume', 'parfum', 'custom', 'sur-mesure', 'sur mesure', 'good', 'morning', '50ml', '100ml', 'bottle', 'flacon', 'want', 'like', 'need', 'please'}
    cleaned_recherche = recherche
    if recherche and isinstance(recherche, str):
        words = [w for w in recherche.lower().split() if w not in GENERIC_WORDS and len(w) > 2]
        cleaned_recherche = " ".join(words) if words else None

    if cleaned_recherche:
        has_filter = True
        e_query = (
            models.Q(nom__icontains=cleaned_recherche) |
            models.Q(notes_tete__icontains=cleaned_recherche) |
            models.Q(notes_coeur__icontains=cleaned_recherche) |
            models.Q(notes_fond__icontains=cleaned_recherche) |
            models.Q(description__icontains=cleaned_recherche)|
            models.Q(description_ia__icontains=cleaned_recherche)
        )
        essences_qs = essences_qs.filter(e_query)
        ingredients_qs = ingredients_qs.filter(models.Q(nom__icontains=cleaned_recherche) | models.Q(description__icontains=cleaned_recherche))

    if categorie:
        has_filter = True
        essences_qs = essences_qs.filter(categorie__icontains=categorie)

    if not essences_qs.exists():
        print(f"[TOOL FALLBACK] tool_rechercher_essences_et_ingredients: Aucune essence avec filtres. Fallback sur toutes les essences dispo.", flush=True)
        essences_qs = base_essences_qs.order_by('?')
    elif not has_filter:
        essences_qs = essences_qs.order_by('?')

    if not ingredients_qs.exists():
        ingredients_qs = base_ingredients_qs.order_by('?')
    elif not has_filter:
        ingredients_qs = ingredients_qs.order_by('?')

    essences_res = []
    for e in essences_qs[:8]:
        active_lot = LotEssence.objects.filter(essence=e, actif=True).first()
        prods_finis = [
            {'id': pf.id, 'taille_ml': pf.taille_ml, 'prix': float(pf.prix_actuel)}
            for pf in e.produits_finis.filter(actif=True, prix__gt=0)
        ]
        essences_res.append({
            'id': e.id,
            'initial_lot_id': active_lot.id if active_lot else None,
            'nom': e.nom,
            'marque': e.marque,
            'categorie': e.categorie,
            'prix_par_ml': float(e.prix_par_ml),
            'description': (e.description_ia or e.description or '')[:100],
            'produits_finis': prods_finis,
        })

    ingredients_res = []
    for i in ingredients_qs[:6]:
        ingredients_res.append({
            'id': i.id,
            'nom': i.nom,
            'prix_par_ml': float(i.prix_par_ml),
        })

    print(f"[TOOL RESULT] tool_rechercher_essences_et_ingredients a retourne {len(essences_res)} essences et {len(ingredients_res)} ingredients.\n", flush=True)
    return {'essences': essences_res, 'ingredients': ingredients_res}


def tool_obtenir_flacons_disponibles(contenance_souhaitee_ml=None, **kwargs):
    """Obtient les flacons disponibles en base."""
    print(f"\n[TOOL CALL] tool_obtenir_flacons_disponibles - Parametres: contenance_souhaitee_ml={contenance_souhaitee_ml}", flush=True)
    qs = Flacon.objects.filter(actif=True)
    if contenance_souhaitee_ml:
        try:
            qs_exact = qs.filter(contenance_ml=int(contenance_souhaitee_ml))
            if qs_exact.exists():
                qs = qs_exact
        except (ValueError, TypeError):
            pass

    flacons = []
    for f in qs[:5]:
        flacons.append({
            'id': f.id,
            'nom': f.nom,
            'contenance_ml': f.contenance_ml,
            'prix_unitaire': float(f.prix_unitaire),
        })
    print(f"[TOOL RESULT] tool_obtenir_flacons_disponibles a retourne {len(flacons)} flacons: {[f['nom'] for f in flacons]}\n", flush=True)
    return flacons


def tool_rechercher_accessoires_et_diffuseurs(recherche=None, budget_max=None, **kwargs):
    """Recherche des accessoires ou diffuseurs d'ambiance."""
    print(f"\n[TOOL CALL] tool_rechercher_accessoires_et_diffuseurs - Parametres: recherche={recherche}, budget_max={budget_max}", flush=True)
    base_acc = Accessoire.objects.filter(actif=True)
    base_diff = DiffuseurParfum.objects.filter(actif=True, stock_quantite__gt=0)

    acc_qs = base_acc
    diff_qs = base_diff

    if recherche:
        acc_qs = acc_qs.filter(models.Q(nom__icontains=recherche) | models.Q(description_courte__icontains=recherche))
        diff_qs = diff_qs.filter(models.Q(nom__icontains=recherche) | models.Q(description__icontains=recherche))
        if not acc_qs.exists():
            acc_qs = base_acc.order_by('?')
        if not diff_qs.exists():
            diff_qs = base_diff.order_by('?')
    else:
        acc_qs = acc_qs.order_by('?')
        diff_qs = diff_qs.order_by('?')

    if budget_max:
        try:
            acc_qs = acc_qs.filter(prix_unitaire__lte=float(budget_max))
            diff_qs = diff_qs.filter(prix_unitaire__lte=float(budget_max))
        except (ValueError, TypeError):
            pass

    accessoires_res = [{'id': a.id, 'nom': a.nom, 'prix_unitaire': float(a.prix_unitaire)} for a in acc_qs[:4]]
    diffuseurs_res = []
    for d in diff_qs[:4]:
        prix = float(d.prix_promotionnel if d.prix_promotionnel is not None else d.prix_unitaire)
        diffuseurs_res.append({'id': d.id, 'nom': d.nom, 'prix': prix})

    print(f"[TOOL RESULT] tool_rechercher_accessoires_et_diffuseurs a retourne {len(accessoires_res)} accessoires et {len(diffuseurs_res)} diffuseurs.\n", flush=True)
    return {'accessoires': accessoires_res, 'diffuseurs': diffuseurs_res}


TOOLS_REGISTRY = {
    'rechercher_parfums': tool_rechercher_parfums,
    'rechercher_essences_et_ingredients': tool_rechercher_essences_et_ingredients,
    'obtenir_flacons_disponibles': tool_obtenir_flacons_disponibles,
    'rechercher_accessoires_et_diffuseurs': tool_rechercher_accessoires_et_diffuseurs,
}

OLLAMA_TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "rechercher_parfums",
            "description": "Recherche UNIQUEMENT des parfums pret-a-l'emploi existants (produits commerciaux deja faits). NE PAS utiliser pour des creations sur mesure ou des compositions personnalisees.",
            "parameters": {
                "type": "object",
                "properties": {
                    "notes": {"type": "string", "description": "Notes olfactives ou mot-clé (ex: floral, boisé, vanille, ambré, frais)"},
                    "budget_max": {"type": "number", "description": "Budget maximum en FCFA pour le parfum"},
                    "contenance_ml": {"type": "number", "description": "Contenance souhaitée en ml"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rechercher_essences_et_ingredients",
            "description": "Recherche des essences prefaites et des ingredients olfactifs pour fabriquer un parfum personnalisé sur-mesure (composition, melange unique, creation a partir de notes brutes).",
            "parameters": {
                "type": "object",
                "properties": {
                    "recherche": {"type": "string", "description": "Mot-clé ou note olfactive (ex: jasmin, patchouli, santal)"},
                    "categorie": {"type": "string", "description": "Catégorie (super_premium, premium, high)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "obtenir_flacons_disponibles",
            "description": "Obtient les flacons disponibles dans le catalogue avec leurs contenances en ml et leurs prix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contenance_souhaitee_ml": {"type": "number", "description": "Contenance souhaitée du flacon en ml"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rechercher_accessoires_et_diffuseurs",
            "description": "Recherche les accessoires ou diffuseurs d'ambiance pour proposer une vente complémentaire (cross-selling).",
            "parameters": {
                "type": "object",
                "properties": {
                    "recherche": {"type": "string", "description": "Type de produit (ex: diffuseur, vaporisateur, coffret)"},
                    "budget_max": {"type": "number", "description": "Budget maximum en FCFA"}
                }
            }
        }
    }
]


def get_catalogue_context():
    """Récupère et formate le catalogue pour l'IA (Fallback)"""
    parfums = Parfum.objects.filter(actif=True).values('id', 'nom', 'contenance_ml', 'description_ia', 'prix_unitaire')
    essence_ids_en_stock = LotEssence.objects.filter(
        actif=True, stock_ml__gt=0
    ).values_list('essence_id', flat=True).distinct()
    essences = Essence.objects.filter(
        actif=True, prix_par_ml__gt=0, id__in=essence_ids_en_stock
    ).values('id', 'nom', 'description_ia', 'prix_par_ml', 'categorie')
    ingredients = Ingredient.objects.filter(actif=True).values('id', 'nom', 'prix_par_ml')
    accessoires = Accessoire.objects.filter(actif=True).values('id', 'nom', 'description_courte', 'prix_unitaire')
    flacons = Flacon.objects.filter(actif=True).values('id', 'nom', 'contenance_ml', 'prix_unitaire')
    diffuseurs = DiffuseurParfum.objects.filter(actif=True, stock_quantite__gt=0).values('id', 'nom', 'description', 'prix_unitaire', 'prix_promotionnel')

    context = "Catalogue actuel de la parfumerie :\n\n"
    context += "=== PARFUMS ===\n"
    for p in parfums:
        context += f"- ID: {p['id']}, Nom: {p['nom']}, Contenance: {p['contenance_ml']}ml, Prix: {p['prix_unitaire']} FCFA\n"
    context += "\n=== ESSENCES PRÉFABRIQUÉES ===\n"
    for e in essences:
        context += f"- ID: {e['id']}, Nom: {e['nom']}, Catégorie: {e['categorie']}, Prix/ml: {e['prix_par_ml']} FCFA\n"
    context += "\n=== INGRÉDIENTS ===\n"
    for i in ingredients:
        context += f"- ID: {i['id']}, Nom: {i['nom']}, Prix/ml: {i['prix_par_ml']} FCFA\n"
    context += "\n=== FLACONS ===\n"
    for f in flacons:
        context += f"- ID: {f['id']}, Nom: {f['nom']}, Contenance: {f['contenance_ml']}ml, Prix: {f['prix_unitaire']} FCFA\n"
    context += "\n=== ACCESSOIRES ===\n"
    for a in accessoires:
        context += f"- ID: {a['id']}, Nom: {a['nom']}, Prix: {a['prix_unitaire']} FCFA\n"
    context += "\n=== DIFFUSEURS ===\n"
    for d in diffuseurs:
        prix = d['prix_promotionnel'] if d.get('prix_promotionnel') is not None else d['prix_unitaire']
        context += f"- ID: {d['id']}, Nom: {d['nom']}, Prix: {prix} FCFA\n"
    return context


def validate_ia_response_schema(reponse):
    required_keys = {
        'message',
        'quantite_demandee_ml',
        'budget_max_fcfa',
        'flacon_id',
        'essences_pre_faites',
        'ingredients_sur_mesure',
        'parfums_existants_recommandes',
        'accessoires',
    }
    if not isinstance(reponse, dict):
        return False, 'La réponse n’est pas un objet JSON.'

    missing = required_keys - set(reponse.keys())
    if missing:
        return False, f'Clés manquantes dans la réponse JSON : {sorted(missing)}.'

    if not isinstance(reponse.get('message'), str):
        return False, 'Le champ message doit être une chaîne de caractères.'

    if not isinstance(reponse.get('essences_pre_faites'), list):
        return False, 'Le champ essences_pre_faites doit être une liste.'

    if not isinstance(reponse.get('ingredients_sur_mesure'), list):
        return False, 'Le champ ingredients_sur_mesure doit être une liste.'

    if not isinstance(reponse.get('parfums_existants_recommandes'), list):
        return False, 'Le champ parfums_existants_recommandes doit être une liste.'

    if 'diffuseurs' in reponse and not isinstance(reponse.get('diffuseurs'), list):
        return False, 'Le champ diffuseurs doit être une liste.'

    return True, None


def _extract_json_from_text(text):
    if not text or not isinstance(text, str):
        return None

    cleaned = text.strip()

    # Nettoyage des balises markdown ```json ... ```
    if '```' in cleaned:
        cleaned = re.sub(r'```(?:json)?\s*', '', cleaned)
        cleaned = cleaned.replace('```', '').strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Extraction de la première accolade { à la dernière }
    first = cleaned.find('{')
    last = cleaned.rfind('}')
    if first != -1 and last != -1 and last > first:
        candidate = cleaned[first:last + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Nettoyage des virgules traînantes (trailing commas: ,} et ,])
            candidate_fixed = re.sub(r',\s*([\}\]])', r'\1', candidate)
            try:
                return json.loads(candidate_fixed)
            except json.JSONDecodeError:
                pass
    return None


def meubler_contexte_historique(history=None, client_info=None, resume=None):
    """
    Construit le contexte à injecter dans le system prompt.
    Utilise le résumé (resume) si disponible, sinon se rabat sur l'historique brut (history).
    """
    client_context = ""
    if client_info:
        prenom = client_info.get('prenom', '').strip()
        nom_complet = client_info.get('nom', '').strip()
        email = client_info.get('email', '').strip()
        # Utiliser le prénom seul si dispo, sinon le nom complet
        appellation = prenom if prenom else nom_complet
        if appellation:
            client_context = (
                f"Le client connecté s'appelle {appellation} (nom complet : {nom_complet}, email : {email}). "
                f"Adresse-toi à lui par son prénom '{appellation}' de manière chaleureuse et personnalisée.\n"
            )

    contexte_str = ""
    if resume and resume.strip():
        # Utiliser le résumé IA condensé — bien plus court qu'un historique complet
        contexte_str = f"Résumé de l'historique de ce client :\n{resume.strip()}\n\n"
    elif history:
        # Fallback : historique brut des derniers messages (si pas encore de résumé)
        contexte_str = "Historique des échanges récents avec ce client :\n"
        for msg in history:
            role_label = 'Client' if msg['role'] == 'user' else 'Assistant'
            contexte_str += f"- {role_label} : {msg['content']}\n"
        contexte_str += "\n"

    return f"{client_context}{contexte_str}"


def generer_resume_conversation(messages_recents, resume_existant=''):
    """
    Génère un résumé condensé de la conversation en appelant Ollama ou Gemini.
    Ce résumé est stocké en BD et réutilisé dans les prochains prompts à la place
    de l'historique complet, ce qui économise des tokens et accélère les réponses.

    Returns:
        str: Le nouveau résumé, ou le résumé existant en cas d'erreur.
    """
    if not messages_recents:
        return resume_existant or ''

    provider = os.environ.get('LLM_PROVIDER', getattr(settings, 'LLM_PROVIDER', 'gemini')).lower()

    # Construire le texte de la conversation à résumer
    conv_text = ""
    for msg in messages_recents:
        role_label = 'Client' if msg['role'] == 'user' else 'Conseiller'
        conv_text += f"{role_label}: {msg['content']}\n"

    contexte_existant = f"Résumé précédent (à mettre à jour) :\n{resume_existant}\n\n" if resume_existant else ""

    prompt_resume = (
        f"{contexte_existant}"
        f"Nouveaux échanges :\n{conv_text}\n"
        "Génère un résumé factuel et concis (3 à 5 phrases maximum) de ce que le client a demandé, "
        "ses préférences olfactives, son budget si mentionné, et les produits ou compositions recommandés. "
        "Ne mets pas de titre, écris directement le résumé en français."
    )

    try:
        if provider == 'ollama':
            ollama_url = os.environ.get('OLLAMA_URL', getattr(settings, 'OLLAMA_URL', 'http://127.0.0.1:11434')).rstrip('/')
            model_name = os.environ.get('OLLAMA_MODEL', getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:3b'))
            payload = {
                'model': model_name,
                'messages': [
                    {'role': 'system', 'content': 'Tu es un assistant qui génère des résumés courts et factuels de conversations.'},
                    {'role': 'user', 'content': prompt_resume},
                ],
                'temperature': 0.1,
                'stream': False,
            }
            resp = requests.post(
                f"{ollama_url}/v1/chat/completions",
                json=payload,
                timeout=(10, 60),
            )
            resp.raise_for_status()
            data = resp.json()
            nouveau_resume = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            print(f"[RESUME IA] Nouveau résumé généré (Ollama): '{nouveau_resume[:100]}...'", flush=True)
            return nouveau_resume if nouveau_resume else resume_existant

        elif provider == 'groq':
            groq_api_key = os.environ.get('GROQ_API_KEY') or getattr(settings, 'GROQ_API_KEY', None)
            groq_model = os.environ.get('GROQ_MODEL', getattr(settings, 'GROQ_MODEL', 'qwen/qwen3.8-27b'))
            if not groq_api_key:
                print(f"[RESUME IA] Clé GROQ_API_KEY manquante.", flush=True)
                return resume_existant
            payload = {
                'model': groq_model,
                'messages': [
                    {'role': 'system', 'content': 'Tu es un assistant qui génère des résumés courts et factuels de conversations.'},
                    {'role': 'user', 'content': prompt_resume},
                ],
                'temperature': 0.1,
            }
            session = requests.Session()
            resp = session.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {groq_api_key}',
                    'Content-Type': 'application/json',
                    'Connection': 'close',
                },
                json=payload,
                timeout=(10, 30),
            )
            resp.raise_for_status()
            data = resp.json()
            nouveau_resume = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            print(f"[RESUME IA] Nouveau résumé généré (Groq/{groq_model}): '{nouveau_resume[:100]}...'", flush=True)
            return nouveau_resume if nouveau_resume else resume_existant

        elif provider in ('huggingface', 'hf'):
            hf_api_key = os.environ.get('HUGGINGFACE_API_KEY') or os.environ.get('HF_API_KEY') or getattr(settings, 'HUGGINGFACE_API_KEY', None)
            hf_model = os.environ.get('HUGGINGFACE_MODEL') or getattr(settings, 'HUGGINGFACE_MODEL', 'Qwen/Qwen2.5-72B-Instruct')
            if not hf_api_key:
                print(f"[RESUME IA] Clé HUGGINGFACE_API_KEY manquante.", flush=True)
                return resume_existant
            hf_urls = [
                'https://router.huggingface.co/v1/chat/completions',
                'https://api-inference.huggingface.co/v1/chat/completions',
            ]
            payload = {
                'model': hf_model,
                'messages': [
                    {'role': 'system', 'content': 'Tu es un assistant qui génère des résumés courts et factuels de conversations.'},
                    {'role': 'user', 'content': prompt_resume},
                ],
                'temperature': 0.1,
            }
            hf_resume = None
            hf_error = None
            for hf_url in hf_urls:
                try:
                    resp = requests.post(
                        hf_url,
                        headers={
                            'Authorization': f'Bearer {hf_api_key}',
                            'Content-Type': 'application/json',
                        },
                        json=payload,
                        timeout=(10, 30),
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    hf_resume = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                    print(f"[RESUME IA] Nouveau résumé généré (HuggingFace/{hf_model}): '{hf_resume[:100]}...'", flush=True)
                    break
                except Exception as hf_err:
                    hf_error = hf_err
                    print(f"[RESUME IA] HuggingFace ({hf_url}) inaccessible: {hf_err}", flush=True)
            if hf_resume:
                return hf_resume
            # Fallback sur Gemini si HuggingFace est inaccessible
            print(f"[RESUME IA] HuggingFace inaccessible, fallback sur Gemini pour le résumé...", flush=True)
            api_key_fb = os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', None)
            gemini_model_fb = os.environ.get('GEMINI_MODEL', getattr(settings, 'GEMINI_MODEL', 'gemini-3.6-flash'))
            if api_key_fb:
                try:
                    client_gemini_fb = genai.Client(api_key=api_key_fb)
                    response_fb = _generate_gemini_with_fallback(
                        client=client_gemini_fb,
                        contents=prompt_resume,
                        config=types.GenerateContentConfig(temperature=0.1),
                        requested_model=gemini_model_fb,
                    )
                    nouveau_resume_fb = response_fb.text.strip()
                    print(f"[RESUME IA] Résumé généré via Gemini (fallback HF): '{nouveau_resume_fb[:100]}...'", flush=True)
                    return nouveau_resume_fb if nouveau_resume_fb else resume_existant
                except Exception as gem_fb_err:
                    print(f"[RESUME IA] Fallback Gemini a aussi échoué: {gem_fb_err}", flush=True)
            return resume_existant

        else:
            api_key = os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', None)
            gemini_model = os.environ.get('GEMINI_MODEL', getattr(settings, 'GEMINI_MODEL', 'gemini-3.6-flash'))
            if not api_key:
                return resume_existant
            client_gemini = genai.Client(api_key=api_key)
            response = _generate_gemini_with_fallback(
                client=client_gemini,
                contents=prompt_resume,
                config=types.GenerateContentConfig(temperature=0.1),
                requested_model=gemini_model,
            )
            nouveau_resume = response.text.strip()
            print(f"[RESUME IA] Nouveau résumé généré (Gemini/{gemini_model}): '{nouveau_resume[:100]}...'", flush=True)
            return nouveau_resume if nouveau_resume else resume_existant

    except Exception as e:
        print(f"[RESUME IA] Erreur lors de la génération du résumé (non bloquant): {str(e)}", flush=True)
        return resume_existant  # On garde l'ancien résumé en cas d'erreur


def _generate_gemini_with_fallback(client, contents, config, requested_model=None):
    """
    Appelle l'API Gemini avec le modèle demandé. Si le modèle retourne une erreur 404 (non disponible/déprécié),
    tente automatiquement d'autres modèles compatibles (gemini-3.6-flash, gemini-flash-latest, etc.)
    ou découvre dynamiquement la liste des modèles actifs autorisés sur l'API Key auprès de Google AI Studio.
    """
    default_requested = requested_model or os.environ.get('GEMINI_MODEL') or getattr(settings, 'GEMINI_MODEL', 'gemini-3.6-flash')
    candidates = [
        default_requested,
        'gemini-3.6-flash',
        'gemini-flash-latest',
        'gemini-2.5-flash',
        'gemini-1.5-flash',
        'gemini-2.0-flash',
    ]
    seen = set()
    models_to_try = [m for m in candidates if m and not (m in seen or seen.add(m))]

    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            print(f"[GEMINI SUCCESS] Appel réussi avec le modèle '{model_name}'.", flush=True)
            return response
        except Exception as e:
            err_str = str(e).lower()
            if '404' in err_str or 'not_found' in err_str or 'no longer available' in err_str or 'not found' in err_str:
                print(f"[GEMINI FALLBACK] Modèle '{model_name}' non disponible (404). Tentative avec le modèle suivant...", flush=True)
                last_error = e
                continue
            raise e

    # Si tous les candidats prédéfinis échouent en 404, découvrir dynamiquement les modèles actifs sur Google AI Studio
    try:
        print("[GEMINI FALLBACK DYNAMIQUE] Recherche automatique des modèles actifs sur AI Studio...", flush=True)
        available_models = list(client.models.list())
        for m in available_models:
            m_name = getattr(m, 'name', '') or str(m)
            m_clean = m_name.replace('models/', '')
            if 'flash' in m_clean.lower() and m_clean not in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=m_clean,
                        contents=contents,
                        config=config,
                    )
                    print(f"[GEMINI DYNAMIC SUCCESS] Appel réussi avec modèle découvert '{m_clean}'.", flush=True)
                    return response
                except Exception:
                    pass
    except Exception:
        pass

    if last_error:
        raise last_error
    raise Exception("Aucun modèle Gemini valide disponible sur cette clé API.")




def _appel_provider_ollama(prompt_utilisateur, system_prompt):
    ollama_url = os.environ.get('OLLAMA_URL', getattr(settings, 'OLLAMA_URL', 'http://127.0.0.1:11434')).rstrip('/')
    model_name = os.environ.get('OLLAMA_MODEL', getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:3b'))

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': f"Demande du client (RÉPONDS STRICTEMENT DANS LA MÊME LANGUE QUE CETTE DEMANDE) : {prompt_utilisateur}"}
    ]

    llm_payload = {
        'model': model_name,
        'messages': messages,
        'tools': OLLAMA_TOOLS_DEFINITIONS,
        'temperature': 0.2,
        'stream': False,
    }

    print(f"[IA-RECOMMANDATION] Ollama: Envoi du premier appel (URL: {ollama_url}/v1/chat/completions)...", flush=True)

    response = requests.post(
        f"{ollama_url}/v1/chat/completions",
        json=llm_payload,
        timeout=(20, 180),
    )
    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict) and 'choices' in data and data['choices']:
        choice = data['choices'][0]
        message_obj = choice.get('message', {})
        tool_calls = message_obj.get('tool_calls')

        if tool_calls:
            print(f"[IA-RECOMMANDATION] Ollama a demandé des outils: {[t.get('function', {}).get('name') for t in tool_calls]}", flush=True)
            messages.append(message_obj)

            for tool_call in tool_calls:
                fn_name = tool_call.get('function', {}).get('name')
                raw_args = tool_call.get('function', {}).get('arguments', '{}')
                try:
                    fn_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    fn_args = {}

                tool_result = TOOLS_REGISTRY[fn_name](**fn_args) if fn_name in TOOLS_REGISTRY else {"error": f"Outil inconnu : {fn_name}"}

                messages.append({
                    'role': 'tool',
                    'tool_call_id': tool_call.get('id', 'call_1'),
                    'content': json.dumps(tool_result, ensure_ascii=False)
                })

            messages.append({
                'role': 'user',
                'content': "Toutes les recherches d'outils ont été effectuées avec succès. Génère MAINTENANT la réponse finale sous la forme d'un objet JSON strict respectant le schéma demandé. Ne fais plus d'appels d'outils."
            })

            second_payload = {
                'model': model_name,
                'messages': messages,
                'response_format': {'type': 'json_object'},
                'temperature': 0.2,
                'stream': False,
            }
            second_resp = requests.post(
                f"{ollama_url}/v1/chat/completions",
                json=second_payload,
                timeout=(20, 180),
            )
            second_resp.raise_for_status()
            second_data = second_resp.json()
            if 'choices' in second_data and second_data['choices']:
                return second_data['choices'][0].get('message', {}).get('content')
        else:
            return message_obj.get('content')
    return response.text


def _appel_provider_groq(prompt_utilisateur, system_prompt):
    groq_api_key = os.environ.get('GROQ_API_KEY') or getattr(settings, 'GROQ_API_KEY', None)
    groq_model = os.environ.get('GROQ_MODEL', getattr(settings, 'GROQ_MODEL', 'deepseek-r1-distill-llama-70b'))

    if not groq_api_key:
        raise ValueError("Clé API Groq manquante (GROQ_API_KEY).")

    groq_headers = {
        'Authorization': f'Bearer {groq_api_key}',
        'Content-Type': 'application/json',
        'Connection': 'close',
    }

    def _post_groq(payload, retries=2):
        for attempt in range(1, retries + 1):
            try:
                resp = requests.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers=groq_headers,
                    json=payload,
                    timeout=(15, 60),
                )
                if resp.status_code in (500, 502, 503, 504, 429) and attempt < retries:
                    print(f"[IA-RECOMMANDATION] Groq retourné HTTP {resp.status_code}, tentative {attempt}/{retries}...", flush=True)
                    import time
                    time.sleep(0.8 * attempt)
                    continue
                return resp
            except (requests.exceptions.RequestException, Exception) as err:
                print(f"[IA-RECOMMANDATION] Tentative Groq {attempt}/{retries} échouée: {err}", flush=True)
                if attempt == retries:
                    raise
                import time
                time.sleep(0.8 * attempt)

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': f"Demande du client (RÉPONDS STRICTEMENT DANS LA MÊME LANGUE QUE CETTE DEMANDE) : {prompt_utilisateur}"}
    ]

    llm_payload = {
        'model': groq_model,
        'messages': messages,
        'tools': OLLAMA_TOOLS_DEFINITIONS,
        'tool_choice': 'auto',
        'parallel_tool_calls': True,
        'temperature': 0.2,
    }

    print(f"[IA-RECOMMANDATION] Groq: Envoi du premier appel (modele: {groq_model})...", flush=True)
    response = _post_groq(llm_payload)

    # Si Groq renvoie HTTP 400 ou 422 (ex: modèle comme DeepSeek R1 qui ne supporte pas Function Calling),
    # fallback immédiat sur l'injection de catalogue directe !
    if response.status_code in (400, 422):
        print(f"[IA-RECOMMANDATION] Groq ({groq_model}) HTTP {response.status_code} avec tools (modèle sans support tool calling). Fallback injection catalogue...", flush=True)
        catalogue_fb = get_catalogue_context()
        contents_fb = f"{system_prompt}\n\nCatalogue disponible :\n{catalogue_fb}\n\nDemande du client (RÉPONDS STRICTEMENT DANS LA MÊME LANGUE QUE CETTE DEMANDE) : {prompt_utilisateur}"
        fallback_payload = {
            'model': groq_model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': contents_fb}
            ],
            'response_format': {'type': 'json_object'},
            'temperature': 0.2,
        }
        response = _post_groq(fallback_payload)
        if response.status_code in (400, 422):
            print(f"[IA-RECOMMANDATION] Groq: Fallback sans response_format...", flush=True)
            fallback_payload.pop('response_format', None)
            response = _post_groq(fallback_payload)

    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict) and 'choices' in data and data['choices']:
        choice = data['choices'][0]
        message_obj = choice.get('message', {})
        tool_calls = message_obj.get('tool_calls')

        if tool_calls:
            print(f"[IA-RECOMMANDATION] Groq a demandé des outils: {[t.get('function', {}).get('name') for t in tool_calls]}", flush=True)
            messages.append({
                'role': 'assistant',
                'content': message_obj.get('content') or None,
                'tool_calls': tool_calls,
            })

            for tool_call in tool_calls:
                fn_name = tool_call.get('function', {}).get('name')
                raw_args = tool_call.get('function', {}).get('arguments', '{}')
                try:
                    fn_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    fn_args = {}

                tool_result = TOOLS_REGISTRY[fn_name](**fn_args) if fn_name in TOOLS_REGISTRY else {"error": f"Outil inconnu : {fn_name}"}

                messages.append({
                    'role': 'tool',
                    'tool_call_id': tool_call.get('id', 'call_1'),
                    'content': json.dumps(tool_result, ensure_ascii=False)
                })

            messages.append({
                'role': 'user',
                'content': "Toutes les recherches d'outils ont été effectuées avec succès. Génère MAINTENANT la réponse finale sous la forme d'un objet JSON strict respectant le schéma demandé. Ne fais plus d'appels d'outils."
            })

            second_payload = {
                'model': groq_model,
                'messages': messages,
                'response_format': {'type': 'json_object'},
                'temperature': 0.2,
            }
            second_resp = _post_groq(second_payload)
            if second_resp.status_code == 200:
                second_data = second_resp.json()
                return second_data['choices'][0].get('message', {}).get('content')
            else:
                try:
                    err_json = second_resp.json()
                    failed_gen = err_json.get('error', {}).get('failed_generation')
                    if failed_gen:
                        return failed_gen
                except Exception:
                    pass
                second_resp.raise_for_status()
        else:
            return message_obj.get('content')
    return response.text


def _appel_provider_huggingface(prompt_utilisateur, system_prompt):
    hf_api_key = os.environ.get('HUGGINGFACE_API_KEY') or os.environ.get('HF_API_KEY') or getattr(settings, 'HUGGINGFACE_API_KEY', None)
    hf_model = os.environ.get('HUGGINGFACE_MODEL') or getattr(settings, 'HUGGINGFACE_MODEL', 'Qwen/Qwen2.5-72B-Instruct')

    if not hf_api_key:
        raise ValueError("Clé API Hugging Face manquante.")

    hf_headers = {
        'Authorization': f'Bearer {hf_api_key}',
        'Content-Type': 'application/json',
    }

    def _post_hf(payload, retries=2):
        urls = ['https://router.huggingface.co/v1/chat/completions']
        last_resp = None
        for url in urls:
            for attempt in range(1, retries + 1):
                try:
                    resp = requests.post(
                        url,
                        headers=hf_headers,
                        json=payload,
                        timeout=(15, 60),
                    )
                    if resp.status_code in (500, 502, 503, 504) and attempt < retries:
                        import time
                        time.sleep(0.8 * attempt)
                        continue
                    if resp.status_code in (200, 400, 422, 429):
                        return resp
                    last_resp = resp
                except Exception as err:
                    if attempt == retries:
                        last_resp = err
                    import time
                    time.sleep(0.8 * attempt)
        if isinstance(last_resp, requests.Response):
            return last_resp
        raise last_resp or Exception("Impossible de contacter l'API HuggingFace.")

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': f"Demande du client (RÉPONDS STRICTEMENT DANS LA MÊME LANGUE QUE CETTE DEMANDE) : {prompt_utilisateur}"}
    ]

    llm_payload = {
        'model': hf_model,
        'messages': messages,
        'tools': OLLAMA_TOOLS_DEFINITIONS,
        'tool_choice': 'auto',
        'temperature': 0.2,
    }

    print(f"[IA-RECOMMANDATION] Hugging Face: Envoi du premier appel (modele: {hf_model})...", flush=True)
    response = _post_hf(llm_payload)

    if response.status_code in (400, 422):
        print(f"[IA-RECOMMANDATION] HuggingFace tools non supportés directement, fallback avec injection du catalogue...", flush=True)
        catalogue_fb = get_catalogue_context()
        contents_hf = f"{system_prompt}\n\nCatalogue disponible :\n{catalogue_fb}\n\nDemande du client (RÉPONDS STRICTEMENT DANS LA MÊME LANGUE QUE CETTE DEMANDE) : {prompt_utilisateur}"
        llm_payload = {
            'model': hf_model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': contents_hf}
            ],
            'response_format': {'type': 'json_object'},
            'temperature': 0.2,
        }
        response = _post_hf(llm_payload)

    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict) and 'choices' in data and data['choices']:
        choice = data['choices'][0]
        message_obj = choice.get('message', {})
        tool_calls = message_obj.get('tool_calls')

        if tool_calls:
            messages.append({
                'role': 'assistant',
                'content': message_obj.get('content') or None,
                'tool_calls': tool_calls,
            })
            for tool_call in tool_calls:
                fn_name = tool_call.get('function', {}).get('name')
                raw_args = tool_call.get('function', {}).get('arguments', '{}')
                try:
                    fn_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    fn_args = {}
                tool_result = TOOLS_REGISTRY[fn_name](**fn_args) if fn_name in TOOLS_REGISTRY else {"error": f"Outil inconnu : {fn_name}"}
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tool_call.get('id', 'call_1'),
                    'content': json.dumps(tool_result, ensure_ascii=False)
                })

            messages.append({
                'role': 'user',
                'content': "Toutes les recherches d'outils ont été effectuées avec succès. Génère MAINTENANT la réponse finale sous la forme d'un objet JSON strict respectant le schéma demandé. Ne fais plus d'appels d'outils."
            })
            second_payload = {
                'model': hf_model,
                'messages': messages,
                'response_format': {'type': 'json_object'},
                'temperature': 0.2,
            }
            second_resp = _post_hf(second_payload)
            second_resp.raise_for_status()
            second_data = second_resp.json()
            return second_data['choices'][0].get('message', {}).get('content')
        else:
            return message_obj.get('content')
    return response.text


def _appel_provider_gemini(prompt_utilisateur, system_prompt):
    api_key = os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', None)
    gemini_model = os.environ.get('GEMINI_MODEL', getattr(settings, 'GEMINI_MODEL', 'gemini-3.6-flash'))

    if not api_key:
        raise ValueError("Clé API Gemini manquante (GEMINI_API_KEY).")

    print(f"[IA-RECOMMANDATION] Gemini: Envoi de la requête (modèle cible: {gemini_model})...", flush=True)
    client = genai.Client(api_key=api_key)
    catalogue_fallback = get_catalogue_context()
    contents = f"{system_prompt}\n\nCatalogue disponible :\n{catalogue_fallback}\n\nDemande du client (RÉPONDS STRICTEMENT DANS LA MÊME LANGUE QUE CETTE DEMANDE) : {prompt_utilisateur}"

    response = _generate_gemini_with_fallback(
        client=client,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type='application/json',
        ),
        requested_model=gemini_model,
    )
    return response.text.strip()


def demander_recommandation_ia(prompt_utilisateur, history=None, client_info=None, resume=None):
    """
    Envoie le prompt à l'IA avec Function Calling (Tools API) et ajuste automatiquement
    la règle des 45% en Python de façon déterministe.

    - resume : résumé condensé de l'historique (stocké en BD). Si fourni, remplace le full history.
    - history : fallback — les derniers messages bruts si aucun résumé n'existe encore.
    """
    provider = os.environ.get('LLM_PROVIDER', getattr(settings, 'LLM_PROVIDER', 'gemini')).lower()
    contexte_client_et_historique = meubler_contexte_historique(history=history, client_info=client_info, resume=resume)

    print(f"\n[IA-RECOMMANDATION] Nouveau prompt recu: '{prompt_utilisateur}' (Provider: {provider})", flush=True)
    if resume:
        print(f"[IA-RECOMMANDATION] Contexte: résumé existant ({len(resume)} chars)", flush=True)
    else:
        print(f"[IA-RECOMMANDATION] Contexte: {len(history or [])} messages bruts (pas encore de résumé)", flush=True)

    system_prompt = f"""Tu es un expert parfumeur et conseiller de vente pour la boutique Accessoire Exclusif.
{contexte_client_et_historique}
Analyse la demande du client et utilise les OUTILS (Function Calling) mis à ta disposition si tu as besoin de chercher des produits, des parfums, des essences, des flacons ou des accessoires dans notre base de données.

CONSIGNES STRICTES DE SELECTION ET LIMITATION DES PRODUITS (TRES IMPORTANT) :

1. SI LE CLIENT DEMANDE UNE CATÉGORIE PRÉCISE :
- Si le client demande spécifiquement des PARFUMS EXISTANTS (prêts à l'emploi) : Propose UNIQUEMENT des parfums dans `parfums_existants_recommandes` (MAXIMUM 3 PARFUMS). Ne propose AUCUN accessoire, AUCUN diffuseur et AUCUNE création sur-mesure (garde `flacon_id = 0`, `essences_pre_faites = []`, `accessoires = []`, `diffuseurs = []`).
- Si le client demande spécifiquement des ACCESSOIRES ou DIFFUSEURS : Propose UNIQUEMENT des produits dans `accessoires` ou `diffuseurs` (MAXIMUM 3 PRODUITS AU TOTAL). Ne propose AUCUN parfum et AUCUNE création sur-mesure (garde `parfums_existants_recommandes = []`, `flacon_id = 0`, `essences_pre_faites = []`).
- Si le client demande un PARFUM PERSONNALISÉ / CRÉATION SUR-MESURE : Propose UNE SEULE (1 SEULE) création sur-mesure avec `flacon_id` et ses essences dans `essences_pre_faites`. Ne propose AUCUN parfum existant prêt à l'emploi, AUCUN accessoire et AUCUN diffuseur (garde `parfums_existants_recommandes = []`, `accessoires = []`, `diffuseurs = []`).

2. SI LA DEMANDE EST VAGUE, DÉCOUVERTE OU SANS CATÉGORIE SPÉCIFIQUE (ex: "propose-moi quelque chose", "idées cadeaux", "surprise-moi") :
- Ne propose PAS les 3 catégories en même temps. Choisis UNIQUEMENT 1 SEUL PRODUIT parmi l'une des catégories (soit 1 seul parfum, soit 1 seul accessoire, soit 1 seule création sur-mesure). NE SURCHARGE JAMAIS le client.

3. SIMPLE SALUTATION OU POLITESSE ("bonjour", "hello", "hi") :
- Réponds uniquement avec un message chaleureux dans la langue du client SANS appeler d'outils et laisse TOUTES les listes vides (`flacon_id = 0`, `parfums_existants_recommandes = []`, `accessoires = []`, `diffuseurs = []`, `essences_pre_faites = []`).

RÈGLES IMPÉRATIVES :
0. DÉTECTION DE LA LANGUE ET RÉPONSE (EXIGENCE ABSOLUE ET IMPÉRATIVE) :
- Tu DOIS IMPÉRATIVEMENT détecter et utiliser la LANGUE DU MESSAGE ACTUEL DU CLIENT (le message immédiat qu'il vient d'envoyer : français, anglais, etc.).
- ATTENTION CONTEXTE / HISTORIQUE : NE TE FIE PAS à la langue des messages précédents dans l'historique si le client a changé de langue dans son message actuel !
  - Si le message actuel du client est en anglais (ex: "hello", "I want a perfume"), ta réponse DOIT être STRICTEMENT ET INTÉGRALEMENT EN ANGLAIS.
  - Si le message actuel du client est en français (ex: "bonjour", "je cherche un parfum"), ta réponse DOIT être STRICTEMENT EN FRANÇAIS.
- Écris sans AUCUNE abréviation. Écris TOUJOURS les mots en entier (« pour », « tout », « toujours », « s'il vous plaît », « beaucoup » / "for", "with", "always", "please", "thank you").

1. RÈGLE FLACON / ESSENCES (SUR-MESURE) :
- Si tu ne proposes pas d'essences dans `essences_pre_faites`, tu NE DOIS PAS non plus proposer de flacon (`flacon_id` DOIT ÊTRE ÉGAL À 0). Un `flacon_id` (> 0) n'est autorisé QUE SI `essences_pre_faites` contient au moins une essence.

2. FORMAT DE RÉPONSE FINAL :
Tu DOIS obligatoirement renvoyer ta réponse finale sous la forme d'un objet JSON strict respectant la structure suivante (sans balise ```json) :
{{
    "message": "Ton message chaleureux expliquant tes choix rédigé STRICTEMENT DANS LA LANGUE DU MESSAGE ACTUEL DU CLIENT (2 phrases maximum, mots complets, sans abréviation).",
    "quantite_demandee_ml": 0,
    "budget_max_fcfa": 0,
    "flacon_id": 0,
    "essences_pre_faites": [],
    "ingredients_sur_mesure": [],
    "parfums_existants_recommandes": [],
    "accessoires": [],
    "diffuseurs": []
}}
"""

    providers_map = {
        'groq': _appel_provider_groq,
        'gemini': _appel_provider_gemini,
        'huggingface': _appel_provider_huggingface,
        'hf': _appel_provider_huggingface,
        'ollama': _appel_provider_ollama,
    }

    primary_provider = os.environ.get('LLM_PROVIDER', getattr(settings, 'LLM_PROVIDER', 'gemini')).lower()
    
    # Ordre de basculement automatique des providers en cas d'erreur
    default_order = ['groq', 'gemini', 'huggingface', 'ollama']
    providers_chain = [primary_provider] if primary_provider in providers_map else ['gemini']
    for prov in default_order:
        if prov not in providers_chain and (prov == 'huggingface' and 'hf' in providers_chain):
            continue
        if prov not in providers_chain:
            providers_chain.append(prov)

    reponse_texte = None
    dernieres_erreurs = []

    for current_provider in providers_chain:
        runner_fn = providers_map.get(current_provider)
        if not runner_fn:
            continue

        try:
            print(f"[IA-RECOMMANDATION] Tentative d'appel avec le provider '{current_provider}'...", flush=True)
            reponse_texte = runner_fn(prompt_utilisateur, system_prompt)
            if reponse_texte:
                print(f"[IA-RECOMMANDATION] Succès de la réponse obtenue via '{current_provider}' !", flush=True)
                break
        except Exception as e:
            err_msg = str(e)
            print(f"[IA-RECOMMANDATION] ERREUR sur provider '{current_provider}': {err_msg}. Switch automatique vers le provider suivant...", flush=True)
            logger.warning(f"Échec provider IA {current_provider}: {err_msg}")
            dernieres_erreurs.append(f"{current_provider}: {err_msg}")

    if not reponse_texte:
        print(f"[IA-RECOMMANDATION] TOUS les providers IA ont échoué : {dernieres_erreurs}", flush=True)
        return {"error": "Tous les services d'IA sont actuellement indisponibles. Veuillez réessayer dans quelques instants."}

    if not reponse_texte:
        return {"error": "Aucune réponse texte reçue de l'IA."}

    parsed = _extract_json_from_text(reponse_texte)

    # Fallback de réparation si la réponse Ollama n'était pas un JSON valide au premier essai
    if parsed is None and provider == 'ollama':
        print(f"[IA-RECOMMANDATION] Tentative de reparation JSON avec Ollama...", flush=True)
        try:
            repair_messages = [
                {'role': 'system', 'content': 'Tu es un convertisseur JSON strict. Convertis le texte fourni en un objet JSON respectant le format exact sans aucun texte explicatif. CONSERVE STRICTEMENT LA LANGUE D\'ORIGINE DU TEXTE (Français, Anglais, etc.) dans le champ "message".'},
                {'role': 'user', 'content': f"Convertis ce texte en un objet JSON strict respectant exactement cette structure :\n{{\"message\": \"...\", \"quantite_demandee_ml\": 0, \"budget_max_fcfa\": 0, \"flacon_id\": 0, \"essences_pre_faites\": [], \"ingredients_sur_mesure\": [], \"parfums_existants_recommandes\": [], \"accessoires\": [], \"diffuseurs\": []}}\n\nTexte :\n{reponse_texte}"}
            ]
            repair_resp = requests.post(
                f"{ollama_url}/v1/chat/completions",
                json={
                    'model': model_name,
                    'messages': repair_messages,
                    'response_format': {'type': 'json_object'},
                    'temperature': 0.1,
                    'stream': False,
                },
                timeout=(10, 60),
            )
            if repair_resp.status_code == 200:
                repair_text = repair_resp.json().get('choices', [{}])[0].get('message', {}).get('content', '')
                parsed = _extract_json_from_text(repair_text)
        except Exception as e:
            print(f"[IA-RECOMMANDATION] Échec de la réparation JSON: {e}", flush=True)
    if parsed is None:
        print(f"[IA-RECOMMANDATION] ERREUR: Impossible d'extraire le JSON de la reponse: {reponse_texte}", flush=True)
        return {
            "error": "L'IA a généré une réponse qui n'est pas un JSON valide.",
            "raw_response": reponse_texte,
        }

    # 1. Ajustement déterministe Python de la règle des 45% — UNIQUEMENT pour les créations sur mesure
    flacon_id_raw = parsed.get('flacon_id', 0)
    essences_raw = parsed.get('essences_pre_faites', [])
    is_custom_creation = bool(flacon_id_raw) and bool(essences_raw)

    if is_custom_creation:
        parsed = normaliser_reponse_composition(parsed)
        parsed = ajuster_composition_45_percent(parsed)
        # Une création sur-mesure est exclusive : on vide les autres catégories
        parsed['parfums_existants_recommandes'] = []
        parsed['accessoires'] = []
        parsed['diffuseurs'] = []
    else:
        # Réponse directe (salutation, parfums existants, accessoires)
        # S'il n'y a pas d'essences pré-faites, on garantit flacon_id = 0 et essences_pre_faites = []
        parsed['flacon_id'] = 0
        parsed['essences_pre_faites'] = []
        # Plafonnier strict à 3 éléments maximum par catégorie ciblée
        if parsed.get('parfums_existants_recommandes'):
            parsed['parfums_existants_recommandes'] = parsed['parfums_existants_recommandes'][:3]
        if parsed.get('accessoires') or parsed.get('diffuseurs'):
            parsed['accessoires'] = parsed.get('accessoires', [])[:3]
            rem = max(0, 3 - len(parsed['accessoires']))
            parsed['diffuseurs'] = parsed.get('diffuseurs', [])[:rem]
        print(f"[IA-RECOMMANDATION] Post-traitement Python des limites et réinitialisation flacon_id appliqué avec succès.", flush=True)

    # 2. Validation du schéma JSON
    valid, validation_error = validate_ia_response_schema(parsed)
    if not valid:
        print(f"[IA-RECOMMANDATION] ERREUR: Le JSON ne respecte pas le schema de sortie: {validation_error}", flush=True)
        return {
            "error": f"Réponse IA invalide : {validation_error}",
            "parsed_response": parsed,
            "raw_response": reponse_texte,
        }

    print(f"[IA-RECOMMANDATION] Succes de la generation et validation du JSON final.\n", flush=True)
    return parsed
