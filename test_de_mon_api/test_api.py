#!/usr/bin/env python3
"""
API Test Runner - Test dynamique de tous les endpoints
Usage: python test_api.py [--role superadmin|serveuse|prestataire|livreur|client] [--endpoint path]
"""

import requests
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime

# Couleurs pour le terminal
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class APITester:
    def __init__(self, config_file: str = "endpoints.json"):
        self.config_path = Path(__file__).parent / config_file
        with open(self.config_path) as f:
            self.config = json.load(f)

        self.api_base = self.config["api_base"]
        self.tokens = {}  # Stocke les tokens par rôle
        self.results = []

    def login(self, role: str) -> bool:
        """Authentifier un utilisateur pour un rôle donné"""
        if role not in self.config["roles"]:
            print(f"{Colors.FAIL}✗ Rôle '{role}' non trouvé{Colors.ENDC}")
            return False

        role_data = self.config["roles"][role]
        url = f"{self.api_base}/auth/mobile/login/"

        try:
            resp = requests.post(url, json={
                "email": role_data["email"],
                "password": role_data["password"]
            }, timeout=5)

            if resp.status_code == 200:
                self.tokens[role] = resp.json().get("access")
                print(f"{Colors.OKGREEN}✓ Connecté en tant que {role}{Colors.ENDC}")
                return True
            else:
                print(f"{Colors.FAIL}✗ Erreur login {role}: {resp.status_code}{Colors.ENDC}")
                return False
        except Exception as e:
            print(f"{Colors.FAIL}✗ Exception login: {e}{Colors.ENDC}")
            return False

    def test_endpoint(self, role: str, method: str, path: str, body: Dict = None, params: Dict = None) -> Tuple[int, Dict]:
        """Tester un endpoint spécifique"""
        if role not in self.tokens:
            status, _ = None, None
            if not self.login(role):
                return None, {"error": "Impossible de se connecter"}

        token = self.tokens.get(role)
        url = f"{self.api_base}{path}"

        # Remplacer les paramètres dans l'URL
        if params:
            for key, value in params.items():
                url = url.replace(f"{{{key}}}", str(value))

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                resp = requests.post(url, json=body or {}, headers=headers, timeout=10)
            elif method == "PUT":
                resp = requests.put(url, json=body or {}, headers=headers, timeout=10)
            elif method == "PATCH":
                resp = requests.patch(url, json=body or {}, headers=headers, timeout=10)
            elif method == "DELETE":
                resp = requests.delete(url, headers=headers, timeout=10)
            else:
                return None, {"error": f"Méthode {method} non supportée"}

            return resp.status_code, resp.json() if resp.text else {}
        except Exception as e:
            return None, {"error": str(e)}

    def print_result(self, role: str, method: str, path: str, status: int, response: Dict):
        """Afficher le résultat d'un test"""
        status_color = Colors.OKGREEN if 200 <= status < 300 else Colors.WARNING if 400 <= status < 500 else Colors.FAIL

        print(f"\n{Colors.BOLD}{role.upper()}{Colors.ENDC}")
        print(f"  {method:6} {path}")
        print(f"  Status: {status_color}{status}{Colors.ENDC}")

        if isinstance(response, dict) and response:
            # Afficher les premières lignes de la réponse
            resp_str = json.dumps(response, indent=2, ensure_ascii=False)
            lines = resp_str.split('\n')[:5]
            for line in lines:
                print(f"  {line}")
            if len(resp_str.split('\n')) > 5:
                print(f"  ... ({len(resp_str.split(chr(10)))} lignes totales)")

    def run_role_tests(self, role: str):
        """Exécuter tous les tests pour un rôle"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}=== Tests pour {role.upper()} ==={Colors.ENDC}\n")

        if not self.login(role):
            return

        for category, category_data in self.config.get("endpoints", {}).items():
            endpoints = category_data.get("endpoints", [])
            print(f"\n{Colors.OKCYAN}{category_data['name']}{Colors.ENDC}")

            for ep in endpoints:
                # Vérifier si ce rôle peut accéder
                if role not in ep.get("roles", []) and "all" not in ep.get("roles", []):
                    print(f"  ✗ {ep['method']:6} {ep['path']:40} (Accès refusé pour {role})")
                    continue

                status, response = self.test_endpoint(
                    role,
                    ep["method"],
                    ep["path"],
                    ep.get("body"),
                    ep.get("params")
                )

                if status is None:
                    print(f"  {Colors.FAIL}✗{Colors.ENDC} {ep['method']:6} {ep['path']:40} - Erreur")
                else:
                    icon = "✓" if 200 <= status < 300 else "!"
                    status_color = Colors.OKGREEN if 200 <= status < 300 else Colors.WARNING if 400 <= status < 500 else Colors.FAIL
                    print(f"  {status_color}{icon}{Colors.ENDC} {ep['method']:6} {ep['path']:40} [{status}]")

                self.results.append({
                    "role": role,
                    "method": ep["method"],
                    "path": ep["path"],
                    "status": status,
                    "timestamp": datetime.now().isoformat()
                })

    def run_all_tests(self):
        """Exécuter les tests pour tous les rôles"""
        roles = list(self.config["roles"].keys())

        for role in roles:
            self.run_role_tests(role)

        self.print_summary()

    def print_summary(self):
        """Afficher un résumé des tests"""
        print(f"\n\n{Colors.HEADER}{Colors.BOLD}=== RÉSUMÉ DES TESTS ==={Colors.ENDC}\n")

        success = sum(1 for r in self.results if 200 <= (r["status"] or 0) < 300)
        total = len(self.results)

        print(f"Total: {total} tests")
        print(f"{Colors.OKGREEN}✓ Réussis: {success}{Colors.ENDC}")
        print(f"{Colors.FAIL}✗ Échoués: {total - success}{Colors.ENDC}")
        print(f"Taux de réussite: {100 * success / total:.1f}%")

        # Résultats par rôle
        print(f"\n{Colors.BOLD}Par rôle:{Colors.ENDC}")
        for role in self.config["roles"]:
            role_results = [r for r in self.results if r["role"] == role]
            if role_results:
                success = sum(1 for r in role_results if 200 <= (r["status"] or 0) < 300)
                print(f"  {role:15} {success:3}/{len(role_results):3}")

        # Sauvegarder les résultats
        with open(Path(__file__).parent / "test_results.json", "w") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)

        print(f"\n{Colors.OKBLUE}Résultats sauvegardés dans test_results.json{Colors.ENDC}")

def main():
    if len(sys.argv) < 2:
        print(f"{Colors.HEADER}API Test Runner{Colors.ENDC}")
        print(f"\nUsage:")
        print(f"  python test_api.py                    # Tous les tests")
        print(f"  python test_api.py --role superadmin  # Tests pour un rôle")
        print(f"  python test_api.py --all              # Tests complets\n")
        sys.exit(1)

    tester = APITester()

    if "--role" in sys.argv:
        idx = sys.argv.index("--role")
        if idx + 1 < len(sys.argv):
            role = sys.argv[idx + 1]
            tester.run_role_tests(role)
    else:
        tester.run_all_tests()

if __name__ == "__main__":
    main()
