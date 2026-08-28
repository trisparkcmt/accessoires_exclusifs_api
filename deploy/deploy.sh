#!/usr/bin/env bash
# ============================================================
# deploy.sh — Script de déploiement initial sur VPS Hostinger
# Accessoires Exclusifs — Production
#
# À exécuter UNE SEULE FOIS en root sur le VPS :
#   chmod +x deploy/deploy.sh && sudo ./deploy/deploy.sh
# ============================================================

set -euo pipefail

# ─── Variables ────────────────────────────────────────────────────────────────
DOMAIN="api.accessoiresexclusifs.com"
APP_DIR="/var/www/accessoiresexclusifs"
REPO_URL="https://github.com/trisparkcmt/accessoires_exclusifs_api.git"
BRANCH="master"
PYTHON="python3"
APP_USER="www-data"

echo "════════════════════════════════════════════════"
echo " Déploiement Accessoires Exclusifs API — Production"
echo "════════════════════════════════════════════════"

# ─── 1. Mise à jour système & dépendances ─────────────────────────────────────
echo "[1/9] Mise à jour des paquets système..."
apt-get update -qq
apt-get install -y -qq \
    git python3 python3-pip python3-venv python3-dev \
    postgresql postgresql-contrib \
    nginx certbot python3-certbot-nginx \
    build-essential libpq-dev curl

# ─── 2. Cloner / mettre à jour le projet ──────────────────────────────────────
echo "[2/9] Récupération du code source depuis GitHub..."
mkdir -p "$APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git reset --hard "origin/$BRANCH"
else
    git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# ─── 3. Environnement virtuel Python ──────────────────────────────────────────
echo "[3/9] Création de l'environnement virtuel..."
if [ ! -d "$APP_DIR/venv" ]; then
    $PYTHON -m venv "$APP_DIR/venv"
fi
source "$APP_DIR/venv/bin/activate"

pip install --upgrade pip -q
pip install -r "$APP_DIR/requirements.txt" -q
echo "   → Dépendances Python installées."

# ─── 4. Copie du fichier .env ─────────────────────────────────────────────────
echo "[4/9] Configuration de l'environnement..."
if [ ! -f "$APP_DIR/.env" ]; then
    echo "⚠️  Fichier .env introuvable dans $APP_DIR/.env !"
    echo "   Copiez votre .env avec la commande :"
    echo "   scp .env root@IP_VPS:$APP_DIR/.env"
    exit 1
fi
chmod 600 "$APP_DIR/.env"

# ─── 5. Django — collectstatic & migrations ───────────────────────────────────
echo "[5/9] Préparation de Django..."
cd "$APP_DIR"
$APP_DIR/venv/bin/python manage.py collectstatic --noinput -v 0
$APP_DIR/venv/bin/python manage.py migrate --noinput
echo "   → Static files collectés, migrations appliquées."

# ─── 6. Permissions ───────────────────────────────────────────────────────────
echo "[6/9] Configuration des permissions..."
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
chmod -R 755 "$APP_DIR"
mkdir -p /var/log/gunicorn
chown "$APP_USER":"$APP_USER" /var/log/gunicorn

# ─── 7. Gunicorn (Systemd) ────────────────────────────────────────────────────
echo "[7/9] Installation du service Gunicorn..."
cp "$APP_DIR/deploy/gunicorn.service" /etc/systemd/system/gunicorn.service
systemctl daemon-reload
systemctl enable gunicorn
systemctl restart gunicorn
echo "   → Service Gunicorn actif."

# ─── 8. Nginx ─────────────────────────────────────────────────────────────────
echo "[8/9] Configuration de Nginx..."
cp "$APP_DIR/deploy/nginx.conf" "/etc/nginx/sites-available/$DOMAIN"
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl reload nginx
echo "   → Nginx configuré et rechargé."

# ─── 9. SSL / HTTPS avec Let's Encrypt ───────────────────────────────────────
echo "[9/9] Installation du certificat SSL (Let's Encrypt)..."
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    certbot --nginx \
        -d "$DOMAIN" \
        --non-interactive \
        --agree-tos \
        -m "accessoiresexclusifs@gmail.com" \
        --redirect
    echo "   → Certificat SSL installé et HTTPS activé."
else
    echo "   → Certificat SSL déjà en place."
fi

echo ""
echo "════════════════════════════════════════════════"
echo " ✅ Déploiement terminé avec succès !"
echo " 🌐 API disponible sur : https://$DOMAIN"
echo "════════════════════════════════════════════════"
echo ""
echo " Commandes utiles sur le VPS :"
echo "   sudo systemctl status gunicorn       # état du serveur"
echo "   sudo systemctl restart gunicorn      # redémarrer"
echo "   sudo journalctl -u gunicorn -f       # logs temps réel"
echo "   sudo tail -f /var/log/nginx/accessoiresexclusifs_error.log"
