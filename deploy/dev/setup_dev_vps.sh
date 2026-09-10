#!/bin/bash
# ============================================================
# setup_dev_vps.sh — Installation INITIALE du serveur dev
# À exécuter UNE SEULE FOIS sur le VPS en tant que root/sudo
# ============================================================
set -e

REPO="git@github.com:trisparkcmt/accessoires_exclusifs_api.git"
APP_DIR="/var/www/accessoiresexclusifs_dev"
SERVICE_FILE="$APP_DIR/deploy/dev/gunicorn_dev.service"
NGINX_CONF="$APP_DIR/deploy/dev/nginx-dev-api.conf"
DOMAIN="dev-api.accessoiresexclusifs.com"

echo "═══════════════════════════════════════════"
echo " Setup API Dev — $DOMAIN"
echo "═══════════════════════════════════════════"

# 1. Cloner la branche main
echo "📦 [1/8] Clonage de la branche main..."
git clone -b main "$REPO" "$APP_DIR"
cd "$APP_DIR"

# 2. Virtualenv + dépendances
echo "🐍 [2/8] Création du virtualenv..."
python3 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Vérifier que le .env existe
echo "⚙️  [3/8] Vérification du fichier .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    echo "❌ ERREUR : Le fichier $APP_DIR/.env est manquant."
    echo "   Copie deploy/dev/.env.dev.example vers .env et remplis les valeurs."
    exit 1
fi

# 4. Migrations + collectstatic
echo "🗄️  [4/8] Migrations..."
python manage.py migrate --noinput

echo "📁 [5/8] Collectstatic..."
python manage.py collectstatic --noinput

# 6. Logs gunicorn
echo "📝 [6/8] Création du répertoire de logs..."
mkdir -p /var/log/gunicorn

# 7. Service systemd
echo "🔧 [7/8] Installation du service systemd..."
cp "$SERVICE_FILE" /etc/systemd/system/gunicorn_dev.service
systemctl daemon-reload
systemctl enable gunicorn_dev
systemctl start gunicorn_dev

# 8. Nginx
echo "🌐 [8/8] Configuration Nginx..."
cp "$NGINX_CONF" "/etc/nginx/sites-available/$DOMAIN"
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/"
nginx -t
systemctl reload nginx

echo ""
echo "✅ Installation terminée !"
echo ""
echo "👉 Prochaine étape — Obtenir le certificat SSL :"
echo "   certbot --nginx -d $DOMAIN"
echo ""
echo "👉 Puis vérifier :"
echo "   curl -I https://$DOMAIN/api/v1/"
