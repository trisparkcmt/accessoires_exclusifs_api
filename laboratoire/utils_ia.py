import json
import logging
import os
import re

import requests
from django.conf import settings
from google import genai
from google.genai import types
from catalogue.models import Parfum, Essence, Accessoire, Flacon, Ingredient

logger = logging.getLogger(__name__)

def get_catalogue_context():
    """Récupère et formate le catalogue pour l'IA"""
    from catalogue.models import LotEssence, DiffuseurParfum
    parfums = Parfum.objects.filter(actif=True).values('id', 'nom', 'contenance_ml', 'description_ia', 'prix_unitaire')
    # Essences : uniquement celles actives, avec prix et en stock (au moins un lot actif avec stock)
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
        context += f"- ID: {p['id']}, Nom: {p['nom']}, Contenance: {p['contenance_ml']}ml, Prix: {p['prix_unitaire']} FCFA, Description: {p['description_ia']}\n"
        
    context += "\n=== ESSENCES PRÉFABRIQUÉES ===\n"
    for e in essences:
        context += f"- ID: {e['id']}, Nom: {e['nom']}, Catégorie: {e['categorie']}, Prix/ml: {e['prix_par_ml']} FCFA, Description: {e['description_ia']}\n"
    
    context += "\n=== INGRÉDIENTS (pour création 100% sur mesure) ===\n"
    for i in ingredients:
        context += f"- ID: {i['id']}, Nom: {i['nom']}, Prix/ml: {i['prix_par_ml']} FCFA\n"
    
    context += "\n=== FLACONS ===\n"
    for f in flacons:
        context += f"- ID: {f['id']}, Nom: {f['nom']}, Contenance: {f['contenance_ml']}ml, Prix: {f['prix_unitaire']} FCFA\n"
        
    context += "\n=== ACCESSOIRES ===\n"
    for a in accessoires:
        context += f"- ID: {a['id']}, Nom: {a['nom']}, Prix: {a['prix_unitaire']} FCFA, Description: {a['description_courte']}\n"
        
    context += "\n=== DIFFUSEURS DE PARFUM ===\n"
    for d in diffuseurs:
        prix = d['prix_promotionnel'] if d.get('prix_promotionnel') is not None else d['prix_unitaire']
        desc = (d.get('description') or '').replace('\n', ' ')[:100]
        context += f"- ID: {d['id']}, Nom: {d['nom']}, Prix: {prix} FCFA, Description: {desc}\n"
        
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


