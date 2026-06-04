import os
import json
import re
from google import genai
from google.genai import types
from django.conf import settings
from catalogue.models import Parfum, Essence, Accessoire, Flacon, Ingredient

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

def demander_recommandation_ia(prompt_utilisateur):
    """Envoie le prompt à Gemini et retourne une réponse formatée"""
    # Configuration de l'API avec la clé
    api_key = os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', None)
    
    if not api_key:
        return {"error": "Clé API Gemini manquante. Veuillez configurer GEMINI_API_KEY."}
        
    # Initialisation du client google.genai
    client = genai.Client(api_key=api_key)
    
    # Ton API n'a plus accès à la version 1.5. 
    # On utilise gemini-2.5-flash ou gemini-2.0-flash-lite (qui a souvent un quota gratuit généreux)
    model_name = 'gemini-2.5-flash'
    
    catalogue_context = get_catalogue_context()
    
    system_prompt = f"""Tu es un expert parfumeur et conseiller de vente pour la boutique Accessoire Exclusif.
Un client va te faire une demande avec potentiellement :
- Une quantité désirée en ml (ex: "30ml", "50ml")
- Un budget maximum (ex: "moins de 50000 FCFA")
- Des préférences d'odeurs, de parfums, d'essences ou d'accessoires.

Tu dois analyser sa demande, extraire la quantité, le budget et ses envies.
Puis recommander une création de parfum personnalisée ou des parfums existants et des accessoires.

RÈGLES D'OR DE RECOMMANDATION & CATALOGUE :
1. ACCESSOIRES : Recommande systématiquement des accessoires appropriés (comme des diffuseurs, des pochettes, des coffrets ou des sprays) en lien avec la demande de l'utilisateur ou pour compléter l'expérience de parfum.
2. TAILLE DE FLACON PAR DÉFAUT : Si le client ne précise pas de quantité (en ml) ou de flacon dans sa demande, choisis par défaut le plus grand flacon disponible dans le catalogue (celui ayant la plus grande valeur 'Contenance' en ml).
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
    
    try:
        # On utilise une température basse pour que l'IA reste factuelle et respecte le JSON
        response = client.models.generate_content(
            model=model_name,
            contents=f"{system_prompt}\n\nDemande du client : {prompt_utilisateur}",
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            )
        )
        
        reponse_texte = response.text.strip()
        reponse_json = json.loads(reponse_texte)
        return reponse_json
        
    except json.JSONDecodeError:
        return {"error": "L'IA a généré une réponse qui n'est pas un JSON valide."}
    except Exception as e:
        return {"error": f"Erreur de l'API IA : {str(e)}"}
