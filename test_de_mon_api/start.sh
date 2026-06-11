#!/bin/bash
# Script de démarrage complet - Lance le serveur Django + Setup test users + Interface Web

set -e

cd "$(dirname "$0")/.."

# Couleurs
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════╗"
echo "║  🚀 Accessoire Exclusif - Test Suite Launcher   ║"
echo "╚════════════════════════════════════════════════════╝"
echo -e "${NC}\n"

# Vérifier si Django est déjà en cours d'exécution
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}⚠ Le port 8000 est déjà utilisé (Django probablement en cours)${NC}\n"
    read -p "Continuer quand même? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

echo -e "${BLUE}📦 Étape 1: Migrations${NC}"
python manage.py migrate --noinput
echo -e "${GREEN}✓ Migrations OK${NC}\n"

echo -e "${BLUE}👤 Étape 2: Création des utilisateurs de test${NC}"
cd test_de_mon_api
python setup_test_users.py
cd ..
echo -e "${GREEN}✓ Utilisateurs OK${NC}\n"

echo -e "${BLUE}🌐 Étape 3: Démarrage du serveur Django${NC}"
echo -e "${YELLOW}Serveur disponible à: http://127.0.0.1:8000${NC}"
echo -e "${YELLOW}Interface de test: file://${PWD}/test_de_mon_api/index.html${NC}\n"

# Afficher les utilisateurs de test
echo -e "${BLUE}📋 Utilisateurs de test créés:${NC}"
echo "  Email: admin@test.com | Password: AdminPassword123!"
echo "  Email: serveuse@test.com | Password: ServeusePassword123!"
echo "  Email: prestataire@test.com | Password: PrestatairePassword123!"
echo "  Email: livreur@test.com | Password: LivreurPassword123!"
echo "  Email: client@test.com | Password: ClientPassword123!"
echo ""
echo -e "${BLUE}🧪 Pour lancer les tests (dans un autre terminal):${NC}"
echo "  cd test_de_mon_api"
echo "  bash run_tests.sh"
echo ""

# Lancer le serveur
python manage.py runserver