def _ollama_embedding_query(text, model_name=None, timeout=None):
    # Désactivé si USE_ALL_MINI n'est pas activé
    use_all_mini = os.getenv('USE_ALL_MINI', 'false').strip().lower()
    if use_all_mini not in ('1', 'true', 'yes', 'on'):
        raise RuntimeError('USE_ALL_MINI non activé — embeddings Ollama désactivés.')

    ollama_url = getattr(settings, 'OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
    model_name = model_name or getattr(settings, 'OLLAMA_EMBEDDING_MODEL', 'all-minilm')
    timeout_seconds = int(timeout or getattr(settings, 'OLLAMA_TIMEOUT_SECONDS', '30'))
    timeout_seconds = max(timeout_seconds, 60)
    payload = {
        'model': model_name,
        'input': [text],
    }

    logger.info('[EMBEDDING_CALL] Ollama embeddings request', extra={
        'model': model_name,
        'url': f"{ollama_url}/v1/embeddings",
        'timeout': timeout_seconds,
        'text_preview': text[:200],
    })

    response = requests.post(
        f"{ollama_url}/v1/embeddings",
        json=payload,
        timeout=(10, timeout_seconds),
    )
    response.raise_for_status()
    data = response.json()

    logger.info('[EMBEDDING_RESPONSE] Ollama embeddings response', extra={
        'status_code': response.status_code,
        'embeddings_count': len(data.get('embeddings', [])),
        'response_text_preview': response.text[:400],
    })

    embeddings = data.get('embeddings')
    if isinstance(embeddings, list) and embeddings:
        return embeddings[0]
    raise ValueError('Embeddings Ollama inattendus')


def _cosine_similarity(vec_a, vec_b):
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return -1

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return -1
    return dot / (norm_a * norm_b)


def get_relevant_catalogue_context(prompt_utilisateur, top_n=4):
    """Récupère un sous-ensemble pertinent du catalogue basé sur des embeddings."""
    try:
        prompt_embedding = _ollama_embedding_query(prompt_utilisateur)
    except Exception:
        return get_catalogue_context()

    essences = Essence.objects.filter(actif=True, embedding__isnull=False).exclude(embedding__exact='')
    parfums = Parfum.objects.filter(actif=True, embedding__isnull=False).exclude(embedding__exact='')
    accessoires = Accessoire.objects.filter(actif=True, embedding__isnull=False).exclude(embedding__exact='')

    scored = []

    for instance, model_type in [(essences, 'essence'), (parfums, 'parfum'), (accessoires, 'accessoire')]:
        for obj in instance:
            try:
                similarity = _cosine_similarity(prompt_embedding, obj.embedding)
            except Exception:
                continue
            scored.append((similarity, obj, model_type))

    if not scored:
        return get_catalogue_context()

    scored.sort(key=lambda item: item[0], reverse=True)
    top_results = scored[:top_n]

    context = "Catalogue le plus pertinent de la parfumerie :\n\n"

    for similarity, obj, model_type in top_results:
        if model_type == 'essence':
            description = (obj.description_ia or obj.description or '').replace('\n', ' ')[:120]
            context += (
                f"[Essence] ID: {obj.id}, Nom: {obj.nom}, Catégorie: {obj.categorie}, Prix/ml: {obj.prix_par_ml} FCFA, "
                f"Notes: {obj.notes_tete or 'N/A'} / {obj.notes_coeur or 'N/A'} / {obj.notes_fond or 'N/A'}, "
                f"Description: {description}\n"
            )
        elif model_type == 'parfum':
            description = (obj.description_ia or obj.description_longue or obj.description_courte or '').replace('\n', ' ')[:120]
            context += (
                f"[Parfum] ID: {obj.id}, Nom: {obj.nom}, Contenance: {obj.contenance_ml}ml, Prix: {obj.prix_unitaire} FCFA, "
                f"Notes: {obj.notes_tete or 'N/A'} / {obj.notes_coeur or 'N/A'} / {obj.notes_fond or 'N/A'}, "
                f"Description: {description}\n"
            )
        else:
            description = (obj.description_longue or obj.description_courte or '').replace('\n', ' ')[:120]
            context += (
                f"[Accessoire] ID: {obj.id}, Nom: {obj.nom}, Prix: {obj.prix_unitaire} FCFA, "
                f"Type: {obj.type_accessoire.nom if obj.type_accessoire else 'N/A'}, "
                f"Description: {description}\n"
            )

    context += "\n=== FLACONS ===\n"
    for f in Flacon.objects.filter(actif=True).values('id', 'nom', 'contenance_ml', 'prix_unitaire')[:4]:
        context += f"- ID: {f['id']}, Nom: {f['nom']}, Contenance: {f['contenance_ml']}ml, Prix: {f['prix_unitaire']} FCFA\n"

    context += "\n=== DIFFUSEURS DE PARFUM ===\n"
    from catalogue.models import DiffuseurParfum
    for d in DiffuseurParfum.objects.filter(actif=True, stock_quantite__gt=0).values('id', 'nom', 'prix_unitaire', 'prix_promotionnel')[:4]:
        prix = d['prix_promotionnel'] if d.get('prix_promotionnel') is not None else d['prix_unitaire']
        context += f"- ID: {d['id']}, Nom: {d['nom']}, Prix: {prix} FCFA\n"

    return context


def demander_recommandation_ia(prompt_utilisateur, history=None, client_info=None):
    """Envoie le prompt à l'IA configurée et retourne une réponse formatée."""
    provider = os.environ.get('LLM_PROVIDER', getattr(settings, 'LLM_PROVIDER', 'gemini')).lower()
    catalogue_context = get_relevant_catalogue_context(prompt_utilisateur)
    historique = ''
    if history:
        historique = 'Historique des échanges précédents :\n'
        for message in history:
            role = 'Client' if message['role'] == 'user' else 'Assistant'
            historique += f"- {role} : {message['content']}\n"
        historique += '\n'

    include_catalogue = os.environ.get('OLLAMA_INCLUDE_CATALOGUE', 'true').lower() == 'true'
    if not include_catalogue:
        catalogue_context = ''

    client_context = ""
    if client_info:
        client_context = f"Le client actuel est connecté et s'appelle {client_info.get('nom')} (Email : {client_info.get('email')}). N'hésite pas à t'adresser à lui en utilisant son nom si cela est naturel, et à personnaliser ton message en fonction de lui.\n"

    system_prompt = f"""Tu es un expert parfumeur et conseiller de vente pour la boutique Accessoire Exclusif.
{client_context}Prends en compte l'historique de la discussion pour adapter tes réponses et comprendre le contexte global.

Analyse la demande du client et respecte IMPÉRATIVEMENT toutes les règles suivantes :

0. LANGAGE ET ORTHOGRAPHE (CRITIQUE — NON NÉGOCIABLE) :
- Tu dois écrire en français parfait, sans AUCUNE abréviation. JAMAIS.
- Interdit : « pr », « tt », « tjrs », « pcq », « svp », « bcp », « qd », « qq », « etc. » ou tout autre raccourci.
- Écris TOUJOURS les mots en entier : « pour », « tout », « toujours », « parce que », « s'il vous plaît », « beaucoup », « quand », « quelques ».
- Un message de qualité professionnelle est obligatoire.

1. COMPORTEMENT ET LOGIQUE DE CONVERSATION :
- Si la demande est un simple salut (ex: "bonjour", "salut"), une politesse, ou une question d'information générale sans intention d'achat/recommandation, réponds chaleureusement et naturellement dans le champ "message". Ne propose aucun produit, mets "flacon_id" à 0 et laisse toutes les listes de produits vides.
- Si le client demande des recommandations de produits ou une création sur mesure, réponds chaleureusement en justifiant tes choix.
- Le champ "message" doit être écrit en français sans faute et composé de 2 phrases maximum.

2. FLACON ET COMPOSITION (SUR MESURE) — CALCUL OBLIGATOIRE :
- Un flacon ("flacon_id") ne doit être choisi (valeur > 0) QUE si tu proposes une composition sur mesure (c'est-à-dire si tu mets des éléments dans "essences_pre_faites" ou "ingredients_sur_mesure"). Si tu ne recommandes pas de création personnalisée, "flacon_id" doit être égal à 0.
- RÈGLE DES 45% (CRITIQUE ET ABSOLUE) : La somme totale des quantités (en ml) de TOUTES les essences et ingrédients réunis doit être EXACTEMENT égale à 45% de la contenance du flacon choisi.
  * Méthode de calcul OBLIGATOIRE avant de répondre :
    1. Note la contenance du flacon choisi : X ml.
    2. Calcule le volume cible : volume_cible = X × 0.45 ml.
    3. Répartis les essences de façon à ce que leur somme = volume_cible exactement.
    4. Vérifie : somme de toutes les quantite_ml = volume_cible. Si ce n'est pas exact, ajuste.
  * Exemple : Flacon de 50ml → volume_cible = 50 × 0.45 = 22.5ml. Si tu proposes 3 essences, elles doivent totaliser exactement 22.5ml (ex: 10ml + 8ml + 4.5ml = 22.5ml ✓).
- Si le client n'indique pas de quantité en ml, choisis un flacon adapté de notre catalogue.

3. PROPOSITIONS ASSORTIES ET VENTE COMPLÉMENTAIRE (CROSS-SELLING) :
- Lorsque le client demande ou accepte un produit (par exemple un parfum), propose-lui SYSTEMATIQUEMENT quelque chose qui s'associe très bien avec (un accessoire assorti comme un vaporisateur de voyage, ou un diffuseur de parfum de notre catalogue). Explique chaleureusement dans ton message pourquoi ce produit supplémentaire complète parfaitement sa sélection.
- Si le client demande explicitement un diffuseur de parfum (ex: "je veux un diffuseur", "propose-moi un diffuseur d'ambiance"), recommande les IDs des diffuseurs adaptés dans la liste `diffuseurs` du JSON.

4. BUDGET ET PRIX :
- Pour chaque produit ou élément que tu sélectionnes (parfums existants, flacons, essences, ingrédients, accessoires, diffuseurs), calcule mentalement leur prix total à l'aide des prix indiqués dans le catalogue ci-dessous.
- Si le client a spécifié un budget maximum (ou si un budget est mentionné dans l'historique), tu dois STRICTEMENT proposer des produits dont le prix total combiné ne dépasse pas ce budget.
- Mentionne explicitement dans ton "message" les prix individuels des produits que tu proposes pour que le client voie clairement le coût de chaque élément.

5. FORMAT DE RÉPONSE :
- Les listes `parfums_existants_recommandes`, `accessoires` et `diffuseurs` doivent uniquement contenir les IDs numériques des produits (ex: [1, 2]), PAS des objets/dictionnaires.
- Ne propose que des produits présents dans le catalogue ci-dessous.

Catalogue disponible :
{catalogue_context}

Réponds au format JSON strict uniquement, sans aucun texte avant ou après, et sans balises de code markdown (pas de ```json) :
{{
    "message": "Ton message chaleureux avec les prix de chaque élément proposé et la recommandation du produit ou accessoire/diffuseur complémentaire assorti (2 phrases maximum, mots complets, pas d'abréviations).",
    "quantite_demandee_ml": 0,
    "budget_max_fcfa": 0,
    "flacon_id": 0,
    "essences_pre_faites": [
        {{"id": 1, "quantite_ml": 10.5}}
    ],
    "ingredients_sur_mesure": [
        {{"id": 5, "quantite_ml": 5}}
    ],
    "parfums_existants_recommandes": [1, 2],
    "accessoires": [1],
    "diffuseurs": [1]
}}
"""

    reponse_texte = None
    llm_payload = None

    if provider == 'ollama':
        ollama_url = os.environ.get('OLLAMA_URL', getattr(settings, 'OLLAMA_URL', 'http://127.0.0.1:11434')).rstrip('/')
        model_name = os.environ.get('OLLAMA_MODEL', getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:3b'))
        timeout_seconds = int(os.environ.get('OLLAMA_TIMEOUT_SECONDS', getattr(settings, 'OLLAMA_TIMEOUT_SECONDS', '30')))

        include_catalogue = os.environ.get('OLLAMA_INCLUDE_CATALOGUE', 'true').lower() == 'true'
        if not include_catalogue:
            catalogue_context = ''

        llm_payload = {
            'model': model_name,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f"Demande du client : {prompt_utilisateur}"}
            ],
            'temperature': 0.2,
        }

        logger.info('[LLM_CALL] Ollama request', extra={
            'provider': 'ollama',
            'model': model_name,
            'payload': llm_payload,
        })

        try:
            logger.info('[LLM_CALL] Ollama request preview', extra={
                'provider': 'ollama',
                'model': model_name,
                'url': f"{ollama_url}/v1/chat/completions",
                'payload_preview': {
                    'model': llm_payload['model'],
                    'messages': [
                        {
                            'role': llm_payload['messages'][0]['role'],
                            'content': llm_payload['messages'][0]['content'][:300],
                        },
                        {
                            'role': llm_payload['messages'][1]['role'],
                            'content': llm_payload['messages'][1]['content'][:200],
                        },
                    ],
                    'temperature': llm_payload['temperature'],
                },
            })

            response = requests.post(
                f"{ollama_url}/v1/chat/completions",
                json=llm_payload,
                timeout=(10, 300),
            )
            response.raise_for_status()
            data = response.json()

            logger.info('[LLM_RESPONSE] Ollama raw response', extra={
                'provider': 'ollama',
                'endpoint': f"{ollama_url}/v1/chat/completions",
                'status_code': response.status_code,
                'response_json': data,
                'response_text_preview': response.text[:400],
            })

            if isinstance(data, dict) and 'choices' in data and data['choices']:
                choice = data['choices'][0]
                reponse_texte = (
                    choice.get('message', {}).get('content')
                    or choice.get('text')
                    or response.text
                )
            else:
                reponse_texte = response.text
                logger.warning('[LLM_RESPONSE] Ollama returned no choices', extra={
                    'provider': 'ollama',
                    'endpoint': f"{ollama_url}/v1/chat/completions",
                    'response_text': reponse_texte,
                })

        except requests.exceptions.Timeout as exc:
            logger.exception('Timeout Ollama')
            return {"error": f"Erreur HTTP Ollama : {str(exc)}"}
        except requests.exceptions.RequestException as exc:
            logger.exception('Erreur HTTP Ollama')
            return {"error": f"Erreur HTTP Ollama : {str(exc)}"}
        except json.JSONDecodeError:
            logger.exception('Réponse Ollama JSON invalide')
            return {"error": "Réponse de l'API Ollama non JSON ou format inattendu."}
        except Exception as e:
            logger.exception('Erreur interne Ollama')
            return {"error": f"Erreur de l'API Ollama : {str(e)}"}
    else:
        api_key = os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            logger.error('GEMINI_API_KEY manquante')
            return {"error": "Clé API Gemini manquante. Veuillez configurer GEMINI_API_KEY."}

        llm_payload = {
            'model': 'gemini-2.5-flash',
            'contents': f"{historique}{system_prompt}\n\nDemande du client : {prompt_utilisateur}",
            'config': {
                'temperature': 0.2,
                'response_mime_type': 'application/json',
            },
        }

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=llm_payload['model'],
                contents=llm_payload['contents'],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type='application/json',
                )
            )
            reponse_texte = response.text.strip()
            logger.debug('Gemini réponse brute : %s', reponse_texte)
        except json.JSONDecodeError:
            logger.exception('Réponse Gemini JSON invalide')
            return {"error": "L'IA a généré une réponse qui n'est pas un JSON valide."}
        except Exception as e:
            logger.exception('Erreur Gemini')
            return {"error": f"Erreur de l'API IA : {str(e)}"}

    if reponse_texte is None:
        logger.error('Aucune réponse texte obtenue de l’IA', extra={'provider': provider, 'payload': llm_payload})
        return {"error": "Aucune réponse texte reçue de l'IA."}

    parsed = _extract_json_from_text(reponse_texte)
    if parsed is None:
        logger.exception('JSON parsing failed', extra={'provider': provider, 'response_text': reponse_texte})
        return {
            "error": "L'IA a généré une réponse qui n'est pas un JSON valide.",
            "raw_response": reponse_texte,
        }

    valid, validation_error = validate_ia_response_schema(parsed)
    if not valid:
        logger.warning('Validation de schéma IA échouée', extra={
            'provider': provider,
            'validation_error': validation_error,
            'parsed_response': parsed,
        })
        return {
            "error": f"Réponse IA invalide : {validation_error}",
            "parsed_response": parsed,
            "raw_response": reponse_texte,
        }

    return parsed
