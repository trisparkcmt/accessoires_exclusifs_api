# Spécification Technique Exhaustive de l'API — Accessoire Exclusif

Cette documentation détaille de manière rigoureuse et exhaustive les **80 endpoints** du backend. Elle sert de référence absolue pour l'intégration de votre frontend.

Chaque section répertorie :
1. Les en-têtes requis, les query parameters (si applicables).
2. La structure et le statut (`[REQUIS]` ou `[OPTIONNEL]`) de chaque champ du payload d'entrée (`POST`, `PUT`, `PATCH`).
3. La structure exacte de l'objet JSON renvoyé en sortie (`GET` Liste, `GET` Détail, et retours de requêtes d'écriture).
4. Les traitements automatiques du backend.

---

## 1. ENDPOINTS GÉNÉRAUX & DOCUMENTATION

### 1.1 Endpoint de Santé (Healthcheck)
*   **URL** : `GET /health/`
*   **Permissions** : Public (`AllowAny`)
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "status": "ok",                       // string
      "service": "Accessoires Exclusifs API" // string
    }
    ```

### 1.2 Schéma de l'API (OpenAPI)
*   **URL** : `GET /api/schema/`
*   **Permissions** : Public
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Fichier JSON/YAML brut au format OpenAPI 3.0.

### 1.3 Documentation Interactive (Swagger UI)
*   **URL** : `GET /api/docs/` (ou `/api/schema/swagger-ui/`)
*   **Permissions** : Public
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Page HTML avec l'interface interactive Swagger.

### 1.4 Documentation Interactive (ReDoc)
*   **URL** : `GET /api/redoc/` (ou `/api/schema/redoc/`)
*   **Permissions** : Public
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Page HTML avec l'interface ReDoc.

---

## 2. MODULE AUTHENTIFICATION & UTILISATEURS (`/api/v1/auth/`)

### 2.1 Connexion Web (Cookies sécurisés)
*   **URL** : `POST /api/v1/auth/web/login/`
*   **Permissions** : Public
*   **Comportement backend** : Écrit automatiquement `access_token` et `refresh_token` dans les en-têtes HTTP `Set-Cookie`.
*   **Payload d'entrée** :
    ```json
    {
      "email": "user@example.com", // [OPTIONNEL] string (requis si "telephone" absent)
      "telephone": "677777777",    // [OPTIONNEL] string (requis si "email" absent)
      "password": "motdepassefort"  // [REQUIS] string
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "id": 1,                      // integer
      "email": "user@example.com",  // string
      "telephone": "677777777",     // string
      "first_name": "Jean",         // string
      "last_name": "Dupont",        // string
      "role": "client"              // string ("client" | "prestataire" | "livreur" | "admin")
    }
    ```

### 2.2 Connexion Mobile & API (JSON Direct)
*   **URL** : `POST /api/v1/auth/mobile/login/`
*   **Permissions** : Public
*   **Comportement backend** : Renvoie les jetons d'authentification directement dans le JSON.
*   **Payload d'entrée** :
    ```json
    {
      "email": "user@example.com", // [OPTIONNEL] string (requis si "telephone" absent)
      "telephone": "677777777",    // [OPTIONNEL] string (requis si "email" absent)
      "password": "motdepassefort"  // [REQUIS] string
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",  // string (JWT Access)
      "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...", // string (JWT Refresh)
      "user": {
        "id": 1,
        "email": "user@example.com",
        "telephone": "677777777",
        "first_name": "Jean",
        "last_name": "Dupont",
        "role": "client"
      }
    }
    ```

### 2.3 Endpoint de Connexion standard désactivé
*   **URL** : `POST /api/v1/auth/login/`
*   **Permissions** : Public
*   **Payload d'entrée** : Tout payload
*   **Réponse - 400 Bad Request** :
    ```json
    {
      "detail": "L'endpoint '/api/v1/auth/login/' est obsolète..." // string
    }
    ```

### 2.4 Inscription (Création de compte)
*   **URL** : `POST /api/v1/auth/registration/`
*   **Permissions** : Public (limitation anti-abus active)
*   **Comportement backend** : Crée l'utilisateur (inactif si la validation est obligatoire) et envoie automatiquement l'email HTML de validation.
*   **Payload d'entrée** :
    ```json
    {
      "email": "nouveau@example.com",     // [REQUIS] string (format email unique)
      "password": "motdepasse_tres_fort",  // [REQUIS] string (min 8 chars)
      "password_confirm": "motdepasse_tres_fort", // [REQUIS] string (doit correspondre à "password")
      "first_name": "Jean",                // [OPTIONNEL] string (vide par défaut)
      "last_name": "Dupont",               // [OPTIONNEL] string (vide par défaut)
      "telephone": "237699999999"          // [OPTIONNEL] string (vide par défaut)
    }
    ```
*   **Réponse - 201 Created** :
    ```json
    {
      "access": "eyJhbGciOiJIUzI1...",  // string
      "refresh": "eyJhbGciOiJIUz..."    // string
    }
    ```

### 2.5 Vérification de l'adresse e-mail
*   **URL** : `POST /api/v1/auth/registration/verify-email/`
*   **Permissions** : Public
*   **Payload d'entrée** :
    ```json
    {
      "key": "1a2b3c4d5e6f..." // [REQUIS] string
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "ok" // string
    }
    ```

### 2.6 Renvoi de l'e-mail de vérification
*   **URL** : `POST /api/v1/auth/registration/resend-email/`
*   **Permissions** : Public
*   **Payload d'entrée** :
    ```json
    {
      "email": "nouveau@example.com" // [REQUIS] string
    }
    ```
*   **Réponse - 201 Created** :
    ```json
    {
      "detail": "ok" // string
    }
    ```

### 2.7 Déconnexion
*   **URL** : `POST /api/v1/auth/logout/`
*   **Permissions** : Public
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "Successfully logged out." // string
    }
    ```

### 2.8 Demande de réinitialisation de mot de passe (Mot de passe oublié)
*   **URL** : `POST /api/v1/auth/password/reset/`
*   **Permissions** : Public
*   **Comportement backend** : Envoie un e-mail avec un token sécurisé.
*   **Payload d'entrée** :
    ```json
    {
      "email": "user@example.com" // [REQUIS] string
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "Password reset e-mail has been sent." // string
    }
    ```

### 2.9 Confirmation de réinitialisation (API Directe)
*   **URL** : `POST /api/v1/auth/password/reset/confirm/`
*   **Permissions** : Public
*   **Payload d'entrée** :
    ```json
    {
      "uid": "MTI",                                  // [REQUIS] string (ID en base64)
      "token": "a1b2c3d4-e5f6...",                   // [REQUIS] string (Token)
      "new_password": "NouveauMotDePasse123!",       // [REQUIS] string (min 8 chars)
      "new_password_confirm": "NouveauMotDePasse123!" // [REQUIS] string (doit correspondre)
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "Password has been reset with the new password." // string
    }
    ```

### 2.10 Changement de mot de passe (Connecté)
*   **URL** : `POST /api/v1/auth/password/change/`
*   **Permissions** : Connecté (`IsAuthenticated`)
*   **Payload d'entrée** :
    ```json
    {
      "old_password": "MotDePasseActuel123!",        // [REQUIS] string
      "new_password": "NouveauMotDePasseFort456!",   // [REQUIS] string
      "new_password_confirm": "NouveauMotDePasseFort456!" // [REQUIS] string
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "New password has been saved." // string
    }
    ```

### 2.11 Rafraîchissement du Jeton d'Accès
*   **URL** : `POST /api/v1/auth/token/refresh/`
*   **Permissions** : Public
*   **Payload d'entrée (Mobile uniquement)** :
    ```json
    {
      "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." // [REQUIS] string
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." // string
    }
    ```

### 2.12 Vérification de validité d'un Jeton
*   **URL** : `POST /api/v1/auth/token/verify/`
*   **Permissions** : Public
*   **Payload d'entrée** :
    ```json
    {
      "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." // [REQUIS] string
    }
    ```
*   **Réponse - 200 OK** : `{}`

### 2.13 Authentification Google
*   **URL** : `POST /api/v1/auth/google/`
*   **Permissions** : Public
*   **Payload d'entrée** :
    ```json
    {
      "access_token": "ya29.a0AR...", // [REQUIS] string
      "code": "4/0Ad..."              // [OPTIONNEL] string
    }
    ```
*   **Réponse - 200 OK** : Jetons JWT classiques renvoyés en sortie.

### 2.14 Données de profil simplifiées
*   **URL** : `/api/v1/auth/user/`
*   **Méthodes** : `GET`, `PUT`, `PATCH`
*   **Permissions** : Connecté (`IsAuthenticated`)
*   **Payload d'entrée (PUT / PATCH)** :
    ```json
    {
      "first_name": "Jean", // [OPTIONNEL] string
      "last_name": "Dupont"  // [OPTIONNEL] string
    }
    ```
*   **Réponse - 200 OK (GET & Ecritures)** :
    ```json
    {
      "pk": 1,                     // integer
      "username": "user@mail.com", // string
      "email": "user@mail.com",    // string
      "first_name": "Jean",        // string
      "last_name": "Dupont"        // string
    }
    ```

### 2.15 Profil Utilisateur Complet Exclusif (Recommandé)
*   **URL** : `/api/v1/auth/me/` (alias `/api/v1/auth/me`)
*   **Méthodes** : `GET`, `PUT`, `PATCH`
*   **Permissions** : Connecté (`IsAuthenticated`)
*   **Payload d'entrée (PUT / PATCH)** :
    ```json
    {
      "first_name": "Jean-Pierre",         // [OPTIONNEL] string
      "last_name": "Dupont",               // [OPTIONNEL] string
      "telephone": "237677777777",         // [OPTIONNEL] string (requiert current_password si modifié)
      "current_password": "motdepassefort" // [OPTIONNEL] string (requis uniquement si telephone est modifié)
    }
    ```
