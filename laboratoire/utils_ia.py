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
            item_norm['id'] = int(raw_id) if raw_id is not None else None
        except (ValueError, TypeError):
            continue

        try:
            item_norm['quantite_ml'] = round(float(item_norm.get('quantite_ml', 0) or 0), 2)
        except (TypeError, ValueError):
            item_norm['quantite_ml'] = 0.0

        if item_norm.get('id') is None:
            continue
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

def tool_rechercher_parfums(notes=None, budget_max=None, contenance_ml=None, **kwargs):
    """Recherche des parfums dans la base de données."""
    print(f"\n[TOOL CALL] tool_rechercher_parfums - Parametres: notes={notes}, budget_max={budget_max}, contenance_ml={contenance_ml}", flush=True)
    queryset = Parfum.objects.filter(actif=True, stock_quantite__gt=0)
    if notes:
        query = (
            models.Q(nom__icontains=notes) |
            models.Q(notes_tete__icontains=notes) |
            models.Q(notes_coeur__icontains=notes) |
            models.Q(notes_fond__icontains=notes) |
            models.Q(description_courte__icontains=notes) |
            models.Q(description_longue__icontains=notes) |
            models.Q(description_ia__icontains=notes) |
            models.Q(tags__nom__icontains=notes)
        )
        queryset = queryset.filter(query)
    if budget_max is not None:
        try:
            queryset = queryset.filter(prix_unitaire__lte=float(budget_max))
        except (ValueError, TypeError):
            pass
    if contenance_ml is not None:
        try:
            queryset = queryset.filter(contenance_ml=int(contenance_ml))
        except (ValueError, TypeError):
            pass

    results = []
    for p in queryset[:6]:
        results.append({
            'id': p.id,
            'nom': p.nom,
            'contenance_ml': p.contenance_ml,
            'prix_unitaire': float(p.prix_unitaire),
            'description': (p.description_ia or p.description_courte or '')[:120],
        })
    print(f"[TOOL RESULT] tool_rechercher_parfums a retourne {len(results)} parfums: {[r['nom'] for r in results]}\n", flush=True)
    return results


