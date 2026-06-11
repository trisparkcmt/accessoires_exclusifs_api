#!/usr/bin/env python3
"""
Setup script - Crée les utilisateurs de test dans la base de données Django
Usage: python setup_test_users.py
"""

import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from utilisateur.models import User, Client, Prestataire, Livreur, Serveuse

TEST_USERS = [
    {
        "email": "admin@test.com",
        "password": "AdminPassword123!",
        "first_name": "Admin",
        "last_name": "Test",
        "telephone": "+237600000001",
        "is_superuser": True,
        "is_staff": True,
        "role": "superadmin"
    },
    {
        "email": "serveuse@test.com",
        "password": "ServeusePassword123!",
        "first_name": "Sarah",
        "last_name": "Serveuse",
        "telephone": "+237600000002",
        "is_superuser": False,
        "is_staff": False,
        "role": "serveuse"
    },
    {
        "email": "prestataire@test.com",
        "password": "PrestatairePassword123!",
        "first_name": "Pierre",
        "last_name": "Prestataire",
        "telephone": "+237600000003",
        "is_superuser": False,
        "is_staff": False,
        "role": "prestataire"
    },
    {
        "email": "livreur@test.com",
        "password": "LivreurPassword123!",
        "first_name": "Laurent",
        "last_name": "Livreur",
        "telephone": "+237600000004",
        "is_superuser": False,
        "is_staff": False,
        "role": "livreur"
    },
    {
        "email": "client@test.com",
        "password": "ClientPassword123!",
        "first_name": "Claire",
        "last_name": "Client",
        "telephone": "+237600000005",
        "is_superuser": False,
        "is_staff": False,
        "role": "client"
    }
]

def create_test_users():
    """Créer les utilisateurs de test"""

    print("🔧 Création des utilisateurs de test...\n")

    for user_data in TEST_USERS:
        email = user_data['email']
        role = user_data.pop('role')

        # Vérifier si l'utilisateur existe déjà
        if User.objects.filter(email=email).exists():
            print(f"✓ {email} existe déjà")
            continue

        # Créer l'utilisateur
        if role == "superadmin":
            user = User.objects.create_superuser(**user_data)
        else:
            user = User.objects.create_user(**user_data)

        print(f"✓ Créé: {email} ({role})")

        # Créer le profil spécifique
        if role == "serveuse":
            Serveuse.objects.create(client=user.client, actif=True)
            print(f"  └─ Serveuse créée (actif=True)")
        elif role == "prestataire":
            Prestataire.objects.create(
                client=user.client,
                statut='actif',
                code_promo=f"ACC-{email.split('@')[0].upper()}"
            )
            print(f"  └─ Prestataire créé (statut=actif)")
        elif role == "livreur":
            Livreur.objects.create(
                client=user.client,
                statut='disponible'
            )
            print(f"  └─ Livreur créé (statut=disponible)")
        # Client n'a besoin que du Client model (créé automatiquement)

    print("\n✅ Utilisateurs de test créés avec succès!")
    print("\nIdentifiants de test:")
    print("-" * 50)
    for user_data in TEST_USERS:
        print(f"Email: {user_data['email']}")
        print(f"Password: {user_data['password']}")
        print()

def list_test_users():
    """Lister les utilisateurs de test"""

    print("📋 Utilisateurs de test actuels:\n")

    for user_data in TEST_USERS:
        email = user_data['email']
        user = User.objects.filter(email=email).first()

        if user:
            status = "✓ Existe"
            role_info = ""

            if user.is_superuser:
                role_info = " (Superadmin)"
            elif hasattr(user.client, 'serveuse') and user.client.serveuse.actif:
                role_info = f" (Serveuse, actif={user.client.serveuse.actif})"
            elif hasattr(user.client, 'prestataire'):
                role_info = f" (Prestataire, statut={user.client.prestataire.statut})"
            elif hasattr(user.client, 'livreur'):
                role_info = f" (Livreur, statut={user.client.livreur.statut})"
            else:
                role_info = " (Client)"

            print(f"{status}: {email}{role_info}")
        else:
            print(f"✗ Manquant: {email}")

    print()

def delete_test_users():
    """Supprimer les utilisateurs de test"""

    print("🗑️  Suppression des utilisateurs de test...\n")

    for user_data in TEST_USERS:
        email = user_data['email']
        user = User.objects.filter(email=email).first()

        if user:
            user.delete()
            print(f"✓ Supprimé: {email}")
        else:
            print(f"- {email} n'existe pas")

    print("\n✅ Utilisateurs de test supprimés!")

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "delete":
            delete_test_users()
        elif command == "list":
            list_test_users()
        else:
            print(f"Commande inconnue: {command}")
            print("Utilisations: setup_test_users.py [create|list|delete]")
    else:
        list_test_users()
        create_test_users()