*   **Réponse - 200 OK (GET & Ecritures)** :
    ```json
    {
      "user": {
        "id": 1,
        "email": "user@example.com",
        "telephone": "237677777777",
        "first_name": "Jean-Pierre",
        "last_name": "Dupont",
        "role": "client"
      },
      "client": {
        "id": 1,
        "date_naissance": "1995-06-15", // string (YYYY-MM-DD)
        "genre": "homme",               // string ("homme" | "femme" | "mixte" | null)
        "points_fidelite": 150,         // integer
        "date_creation": "2026-05-01T12:00:00Z" // string (datetime)
      },
      "preferences": {
        "familles_olfactives": ["Boisé", "Oriental"], // array of strings
        "humeurs": ["Énergique"],                     // array of strings
        "saisons": ["Automne", "Hiver"],               // array of strings
        "occasions": ["Soirée"],                       // array of strings
        "signes_astrologiques": [],                    // array of strings
        "moments_journee": [],                         // array of strings
        "genres": ["homme"]                            // array of strings
      },
      "favoris": [
        {
          "id": 5,                                             // integer
          "type_produit": "parfum",                            // string ("parfum" | "accessoire")
          "produit_id": 12,                                    // integer
          "nom_produit": "Royal Oud",                          // string
          "prix_produit": "35000.00",                          // string (decimal)
          "image_produit": "http://domain.com/media/image.jpg",// string (URL)
          "detail_url": "http://domain.com/api/v1/shop/...",   // string (URL)
          "date_ajout": "2026-05-25T14:30:00Z"                 // string (datetime)
        }
      ],
      "parfums_personnalises": [
        {
          "id": 1,                                       // integer
          "nom": "Ma Création N°1",                      // string
          "description": "Un parfum d'exception",        // string
          "flacon_id": 2,                                // integer
          "flacon_nom": "Flacon Cristal 100ml",          // string
          "prix_essences": "12500.00",                   // string (decimal)
          "prix_flacon_snapshot": "5000.00",             // string (decimal)
          "prix_total": "17500.00",                      // string (decimal)
          "statut": "validé",                            // string ("brouillon" | "validé" | "production" | "expédié")
          "lignes": [
            {
              "id": 1,                                   // integer
              "essence_type": "catalogue",               // string ("catalogue" | "personnalisee")
              "essence_id": 4,                           // integer
              "essence_nom": "Essence de Patchouli",     // string
              "quantite_ml": 15.00,                      // float
              "prix_par_ml_snapshot": "500.00",          // string (decimal)
              "prix_ligne": "7500.00"                    // string (decimal)
            }
          ]
        }
      ],
      "commandes": []                                    // array of Commandes (voir structure plus bas)
    }
    ```

### 2.16 Demande de Changement d'Email (allauth)
*   **URL** : `POST /api/v1/auth/me/change-email/`
*   **Permissions** : Connecté (`IsAuthenticated`)
*   **Payload d'entrée** :
    ```json
    {
      "email": "nouveau_mail@example.com", // [REQUIS] string (format email unique)
      "current_password": "motdepasseactuel" // [REQUIS] string
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "Un email de confirmation a été envoyé à la nouvelle adresse.", // string
      "email": "nouveau_mail@example.com"                                    // string
    }
    ```

---

## 3. WORKFLOW PRESTATAIRES & RETRAITS MOBILE MONEY

### 3.1 Postuler en tant que Prestataire
*   **URL** : `POST /api/v1/auth/prestataire/apply/`
*   **Permissions** : Connecté (`IsAuthenticated`)
*   **Payload d'entrée** : Aucun
*   **Réponse - 201 Created** :
    ```json
    {
      "detail": "Demande envoyée avec succès." // string
    }
    ```

### 3.2 Tableau de Bord Prestataire
*   **URL** : `GET /api/v1/auth/prestataire/dashboard/`
*   **Permissions** : Prestataire actif
*   **Query Parameters** :
    *   `prestataire_id` : integer `[OPTIONNEL]` (accessible uniquement par l'admin pour visualiser le dashboard d'un partenaire)
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "id": 3,                                      // integer
      "solde_commission": "245000.00",              // string (decimal)
      "taux_commission": "15.00",                   // string (decimal, ex: 15.00%)
      "reduction_client_pourcentage": "5.00",       // string (decimal, ex: 5.00%)
      "code_promo": "ACC-W83K9R1Z",                 // string
      "statut": "actif",                            // string ("actif" | "suspendu" | "en_attente")
      "total_gains": "320000.00",                   // string (decimal)
      "total_retraits": "75000.00",                 // string (decimal)
      "solde_bloque": "0.00",                       // string (decimal)
      "payouts_recents": [
        {
          "id": 1,                                  // integer
          "prestataire": 3,                         // integer (ID)
          "montant": "75000.00",                    // string (decimal)
          "telephone_destination": "237699999999",  // string
          "reference_unique": "payout_847df83c92a", // string
          "statut": "succes",                       // string ("en_cours" | "succes" | "echec")
          "motif_echec": null,                      // string | null
          "date_creation": "2026-05-20T10:00:00Z",  // string (datetime)
          "date_finalisation": "2026-05-20T10:05:00Z" // string (datetime) | null
        }
      ],
      "historique_recent": [
        {
          "id": 12,                                 // integer
          "type_operation": "credit",               // string ("credit" | "retrait")
          "montant": "12500.00",                    // string (decimal)
          "reference_commande": "CMD-2026-9482",    // string
          "date_operation": "2026-05-28T16:30:00Z", // string (datetime)
          "description": "Commission sur la commande CMD-2026-9482" // string
        }
      ]
    }
    ```

### 3.3 Historique Financier Complet du Prestataire
*   **URL** : `GET /api/v1/auth/prestataire/historique/`
*   **Permissions** : Prestataire actif
*   **Query Parameters** :
    *   `type_operation` : string `[OPTIONNEL]` ("credit" | "retrait")
    *   `page` : integer `[OPTIONNEL]` (numéro de page pour la pagination)
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Liste paginée d'objets `CommissionLog` :
    ```json
    {
      "count": 45,
      "next": "http://domain.com/api/v1/auth/prestataire/historique/?page=2",
      "previous": null,
      "results": [
        {
          "id": 12,
          "type_operation": "credit",
          "montant": "12500.00",
          "reference_commande": "CMD-2026-9482",
          "date_operation": "2026-05-28T16:30:00Z",
          "description": "Commission sur la commande CMD-2026-9482"
        }
      ]
    }
    ```

### 3.4 Liste des Demandes de Payouts du Prestataire
*   **URL** : `GET /api/v1/auth/prestataire/payouts/`
*   **Permissions** : Prestataire actif
*   **Query Parameters** :
    *   `statut` : string `[OPTIONNEL]` ("en_cours" | "succes" | "echec")
    *   `page` : integer `[OPTIONNEL]`
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Liste paginée d'objets `PayoutTransaction` (structure identique au champ `payouts_recents` du dashboard).

### 3.5 Webhook Monetbil Mobile Money (Public)
*   **URL** : `POST /api/v1/auth/payout/webhook/` (et `GET`)
*   **Permissions** : Public (`AllowAny`)
*   **Comportement backend** : Monetbil appelle cette URL pour notifier la finalisation d'un virement (crédit Orange/MTN au Cameroun). Si la transaction est notifiée en échec, le solde réservé du prestataire est automatiquement recrédité en BDD.
*   **Payload d'entrée (Transmis par Monetbil)** :
    ```json
    {
      "processing_number": "payout_a9f87c6b54d3e2", // [REQUIS] string (notre référence unique)
      "status": "success",                          // [REQUIS] string ("success" | "failed" | "cancelled")
      "message": "Transfer successful"              // [OPTIONNEL] string
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "Webhook traité avec succès" // string
    }
    ```

### 3.6 Lister les demandes de partenariat en attente (Admin)
*   **URL** : `GET /api/v1/utilisateur/prestataire-requests/`
*   **Permissions** : Admin uniquement (`IsAdminUser`)
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Liste de demandes prestataires à valider :
    ```json
    [
      {
        "id": 4,
        "client": 12,                  // integer (ID)
        "statut": "en_attente",        // string
        "solde_commission": "0.00",    // string (decimal)
        "taux_commission": "0.00",     // string (decimal)
        "code_promo": "",              // string
        "date_creation": "2026-06-03T11:00:00Z"
      }
    ]
    ```

### 3.7 Détail d'une demande de partenariat (Admin)
*   **URL** : `GET /api/v1/utilisateur/prestataire-requests/{id}/`
*   **Permissions** : Admin uniquement
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Objet détaillé de la demande prestataire (structure identique à ci-dessus).

### 3.8 Valider une Demande Prestataire (Admin)
*   **URL** : `PATCH /api/v1/auth/admin/prestataires/validate/{id}/`
*   **Permissions** : Admin uniquement
*   **Comportement backend** : Valide le partenaire, passe son statut à `actif`, génère un code promo unique (`ACC-XXXXXXXX`) et lui envoie un email HTML d'activation.
*   **Payload d'entrée** :
    ```json
    {
      "taux_commission": 15.00,           // [REQUIS] float (Pourcentage de gain, ex: 15.0%)
      "reduction_client_pourcentage": 5.0 // [REQUIS] float (Pourcentage de réduction client, ex: 5.0%)
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "Prestataire validé avec succès.", // string
      "code_promo": "ACC-W83K9R1Z",               // string
      "taux_commission": "15.00",                 // string (decimal)
      "reduction_client_pourcentage": "5.00"      // string (decimal)
    }
    ```

### 3.9 Lister tous les Prestataires (Admin)
*   **URL** : `GET /api/v1/auth/admin/prestataires/`
*   **Permissions** : Admin uniquement
*   **Query Parameters** :
    *   `statut` : string `[OPTIONNEL]` ("actif" | "suspendu" | "en_attente")
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Liste d'objets `Prestataire` avec infos utilisateur liées :
    ```json
    [
      {
        "id": 3,
        "user_details": {
          "id": 10,
          "email": "partenaire@mail.com",
          "telephone": "237699999999",
          "first_name": "Marc",
          "last_name": "Koko",
          "role": "prestataire"
        },
        "solde_commission": "245000.00",
        "taux_commission": "15.00",
        "reduction_client_pourcentage": "5.00",
        "code_promo": "ACC-W83K9R1Z",
        "statut": "actif",
        "date_creation": "2026-05-15T08:00:00Z"
      }
    ]
    ```

### 3.10 Mettre à jour un prestataire (Admin)
*   **URL** : `PATCH /api/v1/auth/admin/prestataires/{id}/update/`
*   **Permissions** : Admin uniquement
*   **Payload d'entrée** :
    ```json
    {
      "taux_commission": 12.00,          // [OPTIONNEL] float
      "reduction_client_pourcentage": 3.0, // [OPTIONNEL] float
      "statut": "suspendu"                 // [OPTIONNEL] string ("actif" | "suspendu")
    }
    ```
*   **Réponse - 200 OK** : Renvoie l'objet prestataire mis à jour.

### 3.11 Demande de Virement Mobile Money (Payout) par l'Admin
*   **URL** : `POST /api/v1/auth/admin/prestataires/{id}/payout/`
*   **Permissions** : Admin uniquement
*   **Comportement backend** : Débite le solde en BDD et initie l'ordre de transfert Monetbil en tâche de fond.
*   **Payload d'entrée** :
    ```json
    {
      "montant": 50000.00 // [REQUIS] float (doit être supérieur à 0 et inférieur ou égal au solde de commission)
    }
    ```
*   **Réponse - 201 Created** :
    ```json
    {
      "id": 4,
      "prestataire": 3,
      "montant": "50000.00",
      "telephone_destination": "237699999999",
      "reference_unique": "payout_a9f87c6b54d3e2",
      "statut": "en_cours",
      "date_creation": "2026-06-01T10:45:00Z",
      "date_finalisation": null
    }
    ```

### 3.12 Suivi global des payouts (Admin)
*   **URL** : `GET /api/v1/auth/admin/payouts/`
*   **Permissions** : Admin uniquement
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Liste de toutes les transactions `PayoutTransaction` du système (structure identique à ci-dessus).

### 3.13 Statistiques Globales de la plateforme (Admin)
*   **URL** : `GET /api/v1/auth/admin/stats/global/`
*   **Permissions** : Admin uniquement
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "total_prestataires": 8,            // integer
      "solde_total_commissions": "845000.00", // string (decimal)
      "total_retraits_succes": "1250000.00", // string (decimal)
      "payouts_en_cours_count": 2         // integer
    }
    ```

