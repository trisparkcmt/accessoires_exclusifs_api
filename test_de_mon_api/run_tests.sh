#!/bin/bash
# Script de test simplifié pour l'API

set -e

cd "$(dirname "$0")"

# Couleurs
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧪 Test Suite API - Accessoire Exclusif${NC}\n"

# Vérifier si Python est disponible
if ! command -v python &> /dev/null; then
    echo -e "${RED}✗ Python n'est pas installé${NC}"
    exit 1
fi

# Vérifier si requests est disponible
python -c "import requests" 2>/dev/null || {
    echo -e "${YELLOW}⚠ Installation de requests...${NC}"
    pip install requests
}

echo -e "${GREEN}✓ Dépendances OK${NC}\n"

# Menu
echo "Choisir le type de test:"
echo "1) Tous les rôles (test complet)"
echo "2) Superadmin seulement"
echo "3) Serveuse seulement"
echo "4) Prestataire seulement"
echo "5) Livreur seulement"
echo "6) Client seulement"
echo "7) Voir les résultats précédents"
echo ""
read -p "Votre choix (1-7): " choice

case $choice in
    1)
        echo -e "\n${BLUE}🚀 Lancement des tests complets...${NC}\n"
        python test_api.py
        ;;
    2)
        echo -e "\n${BLUE}🚀 Tests Superadmin...${NC}\n"
        python test_api.py --role superadmin
        ;;
    3)
        echo -e "\n${BLUE}🚀 Tests Serveuse...${NC}\n"
        python test_api.py --role serveuse
        ;;
    4)
        echo -e "\n${BLUE}🚀 Tests Prestataire...${NC}\n"
        python test_api.py --role prestataire
        ;;
    5)
        echo -e "\n${BLUE}🚀 Tests Livreur...${NC}\n"
        python test_api.py --role livreur
        ;;
    6)
        echo -e "\n${BLUE}🚀 Tests Client...${NC}\n"
        python test_api.py --role client
        ;;
    7)
        if [ -f test_results.json ]; then
            echo -e "\n${BLUE}📊 Résultats précédents:${NC}\n"
            cat test_results.json | python -m json.tool | head -50
            echo ""
            echo "..."
            echo ""
            lines=$(cat test_results.json | python -m json.tool | wc -l)
            echo -e "Total: ${lines} lignes (voir test_results.json complet)"
        else
            echo -e "${RED}✗ Aucun résultat trouvé. Lancez d'abord des tests.${NC}"
        fi
        ;;
    *)
        echo -e "${RED}✗ Choix invalide${NC}"
        exit 1
        ;;
esac

echo -e "\n${GREEN}✓ Terminé${NC}"
