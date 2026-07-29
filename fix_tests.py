import requests

response = requests.post(
    'http://127.0.0.1:8000/api/v1/lab/ia-recommandation/',
    json=   {
      "prompt": "Je cherche un une composition de  parfum boisé et épicé, très mystérieux pour une soirée d'hiver. jai un budget de 60000fcfa et esce tu te souvient de tout  ce quon discute jusqua present ?" 
    }
)
print(response.status_code)
print(response.json())






# import requests

# # Utilisateur connecté
# token = "<votre_access_token>"

# response = requests.get(
#     'http://127.0.0.1:8000/api/v1/lab/ia-conversations/',
#     headers={'Authorization': f'Bearer {token}'}
# )
# print(response.status_code)
# print(response.json())

# ---- Séparément : test anonyme ----
# session = requests.Session()  # conserve le cookie sessionid automatiquement
# # D'abord envoyer un prompt pour créer la session
# session.post('http://127.0.0.1:8000/api/v1/lab/ia-recommandation/', json={"prompt": "Bonjour te souvien t de moi ?"})
# # Puis récupérer l'historique
# r = session.get('http://127.0.0.1:8000/api/v1/lab/ia-conversations/')
# print(r.json())