---

## 4. MODULE LIVREURS & LIVRAISONS

### 4.1 Promouvoir un Client en tant que Livreur (Admin)
*   **URL** : `POST /api/v1/auth/admin/livreurs/promote/`
*   **Permissions** : Admin uniquement
*   **Payload d'entrée** :
    ```json
    {
      "user_id": 14 // [REQUIS] integer (ID User à promouvoir)
    }
    ```
*   **Réponse - 201 Created** :
    ```json
    {
      "id": 1,
      "photo": null,
      "statut": "disponible",
      "nombre_livraisons": 0,
      "date_embauche": "2026-06-01",
      "user_details": {
        "id": 14,
        "email": "livreur@example.com",
        "telephone": "237688888888",
        "first_name": "Paul",
        "last_name": "Nguene",
        "role": "livreur"
      }
    }
    ```

### 4.2 Assigner un Livreur à une Commande (Admin)
*   **URL** : `POST /api/v1/auth/admin/commandes/{id}/affecter-livreur/`
*   **Permissions** : Admin uniquement
*   **Payload d'entrée** :
    ```json
    {
      "livreur_id": 1 // [REQUIS] integer (ID du livreur à assigner)
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "Commande assignée avec succès au livreur Paul Nguene.", // string
      "statut_livraison": "assignée"                                     // string
    }
    ```