def tool_rechercher_essences_et_ingredients(recherche=None, categorie=None, **kwargs):
    """Recherche des essences et ingrédients du laboratoire."""
    print(f"\n[TOOL CALL] tool_rechercher_essences_et_ingredients - Parametres: recherche={recherche}, categorie={categorie}", flush=True)
    essence_ids_en_stock = LotEssence.objects.filter(
        actif=True, stock_ml__gt=0
    ).values_list('essence_id', flat=True).distinct()

    essences_qs = Essence.objects.filter(actif=True, prix_par_ml__gt=0, id__in=essence_ids_en_stock)
    ingredients_qs = Ingredient.objects.filter(actif=True)

    if recherche:
        e_query = (
            models.Q(nom__icontains=recherche) |
            models.Q(notes_tete__icontains=recherche) |
            models.Q(notes_coeur__icontains=recherche) |
            models.Q(notes_fond__icontains=recherche) |
            models.Q(description__icontains=recherche)|
            models.Q(description_ia__icontains=recherche)
        )
        essences_qs = essences_qs.filter(e_query)
        ingredients_qs = ingredients_qs.filter(models.Q(nom__icontains=recherche) | models.Q(description__icontains=recherche))

    if categorie:
        essences_qs = essences_qs.filter(categorie=categorie)

    essences_res = []
    for e in essences_qs[:6]:
        essences_res.append({
            'id': e.id,
            'nom': e.nom,
            'categorie': e.categorie,
            'prix_par_ml': float(e.prix_par_ml),
            'description': (e.description_ia or e.description or '')[:100],
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
    acc_qs = Accessoire.objects.filter(actif=True)
    diff_qs = DiffuseurParfum.objects.filter(actif=True, stock_quantite__gt=0)

    if recherche:
        acc_qs = acc_qs.filter(models.Q(nom__icontains=recherche) | models.Q(description_courte__icontains=recherche))
        diff_qs = diff_qs.filter(models.Q(nom__icontains=recherche) | models.Q(description__icontains=recherche))
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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        first = text.find('{')
        last = text.rfind('}')
        if first != -1 and last != -1 and last > first:
            candidate = text[first:last + 1]
            try:
                return json.loads(candidate)
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
            print(f"[RESUME IA] Nouveau résumé généré: '{nouveau_resume[:100]}...'", flush=True)
            return nouveau_resume if nouveau_resume else resume_existant

        else:
            api_key = os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', None)
            if not api_key:
                return resume_existant
            client_gemini = genai.Client(api_key=api_key)
            response = client_gemini.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt_resume,
                config=types.GenerateContentConfig(temperature=0.1),
            )
            nouveau_resume = response.text.strip()
            print(f"[RESUME IA] Nouveau résumé généré: '{nouveau_resume[:100]}...'", flush=True)
            return nouveau_resume if nouveau_resume else resume_existant

    except Exception as e:
        print(f"[RESUME IA] Erreur lors de la génération du résumé (non bloquant): {str(e)}", flush=True)
        return resume_existant  # On garde l'ancien résumé en cas d'erreur




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
        print(f"[IA-RECOMMANDATION] Contexte: {len(history) if history else 0} messages bruts (pas encore de résumé)", flush=True)


    system_prompt = f"""Tu es un expert parfumeur et conseiller de vente pour la boutique Accessoire Exclusif.
{contexte_client_et_historique}
Analyse la demande du client et utilise les OUTILS (Function Calling) mis à ta disposition si tu as besoin de chercher des produits, des parfums, des essences, des flacons ou des accessoires dans notre base de données.

CONSIGNES DE CHOIX DES OUTILS (TRES IMPORTANT) :
- Si le client s'intéresse à un parfum existant prêt à l'emploi (deja tout fait), utilise `rechercher_parfums`.
- Si le client demande expressément une "composition", une "création", un parfum "sur-mesure", "personnalisé", "sur mesure" ou un mélange, c'est une création sur-mesure. Dans ce cas, n'appelle PAS `rechercher_parfums`. Tu dois appeler `rechercher_essences_et_ingredients` pour trouver les composants, ET appeler `obtenir_flacons_disponibles` pour proposer un flacon adapté.

RÈGLES IMPÉRATIVES :
0. DÉTECTION DE LA LANGUE ET RÉPONSE (CRITIQUE IMPÉRATIVE) :
- Tu DOIS analyser la langue du DERNIER PROMPT actuel soumis par le client ("Demande du client").
- Si le prompt actuel du client est rédigé en ANGLAIS (ex: "I want a sweet perfume", "Hello", "What is your price?"), tu DOIS OBLIGATOIREMENT rédiger le champ "message" de ta réponse finale intégralement en ANGLAIS.
- Si le prompt actuel du client est rédigé en FRANÇAIS (ex: "Je cherche un parfum doux", "Bonjour"), tu DOIS OBLIGATOIREMENT rédiger le champ "message" de ta réponse finale intégralement en FRANÇAIS.
- Ne te fie PAS à la langue des échanges passés ou du résumé : fie-toi STRICTEMENT à la langue du dernier prompt reçu.
- Écris sans AUCUNE abréviation. Écris TOUJOURS les mots en entier (« pour », « tout », « toujours », « s'il vous plaît », « beaucoup » / "for", "with", "always", "please", "thank you").

1. COMPORTEMENT ET LOGIQUE DE CONVERSATION :
- Si la demande est une simple salutation ou une politesse, réponds chaleureusement dans "message" (en anglais si le prompt est en anglais, en français si le prompt est en français) sans appeler d'outils et laisse les listes de produits vides avec flacon_id = 0.
- Si le client cherche une recommandation ou une création sur-mesure, utilise les outils pour interroger la base de données puis propose la meilleure sélection.

2. COMPOSITION SUR-MESURE :
- Un flacon ("flacon_id") ne doit être choisi que pour une création personnalisée sur-mesure. Les quantités d'essences en ml seront automatiquement ajustées par notre système Python à exactement 45% de la contenance du flacon.
- Pour une création personnalisée, la base du parfum doit contenir uniquement des essences dans "essences_pre_faites". Le champ "ingredients_sur_mesure" doit rester vide.
- Si le client demande une création personnalisée, n'inclus pas d'ingrédients dans la réponse finale.
- IMPORTANT : pour "essences_pre_faites", fournis une liste d'objets avec "id" et "quantite_ml".
- Pour "parfums_existants_recommandes", "accessoires", et "diffuseurs", il suffit de fournir la liste de leurs identifiants numériques [id1, id2]. Le serveur Python récupèrera automatiquement toutes les caractéristiques des produits depuis la base de données.

3. VENTE COMPLÉMENTAIRE (CROSS-SELLING) :
- N'inclus un accessoire (dans "accessoires") ou un diffuseur (dans "diffuseurs") QUE si un produit pertinent a été trouvé via les outils ou le catalogue. Ne mets PAS d'ID par défaut et laisse la liste vide `[]` si aucun accessoire n'est spécifiquement pertinent pour la demande.

4. FORMAT DE RÉPONSE FINAL :
Tu DOIS obligatoirement renvoyer ta réponse finale sous la forme d'un objet JSON strict respectant la structure suivante (sans balise ```json).
ATTENTION : Les nombres et IDs indiqués dans le modèle ci-dessous ne sont que des EXEMPLES D'ILLUSTRATION de la structure. Tu DOIS les remplacer par les vrais IDs et les vraies valeurs issus de la recherche de produits :
{{
    "message": "Ton message chaleureux expliquant tes choix rédigé STRICTEMENT DANS LA LANGUE DU DERNIER PROMPT (français ou anglais, 2 phrases maximum, mots complets, sans abréviation).",
    "quantite_demandee_ml": 0,
    "budget_max_fcfa": 0,
    "flacon_id": 0,
    "essences_pre_faites": [
        {{"id": 11, "quantite_ml": 11.25}},
        {{"id": 12, "quantite_ml": 11.25}}
    ],
    "ingredients_sur_mesure": [],
    "parfums_existants_recommandes": [1],
    "accessoires": [],
    "diffuseurs": []
}}
"""

    reponse_texte = None

    if provider == 'ollama':
        ollama_url = os.environ.get('OLLAMA_URL', getattr(settings, 'OLLAMA_URL', 'http://127.0.0.1:11434')).rstrip('/')
        model_name = os.environ.get('OLLAMA_MODEL', getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:3b'))

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': f"Demande du client : {prompt_utilisateur}"}
        ]

        llm_payload = {
            'model': model_name,
            'messages': messages,
            'tools': OLLAMA_TOOLS_DEFINITIONS,
            'temperature': 0.2,
            'stream': False,
        }

        print(f"[IA-RECOMMANDATION] Ollama: Envoi du premier appel (URL: {ollama_url}/v1/chat/completions)...", flush=True)
        logger.info('[LLM_CALL] Ollama request Function Calling', extra={'model': model_name, 'url': f"{ollama_url}/v1/chat/completions"})

        try:
            # Augmentation du timeout (connection = 20s, lecture = 180s)
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

                # Si le modèle demande à exécuter un ou plusieurs outils
                if tool_calls:
                    print(f"[IA-RECOMMANDATION] Ollama a demande des outils: {[t.get('function', {}).get('name') for t in tool_calls]}", flush=True)
                    logger.info('[LLM_TOOL_CALL] Ollama a demandé des outils', extra={'tool_calls': tool_calls})
                    messages.append(message_obj)

                    for tool_call in tool_calls:
                        fn_name = tool_call.get('function', {}).get('name')
                        raw_args = tool_call.get('function', {}).get('arguments', '{}')
                        try:
                            fn_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        except json.JSONDecodeError:
                            fn_args = {}

                        print(f"[IA-RECOMMANDATION] Execution de l'outil local: {fn_name}(**{fn_args})...", flush=True)
                        if fn_name in TOOLS_REGISTRY:
                            tool_result = TOOLS_REGISTRY[fn_name](**fn_args)
                        else:
                            tool_result = {"error": f"Outil inconnu : {fn_name}"}
                        print(f"[IA-RECOMMANDATION] Resultat de l'outil {fn_name}: {tool_result}", flush=True)

                        messages.append({
                            'role': 'tool',
                            'tool_call_id': tool_call.get('id', 'call_1'),
                            'content': json.dumps(tool_result, ensure_ascii=False)
                        })

                    # Second appel à Ollama avec les résultats des outils
                    second_payload = {
                        'model': model_name,
                        'messages': messages,
                        'temperature': 0.2,
                        'stream': False,
                    }
                    print(f"[IA-RECOMMANDATION] Ollama: Envoi du deuxieme appel avec les resultats des outils...", flush=True)
                    second_resp = requests.post(
                        f"{ollama_url}/v1/chat/completions",
                        json=second_payload,
                        timeout=(20, 180),
                    )
                    second_resp.raise_for_status()
                    second_data = second_resp.json()
                    if 'choices' in second_data and second_data['choices']:
                        reponse_texte = second_data['choices'][0].get('message', {}).get('content')
                        print(f"[IA-RECOMMANDATION] Reponse finale recue d'Ollama: '{reponse_texte[:120]}...'", flush=True)
                else:
                    reponse_texte = message_obj.get('content')
                    print(f"[IA-RECOMMANDATION] Reponse directe recue d'Ollama: '{reponse_texte[:120]}...'", flush=True)
            else:
                reponse_texte = response.text
                print(f"[IA-RECOMMANDATION] Reponse inattendue d'Ollama: {reponse_texte}", flush=True)

        except Exception as e:
            print(f"[IA-RECOMMANDATION] ERREUR critique lors de l'appel a Ollama: {str(e)}", flush=True)
            logger.exception('Erreur Ollama Function Calling')
            return {"error": f"Erreur de l'API Ollama : {str(e)}"}

    else:
        # Provider Gemini
        api_key = os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            return {"error": "Clé API Gemini manquante."}

        print(f"[IA-RECOMMANDATION] Gemini: Envoi de la requete...", flush=True)
        try:
            client = genai.Client(api_key=api_key)

            # Execution simple avec catalogue fallback pour Gemini
            catalogue_fallback = get_catalogue_context()
            contents = f"{system_prompt}\n\nCatalogue disponible :\n{catalogue_fallback}\n\nDemande du client : {prompt_utilisateur}"

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type='application/json',
                )
            )
            reponse_texte = response.text.strip()
            print(f"[IA-RECOMMANDATION] Reponse recue de Gemini: '{reponse_texte[:120]}...'", flush=True)
        except Exception as e:
            print(f"[IA-RECOMMANDATION] ERREUR critique lors de l'appel a Gemini: {str(e)}", flush=True)
            logger.exception('Erreur Gemini')
            return {"error": f"Erreur de l'API Gemini : {str(e)}"}

    if not reponse_texte:
        return {"error": "Aucune réponse texte reçue de l'IA."}

    parsed = _extract_json_from_text(reponse_texte)
    if parsed is None:
        print(f"[IA-RECOMMANDATION] ERREUR: Impossible d'extraire le JSON de la reponse: {reponse_texte}", flush=True)
        return {
            "error": "L'IA a généré une réponse qui n'est pas un JSON valide.",
            "raw_response": reponse_texte,
        }

    # 1. Normalisation stricte selon la logique métier
    parsed = normaliser_reponse_composition(parsed)

    # 2. Ajustement déterministe Python de la règle des 45%
    parsed = ajuster_composition_45_percent(parsed)

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
