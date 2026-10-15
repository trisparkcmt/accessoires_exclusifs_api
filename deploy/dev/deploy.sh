#!/bin/bash
# ============================================================
# deploy.sh — Script de déploiement de l'API Dev
# Branche : main  |  Domaine : dev-api.accessoiresexclusifs.com
# Répertoire VPS : /var/www/accessoiresexclusifs_dev
#
# Usage : sudo bash deploy.sh
# ============================================================
set -e

APP_DIR="/var/www/accessoiresexclusifs_dev"
VENV="$APP_DIR/env"
SERVICE="gunicorn_dev"

echo "📦 [1/6] Pull de la branche main..."
cd "$APP_DIR"
git pull origin main

echo "🐍 [2/6] Mise à jour des dépendances..."
source "$VENV/bin/activate"
pip install -r requirements.txt --quiet

echo "🗄️  [3/6] Migrations..."
python manage.py migrate --noinput

echo "📁 [4/6] Collectstatic..."
python manage.py collectstatic --noinput --clear

echo "🔍 [5/6] Vérification Django..."
python manage.py check

echo "🔄 [6/6] Mise à jour des services systemd et redémarrage (Gunicorn + Celery)..."
cp "$APP_DIR/deploy/dev/gunicorn_dev.service" /etc/systemd/system/gunicorn_dev.service
cp "$APP_DIR/deploy/dev/celery_dev.service" /etc/systemd/system/celery_dev.service
cp "$APP_DIR/deploy/dev/celerybeat_dev.service" /etc/systemd/system/celerybeat_dev.service
systemctl daemon-reload
systemctl enable --now celery_dev.service celerybeat_dev.service 2>/dev/null || true
systemctl restart "$SERVICE"
systemctl restart celery_dev.service 2>/dev/null || true
systemctl restart celerybeat_dev.service 2>/dev/null || true

echo ""
echo "✅ Déploiement dev terminé !"
echo "   API  : https://dev-api.accessoiresexclusifs.com"
echo "   Front: https://dev.accessoiresexclusifs.com"