### 4.3 Tableau de Bord Livreur (Livraisons en cours)
*   **URL** : `GET /api/v1/auth/livreur/dashboard/`
*   **Permissions** : Livreur actif
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "id": 1,
      "statut": "disponible",       // string ("disponible" | "en_livraison" | "indisponible")
      "nombre_livraisons": 25,      // integer
      "livraisons_actives": [
        {
          "id": 98,                                    // integer (ID Commande)
          "numero_commande": "CMD-2026-9812",          // string
          "statut": "en_cours_de_livraison",           // string
          "statut_livraison": "assignée",              // string ("assignée" | "en_cours" | "livrée" | "échouée")
          "livraison_nom_complet": "Alice Ebanda",      // string
          "livraison_quartier": "Bastos",              // string
          "livraison_ville": "Yaoundé",                // string
          "livraison_telephone": "237671234567",       // string
          "methode_paiement": "cash",                  // string ("cash" | "om" | "momo")
          "statut_paiement": "non_payé",               // string ("payé" | "non_payé")
          "total_ttc": "43500.00",                     // string (decimal)
          "note_client": "Appeler 10 min avant."       // string
        }
      ]
    }
    ```

### 4.4 Mettre à Jour le Statut d'une Livraison (Livreur)
*   **URL** : `POST /api/v1/auth/livreur/livraisons/{id}/statut/`
*   **Permissions** : Livreur assigné à cette commande uniquement
*   **Comportement backend** : Si `action` est `"livrer"`, passe le paiement cash de la commande à `"payé"` et incrémente le compteur du livreur.
*   **Payload d'entrée** :
    ```json
    {
      "action": "echouer",                         // [REQUIS] string ("livrer" | "echouer")
      "motif": "Client injoignable après 3 appels" // [OPTIONNEL] string (requis uniquement si action="echouer")
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "Livraison validée avec succès.", // string
      "statut_livraison": "livrée"                // string ("livrée" | "échouée")
    }
    ```

### 4.5 Lister les livreurs (Admin)
*   **URL** : `GET /api/v1/auth/admin/livreurs/`
*   **Permissions** : Admin uniquement
*   **Query Parameters** :
    *   `statut` : string `[OPTIONNEL]` ("disponible" | "en_livraison" | "indisponible")
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Liste de tous les profils livreurs (structure identique à la réponse de promotion livreur).

### 4.6 Modifier un livreur (Admin)
*   **URL** : `PATCH /api/v1/auth/admin/livreurs/{id}/`
*   **Permissions** : Admin uniquement
*   **Payload d'entrée** :
    ```json
    {
      "statut": "indisponible" // [OPTIONNEL] string ("disponible" | "en_livraison" | "indisponible")
    }
    ```
*   **Réponse - 200 OK** : Objet livreur modifié.

### 4.7 Suivi global de toutes les livraisons (Admin)
*   **URL** : `GET /api/v1/auth/admin/livraisons/`
*   **Permissions** : Admin uniquement
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Liste de toutes les commandes avec informations de livraison (structure identique à la liste `livraisons_actives` du dashboard livreur).

### 4.8 Historique personnel du livreur
*   **URL** : `GET /api/v1/auth/livreur/livraisons/`
*   **Permissions** : Livreur connecté
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** : Liste de toutes ses livraisons passées (livrées et échouées).

---

## 5. MODULE CATALOGUE & BOUTIQUE (`/api/v1/shop/`)

### 5.1 Parfums
*   **URL** : `/api/v1/shop/parfums/`
*   **Méthodes** : `GET` (Public), `POST` (Création - Admin uniquement)
*   **Query Parameters (GET)** :
    *   `page` : integer `[OPTIONNEL]` (pagination de 50 par page)
    *   `search` : string `[OPTIONNEL]` (recherche nom/description/notes)
    *   `contenance_ml` : integer `[OPTIONNEL]`
    *   `est_bestseller` : boolean `[OPTIONNEL]`
    *   `est_nouveau` : boolean `[OPTIONNEL]`
    *   `famille_olfactive` : string `[OPTIONNEL]`
    *   `genre` : string `[OPTIONNEL]` ("homme" | "femme" | "mixte")
    *   `humeur` : string `[OPTIONNEL]`
    *   `intensite` : string `[OPTIONNEL]`
    *   `occasion` : string `[OPTIONNEL]`
    *   `saison` : string `[OPTIONNEL]`
    *   `prix_min` / `prix_max` : string (decimal) `[OPTIONNEL]`
    *   `tags` : string `[OPTIONNEL]` (IDs séparés par virgules: "1,4")
    *   `ordering` : string `[OPTIONNEL]` ("prix_unitaire", "-prix_unitaire", "nom", "-date_creation")
*   **Payload attendu (POST - Création Administrateur)** :
    ```json
    {
      "nom": "Royal Oud",                    // [REQUIS] string
      "slug": "royal-oud",                   // [OPTIONNEL] string (auto-généré si vide)
      "reference_sku": "PRF-ROY-OUD",        // [OPTIONNEL] string (unique)
      "description_courte": "Description",   // [OPTIONNEL] string
      "description_longue": "Description L", // [OPTIONNEL] string
      "description_ia": "Description IA",    // [OPTIONNEL] string
      "contenance_ml": 100,                  // [REQUIS] integer (positif)
      "prix_unitaire": "35000.00",           // [REQUIS] string (decimal)
      "prix_promotionnel": null,             // [OPTIONNEL] string (decimal)
      "genre_cible": "mixte",                // [REQUIS] string ("homme" | "femme" | "mixte")
      "intensite": "forte",                  // [REQUIS] string ("légère" | "moyenne" | "forte" | "très forte")
      "notes_tete": "Citron",                // [OPTIONNEL] string
      "notes_coeur": "Oud",                  // [OPTIONNEL] string
      "notes_fond": "Santal",                // [OPTIONNEL] string
      "tags": [1, 2],                        // [OPTIONNEL] tableau d'IDs de tags
      "est_nouveau": true,                   // [OPTIONNEL] boolean (défaut: false)
      "est_bestseller": false,               // [OPTIONNEL] boolean (défaut: false)
      "stock_quantite": 50,                  // [REQUIS] integer
      "seuil_alerte_stock": 5,               // [REQUIS] integer
      "categorie": 1,                        // [REQUIS] integer (ID CategorieParfum)
      "image_principale": null,              // [OPTIONNEL] fichier image (multipart/form-data)
      "images_supplementaires": [],          // [OPTIONNEL] tableau d'images
      "actif": true                          // [OPTIONNEL] boolean (défaut: true)
    }
    ```
*   **Réponse - 200 OK (GET Liste - Public)** :
    ```json
    {
      "count": 1,
      "next": null,
      "previous": null,
      "results": [
        {
          "id": 12,
          "nom": "Royal Oud",
          "slug": "royal-oud",
          "prix_unitaire": "35000.00",
          "prix_actuel": "35000.00",
          "en_promotion": false,
          "genre_cible": "mixte",
          "intensite": "forte",
          "image_principale": "http://domain.com/media/parfums/royal-oud.jpg",
          "is_favori": false,
          "categorie": 1
        }
      ]
    }
    ```
*   **Détail d'un Parfum** : `GET /api/v1/shop/parfums/{slug}/` (Public)
    *   *Payload d'entrée* : Aucun
    *   *Réponse - 200 OK* :
        ```json
        {
          "id": 12,
          "nom": "Royal Oud",
          "slug": "royal-oud",
          "reference_sku": "PRF-ROY-OUD",
          "description_courte": "Description",
          "contenance_ml": 100,
          "prix_unitaire": "35000.00",
          "prix_actuel": "35000.00",
          "taux_reduction": null,
          "en_promotion": false,
          "genre_cible": "mixte",
          "intensite": "forte",
          "notes_tete": "Citron",
          "notes_coeur": "Oud",
          "notes_fond": "Santal",
          "tags": [ { "id": 1, "nom": "Oriental", "slug": "oriental", "type": "famille_olfactive" } ],
          "famille_olfactive": ["Oriental"],
          "humeurs_compatibles": [],
          "occasions": [],
          "saisons_compatibles": [],
          "est_nouveau": true,
          "est_bestseller": false,
          "image_principale": "http://domain.com/media/parfums/royal-oud.jpg",
          "images_supplementaires": [],
          "stock_quantite": 50,
          "date_creation": "2026-05-10T08:00:00Z",
          "is_favori": false,
          "categorie": 1,
          "produits_similaires": [
            {
              "id": 15,
              "nom": "Oud Impérial",
              "slug": "oud-imperial",
              "prix_actuel": "42000.00",
              "image_principale": "http://domain.com/media/parfums/oud-imperial.jpg"
            }
          ]
        }
        ```
*   **Modifier / Supprimer** : `PUT`, `PATCH`, `DELETE` sur `/api/v1/shop/parfums/{slug}/` (Admin)
*   **Bascule Favori** : `POST /api/v1/shop/parfums/{slug}/favori/` (Connecté)
    *   *Payload d'entrée* : Aucun
    *   *Réponse - 200 OK* : `{"detail": "Parfum ajouté aux favoris."}` (ou `"Parfum retiré..."`)
*   **Bestsellers Historique** : `GET /api/v1/shop/parfums/bestsellers/`
*   **Ventes Hotsellers** : `GET /api/v1/shop/parfums/hotsellers/`

### 5.2 Accessoires
*   **URL** : `/api/v1/shop/accessoires/`
*   **Méthodes** : `GET` (Public), `POST` (Création - Admin uniquement)
*   **Query Parameters (GET)** : `couleur`, `en_stock`, `matiere`, `taille`, `type_accessoire`, `type_nom`, `prix_min`, `prix_max`, `search`, `ordering`.
*   **Payload attendu (POST - Création Administrateur)** :
    ```json
    {
      "nom": "Pochette Cuir",                // [REQUIS] string
      "slug": "pochette-cuir",               // [OPTIONNEL] string (auto-généré)
      "reference_sku": "ACC-PCH-CUIR",       // [OPTIONNEL] string (unique)
      "type_accessoire": 1,                  // [REQUIS] integer (ID TypeAccessoire)
      "description_courte": "Description",   // [OPTIONNEL] string
      "description_longue": "Description L", // [OPTIONNEL] string
      "matiere": "Cuir",                     // [OPTIONNEL] string
      "couleur": "Noir",                     // [OPTIONNEL] string
      "taille": "Standard",                  // [OPTIONNEL] string
      "prix_unitaire": "12000.00",           // [REQUIS] string (decimal)
      "prix_promotionnel": null,             // [OPTIONNEL] string (decimal)
      "stock_quantite": 30,                  // [REQUIS] integer
      "seuil_alerte_stock": 3,               // [REQUIS] integer
      "poids_grammes": 150,                  // [REQUIS] integer
      "image_principale": null,              // [OPTIONNEL] fichier image (multipart/form-data)
      "images_supplementaires": [],          // [OPTIONNEL] tableau d'images
      "actif": true,                         // [OPTIONNEL] boolean (défaut: true)
      "est_bestseller": false,               // [OPTIONNEL] boolean
      "est_hotseller": false                 // [OPTIONNEL] boolean
    }
    ```
    **Important image** : pour envoyer `image_principale`, utiliser `multipart/form-data`. En JSON, laisser `null` ou omettre le champ.
*   **Réponse - 200 OK (GET Liste - Public)** :
    ```json
    {
      "count": 1,
      "results": [
        {
          "id": 1,
          "nom": "Pochette Cuir",
          "slug": "pochette-cuir",
          "type_accessoire": { "id": 1, "nom": "Coffret", "slug": "coffret", "description": "Coffrets" },
          "prix_unitaire": "12000.00",
          "prix_actuel": "12000.00",
          "en_promotion": false,
          "image_principale": null,
          "is_favori": false
        }
      ]
    }
    ```
*   **Détail d'un Accessoire** : `GET /api/v1/shop/accessoires/{slug}/` (Public)
    *   *Réponse - 200 OK* :
        ```json
        {
          "id": 1,
          "nom": "Pochette Cuir",
          "slug": "pochette-cuir",
          "reference_sku": "ACC-PCH-CUIR",
          "type_accessoire": 1,
          "description_courte": "Description",
          "matiere": "Cuir",
          "couleur": "Noir",
          "taille": "Standard",
          "prix_unitaire": "12000.00",
          "prix_actuel": "12000.00",
          "taux_reduction": null,
          "en_promotion": false,
          "stock_quantite": 30,
          "seuil_alerte_stock": 3,
          "poids_grammes": 150,
          "image_principale": "http://domain.com/media/accessoires/pochette-cuir/image.jpg",
          "images_supplementaires": [],
          "actif": true,
          "est_bestseller": false,
          "est_hotseller": false,
          "date_creation": "2026-05-15T08:00:00Z",
          "date_modification": "2026-05-15T08:00:00Z",
          "is_favori": false,
          "produits_similaires": []
        }
        ```
*   **Modifier / Supprimer** : `PUT`, `PATCH`, `DELETE` sur `/api/v1/shop/accessoires/{slug}/` (Admin)
*   **Bascule Favori** : `POST /api/v1/shop/accessoires/{slug}/favori/` (Connecté)

### 5.3 Flacons
*   **URL** : `/api/v1/shop/flacons/`
*   **Méthodes** : `GET` (Public), `POST` (Création - Admin uniquement)
*   **Query Parameters (GET)** : `contenance_ml`, `couleur`, `en_stock`, `matiere`, `type_flacon`, `type_nom`, `stock_min`, `stock_max`, `search`, `ordering`.
*   **Payload attendu (POST - Création Administrateur)** :
    ```json
    {
      "nom": "Flacon Cristal 100ml",         // [REQUIS] string
      "reference_sku": "FLC-CRT-100",        // [OPTIONNEL] string (unique)
      "type_flacon": 1,                      // [REQUIS] integer (ID TypeFlacon)
      "contenance_ml": 100,                  // [REQUIS] integer (positif)
      "matiere": "Verre",                    // [REQUIS] string
      "couleur": "Transparent",              // [REQUIS] string
      "hauteur_cm": "15.00",                 // [OPTIONNEL] string (decimal)
      "largeur_cm": "6.00",                  // [OPTIONNEL] string (decimal)
      "poids_grammes": 200,                  // [REQUIS] integer
      "prix_unitaire": "5000.00",            // [REQUIS] string (decimal)
      "stock_quantite": 150,                 // [REQUIS] integer
      "seuil_alerte_stock": 10,              // [REQUIS] integer
      "image_principale": null,              // [OPTIONNEL] fichier image (multipart/form-data)
      "images_supplementaires": [],          // [OPTIONNEL] tableau d'images
      "actif": true                          // [OPTIONNEL] boolean (défaut: true)
    }
    ```
    **Important image** : pour envoyer `image_principale`, utiliser `multipart/form-data`. En JSON, laisser `null` ou omettre le champ.
*   **Réponse - 200 OK (GET Liste - Public)** :
    ```json
    {
      "count": 1,
      "results": [
        {
          "id": 1,
          "nom": "Flacon Cristal 100ml",
          "slug": "flacon-cristal-100ml",
          "type_flacon": { "id": 1, "nom": "Spray", "slug": "spray" },
          "contenance_ml": 100,
          "matiere": "Verre",
          "couleur": "Transparent",
          "prix_unitaire": "5000.00",
          "stock_quantite": 150,
          "stock_suffisant": true,
          "image_principale": "http://domain.com/media/flacons/FLC-CRT-100/image.jpg",
          "actif": true,
          "date_creation": "2026-05-15T08:00:00Z",
          "date_modification": "2026-05-15T08:00:00Z"
        }
      ]
    }
    ```
*   **Détail d'un Flacon** : `GET /api/v1/shop/flacons/{id}/` (Public)
    *   *Réponse - 200 OK* : Objet flacon complet détaillé avec hauteur, largeur, poids.
*   **Modifier / Supprimer** : `PUT`, `PATCH`, `DELETE` sur `/api/v1/shop/flacons/{id}/` (Admin)

### 5.4 Favoris Directs (Par ID de produit)
*   **URL** : `/api/v1/shop/favoris/`
*   **Méthodes** : `GET` (Liste), `POST` (Création)
*   **Permissions** : Connecté (`IsAuthenticated`)
*   **Payload attendu (POST)** :
    ```json
    {
      "parfum": 12,        // [OPTIONNEL] integer (Requis si accessoire est absent)
      "accessoire": null   // [OPTIONNEL] integer (Requis si parfum est absent)
    }
    ```
*   **Réponse - 201 Created** :
    ```json
    {
      "id": 5,
      "date_ajout": "2026-05-25T14:30:00Z",
      "nom_produit": "Royal Oud",
      "prix_produit": "35000.00",
      "image_produit": "http://domain.com/media/image.jpg",
      "type_produit": "parfum",
      "slug_produit": "royal-oud",
      "id_produit": 12
    }
    ```
*   **Supprimer un favori** : `DELETE /api/v1/shop/favoris/{id}/`
    *   *Payload d'entrée* : Aucun
    *   *Réponse - 204 No Content* : (Aucun contenu, suppression validée).

### 5.5 Les Tags (Mots-clés olfactifs et thématiques)
*   **URL** : `/api/v1/shop/tags/`
*   **Méthodes** : `GET`, `POST` (Création - Admin uniquement)
*   **Payload attendu (POST / PUT)** :
    ```json
    {
      "nom": "Mystérieux",      // [REQUIS] string
      "slug": "mysterieux",     // [OPTIONNEL] string (auto-généré si absent)
      "type": "humeur"          // [REQUIS] string ("famille_olfactive" | "humeur" | "saison" | "occasion" | "signe_astrologique" | "moment_journee")
    }
    ```
*   **Réponse - 201 Created** :
    ```json
    {
      "id": 8,
      "nom": "Mystérieux",
      "slug": "mysterieux",
      "type": "humeur"
    }
    ```
*   **Détail, Modifier & Supprimer** : `GET`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/shop/tags/{slug}/` (Admin)
*   **Endpoints de select pour le frontend** :
    *   `GET`, `POST`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/shop/tags-parfum/`
    *   `GET`, `POST`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/lab/tags-essence/`
    *   Lecture publique, écriture admin uniquement.
    *   Ces endpoints servent au même composant select : lire les options, ajouter un tag absent, modifier un tag existant ou supprimer un tag.
    *   Détail/modification/suppression par slug : `/api/v1/shop/tags-parfum/{slug}/` et `/api/v1/lab/tags-essence/{slug}/`.
    *   Filtres : `?type=humeur`, `?search=floral`, `?ordering=nom`.
    *   Réponse d'option :
        ```json
        {
          "id": 1,
          "libelle": "Floral",
          "nom": "Floral",
          "slug": "floral-famille-12345",
          "type": "famille_olfactive"
        }
        ```
    *   Le frontend affiche `libelle` ou `nom`, conserve `id`, puis envoie `tags: [id]` pour un parfum ou `tag_ids: [id]` pour une essence.
    *   Types acceptés pour `tags-parfum` : `famille_olfactive`, `humeur`, `saison`, `occasion`.
    *   Types acceptés pour `tags-essence` : `famille_olfactive`, `humeur`, `saison`, `occasion`, `signe_astrologique`, `moment_journee`.

