#!/usr/bin/env bash
# ============================================================
# fix_dns_ia.sh — Diagnostic et correction DNS pour l'IA
# Accessoires Exclusifs — À exécuter en ROOT sur le VPS
#
#   chmod +x deploy/fix_dns_ia.sh && sudo bash deploy/fix_dns_ia.sh
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
erreur()  { echo -e "${RED}[ERREUR]${NC} $*"; }

APP_DIR="/var/www/accessoiresexclusifs"

echo ""
echo "════════════════════════════════════════════════"
echo "  Diagnostic DNS & Réseau — IA HuggingFace"
echo "════════════════════════════════════════════════"
echo ""

# ─── 1. Vérification du /etc/resolv.conf ──────────────────────────────────────
info "1/6 Contenu de /etc/resolv.conf :"
cat /etc/resolv.conf
echo ""

# ─── 2. Test DNS de base ───────────────────────────────────────────────────────
info "2/6 Test DNS — résolution de plusieurs domaines..."

test_dns() {
    local domaine="$1"
    if getent hosts "$domaine" > /dev/null 2>&1; then
        local ip
        ip=$(getent hosts "$domaine" | awk '{print $1}')
        ok "$domaine → $ip"
        return 0
    else
        erreur "$domaine → ÉCHEC (DNS ou blocage réseau)"
        return 1
    fi
}

hf_ok=0
google_ok=0

test_dns "google.com"         && google_ok=1 || true
test_dns "api.groq.com"       || true
test_dns "router.huggingface.co"      && hf_ok=1 || true
test_dns "api-inference.huggingface.co" && hf_ok=1 || true
test_dns "generativelanguage.googleapis.com" || true

echo ""

# ─── 3. Test HTTPS (accès réel) ───────────────────────────────────────────────
info "3/6 Test HTTPS — connexion réelle aux APIs IA..."

test_https() {
    local url="$1"
    local nom="$2"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
    if [ "$code" = "000" ]; then
        erreur "$nom → IMPOSSIBLE (timeout ou DNS fail)"
    elif [ "$code" = "401" ] || [ "$code" = "403" ] || [ "$code" = "200" ] || [ "$code" = "422" ]; then
        ok "$nom → HTTP $code (serveur joignable ✓)"
    else
        warn "$nom → HTTP $code"
    fi
}

test_https "https://router.huggingface.co" "HuggingFace Router"
test_https "https://api-inference.huggingface.co" "HuggingFace Inference"
test_https "https://api.groq.com" "Groq API"
test_https "https://generativelanguage.googleapis.com" "Google Gemini"

echo ""

# ─── 4. Diagnostic et correction du DNS ───────────────────────────────────────
info "4/6 Vérification et correction de la configuration DNS..."

if [ "$google_ok" = "1" ] && [ "$hf_ok" = "0" ]; then
    echo ""
    warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    warn "  HuggingFace est BLOQUÉ par votre hébergeur (Hostinger)"
    warn "  mais Google (Gemini) fonctionne."
    warn "  → Le DNS global est OK mais HuggingFace est blacklisté."
    warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    warn "Solution : Changez LLM_PROVIDER=gemini dans votre .env"
    warn "           (Gemini fonctionne parfaitement sur ce serveur)"
    echo ""

    # Proposer le changement automatique
    if [ -f "$APP_DIR/.env" ]; then
        echo -n "Voulez-vous changer automatiquement LLM_PROVIDER=gemini dans .env ? [o/N] "
        read -r reponse
        if [ "$reponse" = "o" ] || [ "$reponse" = "O" ]; then
            # Sauvegarde
            cp "$APP_DIR/.env" "$APP_DIR/.env.bak.$(date +%Y%m%d%H%M%S)"
            # Remplacement
            if grep -q "^LLM_PROVIDER=" "$APP_DIR/.env"; then
                sed -i 's/^LLM_PROVIDER=.*/LLM_PROVIDER=gemini/' "$APP_DIR/.env"
            else
                echo "LLM_PROVIDER=gemini" >> "$APP_DIR/.env"
            fi
            ok "LLM_PROVIDER=gemini défini dans .env"
            systemctl restart gunicorn
            ok "Gunicorn redémarré avec le nouveau provider (Gemini)"
        fi
    fi

elif [ "$google_ok" = "0" ] && [ "$hf_ok" = "0" ]; then
    warn "DNS global cassé — on tente de réparer /etc/resolv.conf..."

    # Backup
    cp /etc/resolv.conf /etc/resolv.conf.bak.$(date +%Y%m%d%H%M%S)

    # Vérifier si systemd-resolved est actif
    if systemctl is-active --quiet systemd-resolved; then
        info "systemd-resolved actif — correction via resolved.conf..."
        cat > /etc/systemd/resolved.conf <<'RESOLVED'
[Resolve]
DNS=8.8.8.8 1.1.1.1 8.8.4.4
FallbackDNS=9.9.9.9
DNSStubListener=yes
RESOLVED
        systemctl restart systemd-resolved
        # Recréer le lien symbolique correct
        ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
        ok "systemd-resolved corrigé avec DNS Google (8.8.8.8) et Cloudflare (1.1.1.1)"
    else
        info "Écriture directe de /etc/resolv.conf..."
        cat > /etc/resolv.conf <<'RESOLV'
nameserver 8.8.8.8
nameserver 1.1.1.1
nameserver 8.8.4.4
options timeout:2 attempts:3
RESOLV
        ok "/etc/resolv.conf mis à jour avec DNS 8.8.8.8 et 1.1.1.1"
    fi

    # Re-test
    info "Re-test DNS après correction..."
    sleep 2
    if getent hosts "api-inference.huggingface.co" > /dev/null 2>&1; then
        ok "HuggingFace est maintenant joignable ! ✓"
        systemctl restart gunicorn
        ok "Gunicorn redémarré"
    else
        erreur "HuggingFace toujours inaccessible même avec les DNS Google/Cloudflare."
        erreur "→ Ce domaine est probablement bloqué par Hostinger."
        erreur "→ Changez LLM_PROVIDER=gemini dans votre .env (solution recommandée)"
    fi
else
    ok "DNS opérationnel pour tous les domaines."
fi

echo ""

# ─── 5. Affichage du LLM_PROVIDER actuel ──────────────────────────────────────
info "5/6 Configuration IA actuelle dans .env :"
if [ -f "$APP_DIR/.env" ]; then
    grep -E "^(LLM_PROVIDER|GEMINI_API_KEY|HUGGINGFACE|GROQ)" "$APP_DIR/.env" | \
        sed 's/=.*/=***/' | \
        while read -r line; do echo "   $line"; done
else
    warn "Fichier .env introuvable à $APP_DIR/.env"
fi

echo ""

# ─── 6. Résumé et recommandations ─────────────────────────────────────────────
info "6/6 Résumé :"
echo ""
echo "  Pour changer de provider manuellement :"
echo "    sudo nano $APP_DIR/.env"
echo "    → Modifier : LLM_PROVIDER=gemini   (recommandé si HF bloqué)"
echo "    → Modifier : LLM_PROVIDER=groq     (alternative gratuite)"
echo "    → Modifier : LLM_PROVIDER=huggingface  (si HF accessible)"
echo ""
echo "  Après modification du .env :"
echo "    sudo systemctl restart gunicorn"
echo ""
echo "════════════════════════════════════════════════"
echo "  Diagnostic terminé."
echo "════════════════════════════════════════════════"
