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
    parfums = Parfum.objects.filter(actif=True).values('id', 'nom', 'contenance_ml', 'description_ia', 'prix_unitaire')
    essences = Essence.objects.filter(actif=True).values('id', 'nom', 'description_ia', 'prix_par_ml', 'categorie')
    ingredients = Ingredient.objects.filter(actif=True).values('id', 'nom', 'prix_par_ml')
    accessoires = Accessoire.objects.filter(actif=True).values('id', 'nom', 'description_courte', 'prix_unitaire')
    flacons = Flacon.objects.filter(actif=True).values('id', 'nom', 'contenance_ml', 'prix_unitaire')
    
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

    if not isinstance(reponse.get('accessoires'), list):
        return False, 'Le champ accessoires doit être une liste.'

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


def demander_recommandation_ia(prompt_utilisateur, history=None):
    """Envoie le prompt à l'IA configurée et retourne une réponse formatée."""
    provider = os.environ.get('LLM_PROVIDER', getattr(settings, 'LLM_PROVIDER', 'gemini')).lower()
    catalogue_context = get_catalogue_context()
    historique = ''
    if history:
        historique = 'Historique des échanges précédents :\n'
        for message in history:
            role = 'Client' if message['role'] == 'user' else 'Assistant'
            historique += f"- {role} : {message['content']}\n"
        historique += '\n'

    system_prompt = f"""Tu es un expert parfumeur et conseiller de vente pour la boutique Accessoire Exclusif.
Un client va te faire une demande avec potentiellement :
- Une quantité désirée en ml (ex: "30ml", "50ml")
- Un budget maximum (ex: "moins de 50000 FCFA")
- Des préférences d'odeurs, de parfums, d'essences ou d'accessoires.

Tu dois analyser sa demande, déterminer si le client souhaite vraiment une recommandation ou une création de parfum, et extraire la quantité, le budget et ses envies.
Si la demande n'est pas une demande de recommandation ou d'achat (par exemple : question sur une note, un ingrédient, des conseils généraux, une information sur le magasin, ou une question hors parfum), ne proposes aucun produit, aucun flacon et aucune quantité. Dans ce cas, renvoie uniquement un message utile et des listes vides.
Puis, si le client souhaite une recommandation, recommander une création de parfum personnalisée ou des parfums existants et des accessoires.

RÈGLES D'OR DE RECOMMANDATION & CATALOGUE :
1. ACCESSOIRES : Recommande systématiquement des accessoires appropriés (comme des diffuseurs, des pochettes, des coffrets ou des sprays) en lien avec la demande de l'utilisateur ou pour compléter l'expérience de parfum.
2. TAILLE DE FLACON PAR DÉFAUT : Si le client ne précise pas de quantité (en ml) ou de flacon dans sa demande, choisis par défaut le plus grand flacon disponible dans le catalogue (celui ayant la plus grande valeur 'Contenance' en ml), mais seulement si tu proposes des essences ou des ingrédients.
3. INDISPONIBILITÉ & ALTERNATIVES : Si ce que le client demande explicitement (un ingrédient particulier, une note spécifique, un parfum précis ou un type d'accessoire) n'est PAS disponible dans notre catalogue, propose-lui TOUT DE MÊME le produit de remplacement ou l'alternative la plus proche de notre catalogue. Dans ton champ "message", indique-lui clairement, poliment et chaleureusement que le produit qu'il souhaitait n'est pas disponible, mais que tu lui proposes cette alternative de notre catalogue.

RÈGLE DES 45% (POUR LE SUR MESURE) :
La somme totale des ml de TOUTES les essences et de TOUS les ingrédients que tu proposes NE DOIT JAMAIS DÉPASSER EXACTEMENT 45% de la contenance du flacon choisi. (Exemple: pour un flacon de 50ml, le total des essences/ingrédients doit être MAXIMUM 22.5ml). Le reste sera de la base/alcool (non mentionnée ici).

Voici notre catalogue :
{catalogue_context}

IMPORTANT : Tu DOIS répondre UNIQUEMENT au format JSON strict (sans Markdown autour) :
{{
    "message": "Ton message chaleureux (max 3 phrases), incluant les explications de tes choix et l'indication si une demande du client était indisponible.",
    "quantite_demandee_ml": 50,
    "budget_max_fcfa": 0,
    "flacon_id": 1,
    "essences_pre_faites": [
        {{"id": 1, "quantite_ml": 10.5}}
    ],
    "ingredients_sur_mesure": [
        {{"id": 5, "quantite_ml": 5}},
        {{"id": 12, "quantite_ml": 7}}
    ],
    "parfums_existants_recommandes": [1, 2],
    "accessoires": [1]
}}

RÈGLES CRITIQUES :
- Le total (quantités essences_pre_faites + quantités ingredients_sur_mesure) DOIT être <= (contenance du flacon * 0.45). C'est critique !
- Le flacon_id doit correspondre à la contenance désirée.
- Ne propose pas d'essences ou d'ingrédients qui n'existent pas dans le catalogue.
- Si budget_max_fcfa > 0, calcule mentalement le coût (Flacon + (Essences * prix/ml) + (Ingredients * prix/ml) + Accessoires) et respecte le budget.
- Ne mets AUCUN texte avant ou après le JSON.
"""

    reponse_texte = None
    llm_payload = None

    if provider == 'ollama':
        ollama_url = os.environ.get('OLLAMA_URL', getattr(settings, 'OLLAMA_URL', 'http://127.0.0.1:11434')).rstrip('/')
        model_name = os.environ.get('OLLAMA_MODEL', getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:3b'))
        timeout_seconds = int(os.environ.get('OLLAMA_TIMEOUT_SECONDS', getattr(settings, 'OLLAMA_TIMEOUT_SECONDS', '30')))

        llm_payload = {
            'model': model_name,
            'messages': [
                {'role': 'user', 'content': f"{historique}{system_prompt}\n\nDemande du client : {prompt_utilisateur}"}
            ],
            'temperature': 0.2,
            'max_tokens': 1200,
        }

        try:
            response = requests.post(
                f"{ollama_url}/v1/completions",
                json=llm_payload,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()

            logger.debug('Ollama réponse brute : %s', data)

            if isinstance(data, dict) and 'choices' in data and data['choices']:
                choice = data['choices'][0]
                reponse_texte = (
                    choice.get('message', {}).get('content')
                    or choice.get('text')
                    or response.text
                )
            else:
                reponse_texte = response.text

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
        return {"error": "L'IA a généré une réponse qui n'est pas un JSON valide."}

    valid, validation_error = validate_ia_response_schema(parsed)
    if not valid:
        logger.warning('Validation de schéma IA échouée', extra={
            'provider': provider,
            'validation_error': validation_error,
            'parsed_response': parsed,
        })
        return {"error": f"Réponse IA invalide : {validation_error}"}

    return parsed