### 5.6 Catégories de Parfums
*   **URL** : `/api/v1/shop/categories-parfum/`
*   **Méthodes** : `GET`, `POST` (Création - Admin uniquement)
*   **Comportement automatique** : Modifier `taux_reduction` met automatiquement à jour le prix promotionnel de tous les parfums liés.
*   **Payload attendu (POST / PUT)** :
    ```json
    {
      "nom": "Collection Prestige",  // [REQUIS] string
      "slug": "collection-prestige", // [OPTIONNEL] string (auto-généré)
      "description": "Formulations uniques", // [OPTIONNEL] string
      "image": null,                 // [OPTIONNEL] fichier image
      "ordre_affichage": 1,          // [OPTIONNEL] integer (défaut: 0)
      "actif": true,                 // [OPTIONNEL] boolean (défaut: true)
      "taux_reduction": "15.00"      // [OPTIONNEL] string (decimal, défaut: "0.00")
    }
    ```
*   **Réponse - 201 Created** :
    ```json
    {
      "id": 3,
      "nom": "Collection Prestige",
      "slug": "collection-prestige",
      "description": "Formulations uniques",
      "image": null,
      "ordre_affichage": 1,
      "actif": true,
      "taux_reduction": "15.00",
      "date_creation": "2026-06-01T11:20:00Z"
    }
    ```
*   **Détail, Modifier & Supprimer** : `GET`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/shop/categories-parfum/{id}/` (Admin)

### 5.7 Types d'Accessoires
*   **URL** : `/api/v1/shop/types-accessoire/`
*   **Méthodes** : `GET`, `POST` (Création - Admin uniquement)
*   **Comportement automatique** : modifier `taux_reduction` met automatiquement à jour les prix promotionnels des accessoires liés à ce type.
*   **Payload attendu (POST / PUT)** :
    ```json
    {
      "nom": "Bougie Parfumée",          // [REQUIS] string
      "slug": "bougie-parfumee",         // [OPTIONNEL] string (auto-généré)
      "description": "Créateurs d'ambiance", // [OPTIONNEL] string
      "icone": null,                     // [OPTIONNEL] fichier image (multipart/form-data)
      "actif": true,                     // [OPTIONNEL] boolean (défaut: true)
      "taux_reduction": "0.00"           // [OPTIONNEL] string (decimal, défaut: "0.00")
    }
    ```
    **Important image** : `icone` est maintenant un champ uploadable. Pour envoyer un fichier, utiliser `multipart/form-data`. En réponse, `icone` est une URL absolue si le fichier existe.
*   **Réponse - 201 Created** :
    ```json
    {
      "id": 1,
      "nom": "Bougie Parfumée",
      "slug": "bougie-parfumee-12345",
      "description": "Créateurs d'ambiance",
      "icone": "http://domain.com/media/types/accessoires/bougie-parfumee/icone.png",
      "actif": true,
      "taux_reduction": "0.00",
      "date_creation": "2026-06-06T12:00:00Z"
    }
    ```
*   **Détail, Modifier & Supprimer** : `GET`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/shop/types-accessoire/{id}/` (Admin)

### 5.8 Types de Flacons
*   **URL** : `/api/v1/shop/types-flacon/`
*   **Méthodes** : `GET`, `POST` (Création - Admin uniquement)
*   **Comportement automatique** : modifier `taux_reduction` met automatiquement à jour les prix promotionnels des flacons liés à ce type.
*   **Payload attendu (POST / PUT)** :
    ```json
    {
      "nom": "Spray Vaporisateur",     // [REQUIS] string
      "slug": "spray-vaporisateur",    // [OPTIONNEL] string (auto-généré)
      "description": "Diffusion fine", // [OPTIONNEL] string
      "image": null,                   // [OPTIONNEL] fichier image (multipart/form-data)
      "actif": true,                   // [OPTIONNEL] boolean (défaut: true)
      "taux_reduction": "0.00"         // [OPTIONNEL] string (decimal, défaut: "0.00")
    }
    ```
    **Important image** : `image` est maintenant un champ uploadable. Pour envoyer un fichier, utiliser `multipart/form-data`. En réponse, `image` est une URL absolue si le fichier existe.
*   **Réponse - 201 Created** :
    ```json
    {
      "id": 1,
      "nom": "Spray Vaporisateur",
      "slug": "spray-vaporisateur-12345",
      "description": "Diffusion fine",
      "image": "http://domain.com/media/types/flacons/1/image.png",
      "actif": true,
      "taux_reduction": "0.00",
      "date_creation": "2026-06-06T12:00:00Z"
    }
    ```
*   **Détail, Modifier & Supprimer** : `GET`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/shop/types-flacon/{id}/` (Admin)

### 5.9 Produits Essences Finis (Essences vendues prêtes en flacon)
*   **URL** : `/api/v1/shop/produits-essence/`
*   **Méthodes** : `GET`, `POST` (Création - Admin uniquement)
*   **Payload attendu (POST / PUT)** :
    ```json
    {
      "essence": 4,                    // [REQUIS] integer (ID de l'essence brute)
      "taille_ml": 30,                 // [REQUIS] integer (choix: 10 | 30 | 50 | 100)
      "prix": "18000.00",              // [REQUIS] string (decimal)
      "prix_promotionnel": "15000.00", // [OPTIONNEL] string (decimal)
      "stock_disponible": 75,          // [REQUIS] integer
      "actif": true                    // [OPTIONNEL] boolean (défaut: true)
    }
    ```
*   **Réponse - 201 Created** :
    ```json
    {
      "id": 15,
      "essence": 4,
      "taille_ml": 30,
      "prix": "18000.00",
      "prix_promotionnel": "15000.00",
      "prix_actuel": "15000.00",
      "prix_par_ml": "500.00",
      "stock_disponible": 75,
      "stock_precedent": 0,
      "actif": true
    }
    ```
*   **Détail, Modifier & Supprimer** : `GET`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/shop/produits-essence/{id}/` (Admin)

---

## 6. MODULE LABORATOIRE DIY & ASSISTANT IA (`/api/v1/lab/`)

### 6.1 Recommandation IA par Prompt Libre
*   **URL** : `POST /api/v1/lab/ia-recommandation/`
*   **Permissions** : Public (`AllowAny`)
*   **Payload attendu (Request Body)** :
    ```json
    {
      "prompt": "Je cherche un parfum boisé et épicé, très mystérieux pour une soirée d'hiver." // [REQUIS] string
    }
    ```
*   **Réponse - 200 OK** :
    ```json
    {
      "message": "D'après vos envies de mystère et d'épices, voici une proposition sur mesure...", // string
      "quantite_demandee_ml": 50,                                                                  // integer
      "flacon": {
        "id": 2,                                                                                   // integer
        "nom": "Flacon Cristal 50ml",                                                              // string
        "prix_unitaire": "3500.00"                                                                 // string (decimal)
      },
      "parfums_existants": [
        {
          "id": 12,
          "nom": "Royal Oud",
          "prix_unitaire": "35000.00",
          "image_principale": "http://domain.com/media/image.jpg"
        }
      ],
      "essences_pre_faites": [
        {
          "id": 4,
          "lot_essence_id": 1,
          "nom": "Essence de Patchouli",
          "code_reference": "ESS-PAT",
          "prix_par_ml": "500.00",
          "quantite_ml": 10.5,
          "prix_total_quantite": "5250.00"
        }
      ],
      "ingredients_sur_mesure": [
        {
          "id": 8,
          "nom": "Huile essentielle de Cèdre Noir",
          "prix_par_ml": "600.00",
          "quantite_ml": 4.5,
          "prix_total_quantite": "2700.00"
        }
      ],
      "accessoires": [
        {
          "id": 3,
          "nom": "Diffuseur d'ambiance Gold",
          "prix_unitaire": "12000.00",
          "image_principale": "http://domain.com/media/accessoires/diffuseur.jpg"
        }
      ]
    }
    ```

### 6.2 Essences Brutes (Matières Premières)
*   **URL** : `/api/v1/lab/essences/`
*   **Méthodes** : `GET` (Public), `POST` (Création - Admin uniquement)
*   **Payload attendu (POST - Création Administrateur)** :
    ```json
    {
      "marque": "Exclusif",                  // [REQUIS] string
      "nom": "Essence de Patchouli",         // [REQUIS] string
      "slug": null,                          // [OPTIONNEL] string (auto-généré si absent/null)
      "categorie": "premium",                // [OPTIONNEL] string ("super_premium" | "premium" | "high", défaut: "premium")
      "code_reference": "ESS-PAT",           // [REQUIS] string (unique)
      "description": "Note boisée",          // [OPTIONNEL] string
      "description_ia": "",                  // [OPTIONNEL] string
      "fournisseur": "Hervé S.A.",           // [OPTIONNEL] string
      "origine_pays": "Cameroun",            // [OPTIONNEL] string
      "concentration_max": "15.00",          // [OPTIONNEL] string decimal ou null
      "couleur": "Marron",                   // [OPTIONNEL] string
      "duree": "longue",                     // [OPTIONNEL] string libre
      "intensite": "forte",                  // [OPTIONNEL] string ("légère" | "moyenne" | "forte" | "très forte" | "")
      "genre_cible": "mixte",                // [OPTIONNEL] string ("homme" | "femme" | "mixte", défaut: "mixte")
      "notes_tete": "Citron",                // [OPTIONNEL] string
      "notes_coeur": "Patchouli",            // [OPTIONNEL] string
      "notes_fond": "Santal",                // [OPTIONNEL] string
      "tag_ids": [1, 2, 3],                  // [OPTIONNEL] array d'IDs Tag; remplit automatiquement tag_essence
      "prix_par_ml": "500.00",               // [OPTIONNEL] string decimal (défaut: "0.00")
      "actif": true,                         // [OPTIONNEL] boolean (défaut: true)
      "initial_lot": {                       // [OPTIONNEL] crée le premier lot labo lié
        "stock_ml": "1000.00",               // [OPTIONNEL] string decimal
        "seuil_alerte_ml": "100.00",         // [OPTIONNEL] string decimal ou null
        "reference_fournisseur": "LOT-001"   // [OPTIONNEL] string
      },
      "produits_finis": [                    // [OPTIONNEL] crée les formats vendables liés
        {
          "taille_ml": 10,                   // [REQUIS dans l'objet] integer
          "prix": "5000.00",                 // [REQUIS dans l'objet] string decimal
          "prix_promotionnel": null,         // [OPTIONNEL] string decimal ou null
          "stock_disponible": 20             // [OPTIONNEL] integer (défaut: 0)
        }
      ]
    }
    ```
    **Champs auto-générés / lecture seule** : `id`, `date_creation`, `date_modification`, `tags`, `famille_olfactive`, `humeurs_compatibles`, `occasions`, `saisons_compatibles`, `signes_astrologiques_compatibles`, `moments_journee`.
    **Fonctionnement des tags** : récupérer les options via `GET /api/v1/lab/tags-essence/`, afficher `libelle` ou `nom`, conserver `id`, puis envoyer `tag_ids`. Le backend crée les lignes dans `tag_essence`.
    **Contraintes** : `code_reference` est unique. Le triplet `marque + nom + categorie` doit être unique. Le détail/modification/suppression d'une essence utilise le `slug`.
*   **Réponse - 200 OK (GET Liste - Public)** :
    ```json
    {
      "count": 1,
      "results": [
        {
          "id": 4,
          "nom": "Essence de Patchouli",
          "slug": "essence-patchouli",
          "code_reference": "ESS-PAT",
          "prix_par_ml": "500.00",
          "genre_cible": "mixte",
          "intensite": "forte",
          "actif": true
        }
      ]
    }
    ```
*   **Réponse - 201 Created (POST)** :
    ```json
    {
      "id": 4,
      "marque": "Exclusif",
      "nom": "Essence de Patchouli",
      "slug": "exclusif-essence-de-patchouli-12345",
      "categorie": "premium",
      "code_reference": "ESS-PAT",
      "description": "Note boisée",
      "description_ia": "",
      "fournisseur": "Hervé S.A.",
      "origine_pays": "Cameroun",
      "concentration_max": "15.00",
      "couleur": "Marron",
      "duree": "longue",
      "intensite": "forte",
      "genre_cible": "mixte",
      "notes_tete": "Citron",
      "notes_coeur": "Patchouli",
      "notes_fond": "Santal",
      "tags": [
        {
          "id": 1,
          "nom": "Boisé",
          "slug": "boise-famille-12345",
          "type": "famille_olfactive"
        }
      ],
      "famille_olfactive": ["Boisé"],
      "humeurs_compatibles": [],
      "occasions": [],
      "saisons_compatibles": [],
      "signes_astrologiques_compatibles": [],
      "moments_journee": [],
      "prix_par_ml": "500.00",
      "actif": true,
      "date_creation": "2026-06-06T12:00:00Z",
      "date_modification": "2026-06-06T12:00:00Z"
    }
    ```
*   **Détail, Modifier & Supprimer** : `GET`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/lab/essences/{slug}/` (Admin)

### 6.3 Ingrédients de Base
*   **URL** : `/api/v1/lab/ingredients/`
*   **Méthodes** : `GET`, `POST` (Création - Admin uniquement)
*   **Payload attendu (POST / PUT)** :
    ```json
    {
      "nom": "Cèdre Noir",           // [REQUIS] string
      "slug": "cedre-noir",          // [OPTIONNEL] string (auto-généré)
      "description": "Bois sombre",  // [OPTIONNEL] string
      "prix_par_ml": "500.00",       // [REQUIS] string (decimal)
      "stock_ml": "1000.00",         // [REQUIS] string (decimal)
      "actif": true                  // [OPTIONNEL] boolean (défaut: true)
    }
    ```
*   **Détail, Modifier & Supprimer** : `GET`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/lab/ingredients/{id}/` (Admin)

### 6.4 Essences Personnalisées (Mélanges Ingrédients Client)
*   **URL** : `/api/v1/lab/essences-perso/`
*   **Méthodes** : `GET` (Liste propre), `POST` (Création)
*   **Permissions** : Connecté (`IsAuthenticated`)
*   **Comportement automatique** : Calcule automatiquement le coût au ml du mélange.
*   **Payload attendu (POST)** :
    ```json
    {
      "nom": "Mon Essence Boisée Secrète", // [REQUIS] string
      "lignes": [                          // [REQUIS] tableau de lignes (min 1)
        {
          "ingredient": 8,                 // [REQUIS] integer (ID Ingrédient)
          "quantite_ml": 10.0              // [REQUIS] float (volume en ml)
        },
        {
          "ingredient": 11,
          "quantite_ml": 5.0
        }
      ]
    }
    ```
*   **Réponse - 201 Created** :
    ```json
    {
      "id": 3,
      "nom": "Mon Essence Boisée Secrète",
      "prix_par_ml_calcule": "620.00",
      "lignes": [
        {
          "id": 14,
          "ingredient": 8,
          "ingredient_detail": { "id": 8, "nom": "Cèdre Noir", "prix_par_ml": "600.00" },
          "quantite_ml": "10.00",
          "prix_ligne": "6000.00"
        }
      ],
      "date_creation": "2026-06-01T10:00:00Z"
    }
    ```
*   **Détail, Modifier & Supprimer** : `GET`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/lab/essences-perso/{id}/` (Client)

### 6.5 Parfums Personnalisés (DIY Flacon + Essences)
*   **URL** : `/api/v1/lab/parfums-perso/`
*   **Méthodes** : `GET` (Liste propre), `POST` (Création)
*   **Permissions** : Connecté (`IsAuthenticated`)
*   **Règle métier validée** : Somme des ml des lignes <= 45% du volume du flacon.
*   **Payload attendu (POST)** :
    ```json
    {
      "nom": "Mon Chef-d'Œuvre",           // [OPTIONNEL] string (auto-généré si vide)
      "description": "Formule d'hiver",    // [OPTIONNEL] string
      "flacon": 2,                         // [REQUIS] integer (ID Flacon)
      "enregistre": true,                  // [OPTIONNEL] boolean (défaut: false, si faux=brouillon temporaire)
      "lignes": [                          // [REQUIS] tableau de lignes (min 1)
        {
          "essence": 1,                    // [OPTIONNEL] integer (ID LotEssence brute, requis si essence_personnalisee absent)
          "essence_personnalisee": null,   // [OPTIONNEL] integer (ID EssencePersonnalisee du client, requis si essence absent)
          "quantite_ml": 15.0              // [REQUIS] float
        }
      ]
    }
    ```
*   **Réponse - 201 Created** :
    ```json
    {
      "id": 8,
      "nom": "Mon Chef-d'Œuvre",
      "flacon": 2,
      "flacon_detail": { "id": 2, "nom": "Flacon Cristal 100ml", "contenance_ml": 100, "prix_unitaire": "5000.00" },
      "description": "Formule d'hiver",
      "prix_essences": "13500.00",
      "prix_flacon_snapshot": "5000.00",
      "prix_total": "18500.00",
      "statut": "brouillon",
      "enregistre": true,
      "lignes": [
        {
          "id": 22,
          "essence": 1,
          "essence_personnalisee": null,
          "quantite_ml": "15.00",
          "prix_par_ml_snapshot": "500.00",
          "prix_ligne": "7500.00"
        }
      ],
      "date_creation": "2026-06-01T10:10:00Z"
    }
    ```
*   **Détail, Modifier & Supprimer** : `GET`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/lab/parfums-perso/{id}/`
*   **Recalculer le prix** : `POST /api/v1/lab/parfums-perso/{id}/recalculer/`
    *   *Payload d'entrée* : Aucun. recalcul et met à jour le prix total.

### 6.6 Lots d'Essence (Réserve physique boutique/labo)
*   **URL** : `/api/v1/lab/lots-essence/`
*   **Méthodes** : `GET`, `POST`, `PUT`, `PATCH`, `DELETE` (Admin/Laborantin)
*   **Payload attendu (POST / PUT)** :
    ```json
    {
      "essence": 4,                        // [REQUIS] integer (ID Essence brute)
      "stock_ml": "5000.00",               // [REQUIS] string (decimal)
      "seuil_alerte_ml": "100.00",         // [REQUIS] string (decimal)
      "reference_fournisseur": "LOT-552A", // [OPTIONNEL] string
      "actif": true                        // [OPTIONNEL] boolean (défaut: true)
    }
    ```

### 6.7 Suivi de l'Inventaire Labo
*   **URL** : `/api/v1/lab/labo/essences/`
*   **Méthodes** : `GET`, `POST` (Admin/Laborantin)
*   **Détail, Modifier & Supprimer** : `GET`, `PUT`, `PATCH`, `DELETE` sur `/api/v1/lab/labo/essences/{id}/` (Admin)

---

## 7. MODULE NOTIFICATIONS & SUIVI ADMINISTRATIF (`/api/v1/utilisateur/`)

### 7.1 Alertes Système Administrateur (Notifications)
*   **URL** : `/api/v1/utilisateur/notifications/`
*   **Méthode** : `GET`
*   **Permissions** : Admin uniquement
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    [
      {
        "id": 104,
        "type": "alerte_stock",
        "title": "Alerte de Stock Faible",
        "message": "Le stock de l'essence de Patchouli (ID: 4) est de 8.5ml, ce qui est inférieur au seuil d'alerte de 10ml.",
        "url": "/api/v1/lab/essences/4/",
        "is_read": false,
        "metadata": { "essence_id": 4, "stock_restant": 8.5 },
        "created_at": "2026-06-01T09:30:00Z"
      }
    ]
    ```

### 7.2 Activer / Suspendre un compte utilisateur (Modération)
*   **URL** : `PATCH /api/v1/auth/admin/users/{id}/toggle-status/`
*   **Permissions** : Admin uniquement
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "detail": "Utilisateur bloqué avec succès.",
      "is_active": false
    }
    ```

### 7.3 Lister tous les utilisateurs inscrits (Admin)
*   **URL** : `GET /api/v1/auth/admin/users/`
*   **Permissions** : Admin uniquement
*   **Query Parameters** :
    *   `search` : string `[OPTIONNEL]` (recherche par email/nom/téléphone)
    *   `page` : integer `[OPTIONNEL]`
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "count": 284,
      "results": [
        {
          "id": 1,
          "email": "user@mail.com",
          "telephone": "237699999999",
          "first_name": "Jean",
          "last_name": "Dupont",
          "role": "client",
          "is_active": true,
          "is_staff": false,
          "date_joined": "2026-05-01T12:00:00Z",
          "is_prestataire": false,
          "prestataire_statut": null
        }
      ]
    }
    ```

---

## 8. PAGES DIRECTES DU BACKEND (HTML COMPLET)

Ces deux endpoints importants **ne renvoient pas de JSON**. Ils génèrent des pages HTML dynamiques complètes stylisées en Vanilla CSS. L'application frontend (Web/Mobile) doit simplement rediriger l'utilisateur vers ces URLs.

### 8.1 Validation Directe de l'Email
*   **URL** : `GET /accounts/confirm-email/{key}/`
*   **Comportement et rendu HTML** :
    *   **Cas 1 : Lien valide** -> Confirme l'adresse e-mail en BDD, active le compte. Retourne une page HTML de succès avec un bouton "Retourner à l'application" (redirigeant vers `settings.FRONTEND_URL`).
    *   **Cas 2 : Lien invalide/expiré** -> Retourne une page HTML d'erreur contenant un formulaire asynchrone (Vanilla JS). L'utilisateur saisit son e-mail et clique sur "Renvoyer". La page effectue une requête AJAX `POST` transparente vers `/api/v1/auth/registration/resend-email/` et affiche le résultat du renvoi sur la page sans recharger.

### 8.2 Formulaire de Réinitialisation de Mot de Passe
*   **URL** : `GET /accounts/password/reset/confirm/{uid}/{token}/` (et `POST`)
*   **Comportement et rendu HTML** :
    *   **GET** : Valide le couple `uid`/`token`. Si invalide, affiche une page d'erreur. Si valide, affiche un formulaire de changement de mot de passe sécurisé à double saisie.
    *   **POST** : Réceptionne la soumission du formulaire, applique les validateurs de Django, met à jour le mot de passe de l'utilisateur, envoie un e-mail d'alerte de sécurité de changement de mot de passe, et affiche une page HTML de succès avec un bouton de redirection vers l'accueil.

---

## 9. MODULE NOTIFICATIONS

### 9.1 Notifications Utilisateur (Admin Only) — `/api/v1/admin/notifications/`

#### 9.1.1 Lister les notifications (Admin seulement)
*   **URL** : `GET /api/v1/admin/notifications/`
*   **Permissions** : **Admin seulement** (`IsAdminUser`)
*   **Description** : Récupère toutes les notifications destinées à l'administrateur connecté (notifications personnelles ou globales admin).
*   **Query Parameters** : Aucun
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    [
      {
        "id": 1,                                    // integer
        "recipient": {                              // object | null
          "id": 1,
          "email": "admin@example.com",
          "first_name": "Admin",
          "last_name": "User"
        },
        "type": "prestataire_request",              // string (type de notification)
        "title": "Nouvelle demande de partenariat", // string
        "message": "Jean Martin souhaite devenir prestataire", // string
        "url": "/admin/prestataires/requests/1/",  // string (URL d'action)
        "is_global_admin": false,                   // boolean (notification globale?)
        "is_read": false,                           // boolean
        "metadata": {},                             // object (données supplémentaires)
        "created_at": "2026-06-07T12:30:00Z"        // string (ISO 8601)
      }
    ]
    ```

---

### 9.2 Notifications de Stock Catalogue — `/api/shop/notifications/`

#### 9.2.1 Lister toutes les notifications de stock
*   **URL** : `GET /api/shop/notifications/`
*   **Permissions** : **Admin seulement** (`IsAdminOrReadOnly`)
*   **Description** : Récupère toutes les alertes de stock du catalogue (Essences, Accessoires, Flacons). Inclut les lues et non-lues.
*   **Query Parameters** :
    | Paramètre | Type | Description |
    |-----------|------|-------------|
    | `type_produit` | string | Filtrer par type : `accessoire` \| `flacon` \| `lot_essence` |
    | `est_lu` | boolean | `true` = lues, `false` = non-lues |
    | `search` | string | Recherche dans `product_name` et `message` |
    | `page` | integer | Numéro de page (défaut: 1, 50 résultats/page) |
    | `ordering` | string | Tri: `-created_at` (défaut), `created_at`, `type_produit` |

*   **Exemples d'URLs** :
    ```
    GET /api/shop/notifications/
    GET /api/shop/notifications/?type_produit=accessoire
    GET /api/shop/notifications/?est_lu=false
    GET /api/shop/notifications/?type_produit=flacon&est_lu=false
    GET /api/shop/notifications/?search=Essence+Fleur
    GET /api/shop/notifications/?page=2
    ```

*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "count": 5,                        // integer (total de notifications)
      "next": "http://.../api/shop/notifications/?page=2",  // string | null
      "previous": null,                  // string | null
      "results": [
        {
          "id": 42,                                      // integer
          "type_produit": "accessoire",                  // string ("accessoire" | "flacon" | "lot_essence")
          "product_id": 7,                               // integer
          "product_name": "Bouteille de Parfum 30ml",   // string (nom du produit)
          "message": "⚠️ Alerte stock: Bouteille de Parfum 30ml a atteint le seuil d'alerte (stock: 1, seuil: 3)", // string
          "stock_actuel": 1,                             // number (quantité ou ml actuel)
          "seuil_alerte": 3,                             // number (seuil configuré)
          "est_lu": false,                               // boolean (lue ou non)
          "est_encore_en_alerte": true,                  // boolean (propriété calculée)
          "metadata": {                                  // object (données supplémentaires)
            "type_accessoire": "Emballage",
            "sku": "ACC-001"
          },
          "created_at": "2026-06-07T12:30:00Z",         // string (ISO 8601)
          "updated_at": "2026-06-07T12:30:00Z"          // string (ISO 8601)
        }
      ]
    }
    ```

#### 9.2.2 Récupérer une notification spécifique
*   **URL** : `GET /api/shop/notifications/{id}/`
*   **Permissions** : Admin seulement
*   **Path Parameters** :
    | Paramètre | Type | Description |
    |-----------|------|-------------|
    | `id` | integer | ID de la notification |

*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "id": 42,
      "type_produit": "accessoire",
      "product_id": 7,
      "product_name": "Bouteille de Parfum 30ml",
      "message": "⚠️ Alerte stock: Bouteille de Parfum 30ml a atteint le seuil d'alerte (stock: 1, seuil: 3)",
      "stock_actuel": 1,
      "seuil_alerte": 3,
      "est_lu": false,
      "est_encore_en_alerte": true,
      "metadata": { "type_accessoire": "Emballage", "sku": "ACC-001" },
      "created_at": "2026-06-07T12:30:00Z",
      "updated_at": "2026-06-07T12:30:00Z"
    }
    ```

#### 9.2.3 Marquer une notification comme lue
*   **URL** : `PATCH /api/shop/notifications/{id}/`
*   **Permissions** : Admin seulement
*   **Path Parameters** :
    | Paramètre | Type | Description |
    |-----------|------|-------------|
    | `id` | integer | ID de la notification |

*   **Payload d'entrée** :
    ```json
    {
      "est_lu": true  // [REQUIS] boolean
    }
    ```

*   **Réponse - 200 OK** :
    ```json
    {
      "est_lu": true
    }
    ```

#### 9.2.4 Lister seulement les notifications non-lues
*   **URL** : `GET /api/shop/notifications/non_lues/`
*   **Permissions** : Admin seulement
*   **Description** : Récupère **uniquement** les notifications avec `est_lu=false`.
*   **Query Parameters** :
    | Paramètre | Type | Description |
    |-----------|------|-------------|
    | `type_produit` | string | Filtrer par type (optionnel) |
    | `search` | string | Recherche (optionnel) |
    | `page` | integer | Numéro de page |

*   **Exemples d'URLs** :
    ```
    GET /api/shop/notifications/non_lues/
    GET /api/shop/notifications/non_lues/?type_produit=flacon
    GET /api/shop/notifications/non_lues/?page=1
    ```

*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "count": 3,
      "next": null,
      "previous": null,
      "results": [
        {
          "id": 42,
          "type_produit": "accessoire",
          "product_id": 7,
          "product_name": "Bouteille de Parfum 30ml",
          "message": "⚠️ Alerte stock: ...",
          "stock_actuel": 1,
          "seuil_alerte": 3,
          "est_lu": false,
          "est_encore_en_alerte": true,
          "metadata": { "type_accessoire": "Emballage", "sku": "ACC-001" },
          "created_at": "2026-06-07T12:30:00Z",
          "updated_at": "2026-06-07T12:30:00Z"
        }
      ]
    }
    ```

#### 9.2.5 Marquer toutes les notifications comme lues
*   **URL** : `PATCH /api/shop/notifications/marquer_tous_comme_lus/`
*   **Permissions** : Admin seulement
*   **Description** : Marque **toutes** les notifications non-lues (`est_lu=false`) comme lues.
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "updated": 5,                           // integer (nombre mis à jour)
      "message": "5 notifications marquées comme lues"  // string
    }
    ```

#### 9.2.6 Récupérer les statistiques des notifications
*   **URL** : `GET /api/shop/notifications/stats/`
*   **Permissions** : Admin seulement
*   **Description** : Récupère les statistiques d'alertes par type de produit et statut de lecture.
*   **Payload d'entrée** : Aucun
*   **Réponse - 200 OK** :
    ```json
    {
      "total": 15,           // integer (nombre total de notifications)
      "non_lues": 5,         // integer (nombre de notifications non-lues)
      "lues": 10,            // integer (nombre de notifications lues)
      "par_type_produit": [  // array (comptage par type)
        {
          "type_produit": "accessoire",  // string
          "count": 7                      // integer
        },
        {
          "type_produit": "flacon",
          "count": 5
        },
        {
          "type_produit": "lot_essence",
          "count": 3
        }
      ]
    }
    ```

---

### 9.3 Triggers Automatiques (Backend)

#### Création Automatique de NotificationCatalogue

Les notifications de stock sont créées **automatiquement** via Django Signals quand un produit baisse de stock et atteint son seuil d'alerte. Aucune action frontend n'est nécessaire.

**Conditions de création** :

| Produit | Champ Stock | Champ Seuil | Alerte si |
|---------|------------|-----------|----------|
| **Accessoire** | `stock_quantite` | `seuil_alerte_stock` (défaut: 3) | `stock_quantite <= seuil_alerte_stock` |
| **Flacon** | `stock_quantite` | `seuil_alerte_stock` (défaut: 5) | `stock_quantite <= seuil_alerte_stock` |
| **LotEssence** | `stock_ml` | `seuil_alerte_ml` | `stock_ml <= seuil_alerte_ml` (si configuré) |

**Exemple** :
```python
# Admin change le stock d'un Accessoire via l'admin Django
accessoire = Accessoire.objects.get(id=7)
accessoire.stock_quantite = 1  # < seuil de 3
accessoire.save()

# Un signal Django se déclenche automatiquement
# → NotificationCatalogue créée avec message "⚠️ Alerte stock: ..."
```

---

## 10. INTÉGRATION FRONTEND NEXT.JS

### 10.1 Hook React pour les Notifications

```javascript
// hooks/useNotifications.js
import { useState, useEffect } from 'react';

export function useNotifications(pollInterval = 30000) {
  const [notifications, setNotifications] = useState([]);
  const [stats, setStats] = useState({
    total: 0,
    non_lues: 0,
    lues: 0,
    par_type_produit: []
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchNotifications() {
      try {
        setLoading(true);
        
        // Récupérer les notifications non-lues
        const res = await fetch('/api/shop/notifications/?est_lu=false');
        if (!res.ok) throw new Error('Failed to fetch notifications');
        const data = await res.json();
        setNotifications(data.results || []);

        // Récupérer les statistiques
        const statsRes = await fetch('/api/shop/notifications/stats/');
        if (!statsRes.ok) throw new Error('Failed to fetch stats');
        const statsData = await statsRes.json();
        setStats(statsData);
        
        setError(null);
      } catch (err) {
        console.error('Erreur notifications:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    fetchNotifications();
    const timer = setInterval(fetchNotifications, pollInterval);
    return () => clearInterval(timer);
  }, [pollInterval]);

  const getNotificationsByType = (type) => 
    notifications.filter(n => n.type_produit === type);

  const getCountByType = (type) => {
    const item = stats.par_type_produit?.find(t => t.type_produit === type);
    return item?.count || 0;
  };

  const markAsRead = async (notificationId) => {
    try {
      const res = await fetch(`/api/shop/notifications/${notificationId}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ est_lu: true })
      });
      if (!res.ok) throw new Error('Failed to mark as read');
      
      // Refetch notifications
      const listRes = await fetch('/api/shop/notifications/?est_lu=false');
      const data = await listRes.json();
      setNotifications(data.results || []);
    } catch (err) {
      console.error('Erreur:', err);
    }
  };

  const markAllAsRead = async () => {
    try {
      const res = await fetch('/api/shop/notifications/marquer_tous_comme_lus/', {
        method: 'PATCH'
      });
      if (!res.ok) throw new Error('Failed');
      
      // Reset state
      setNotifications([]);
      setStats(prev => ({ ...prev, non_lues: 0 }));
    } catch (err) {
      console.error('Erreur:', err);
    }
  };

  return {
    notifications,
    stats,
    loading,
    error,
    getNotificationsByType,
    getCountByType,
    markAsRead,
    markAllAsRead
  };
}
```

### 10.2 Exemples de Requêtes cURL

**Lister toutes les notifications** :
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/shop/notifications/"
```

**Filtrer par type non-lues** :
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/shop/notifications/?type_produit=accessoire&est_lu=false"
```

**Récupérer les statistiques** :
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/shop/notifications/stats/"
```

**Marquer une notification comme lue** :
```bash
curl -X PATCH \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"est_lu": true}' \
  "http://localhost:8000/api/shop/notifications/42/"
```

**Marquer toutes les non-lues comme lues** :
```bash
curl -X PATCH \
  -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/shop/notifications/marquer_tous_comme_lus/"
```

---

### 10.3 Codes de Statut HTTP

| Code | Statut | Cas d'usage |
|------|--------|-----------|
| **200** | OK | Requête réussie |
| **400** | Bad Request | Paramètre invalide ou payload malformé |
| **401** | Unauthorized | Token JWT expiré ou absent |
| **403** | Forbidden | Utilisateur non-admin tentant d'accéder |
| **404** | Not Found | Notification inexistante |
| **500** | Server Error | Erreur interne du serveur |

---

### 10.4 Sécurité & Authentification

**Toutes les endpoints de notifications** (utilisateur ET catalogue) nécessitent :
1. ✅ Token JWT valide dans l'en-tête `Authorization: Bearer {token}`
2. ✅ Rôle administrateur (`is_staff=True` ou `is_superuser=True`)
3. ❌ Les clients/prestataires/livreurs NE peuvent PAS accéder

**Exemple d'erreur 403 (accès refusé)** :
```json
{
  "detail": "Vous n'avez pas la permission d'effectuer cette action."
}
```
