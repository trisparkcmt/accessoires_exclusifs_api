#!/usr/bin/env bash
# ============================================================
# update.sh — Script de mise à jour rapide (après chaque push)
#
# Usage sur le VPS :
#   cd /var/www/accessoiresexclusifs/backend
#   sudo ./deploy/update.sh
# ============================================================

set -euo pipefail

APP_DIR="/var/www/accessoiresexclusifs"
BRANCH="master"

echo "🔄 Mise à jour du code..."
cd "$APP_DIR/backend"
git fetch origin
git reset --hard "origin/$BRANCH"

echo "📦 Mise à jour des dépendances..."
source "$APP_DIR/venv/bin/activate"
pip install -r requirements.txt -q

echo "⚙️  Migrations & static files..."
python manage.py migrate --noinput
python manage.py collectstatic --noinput -v 0

echo "♻️  Redémarrage de Gunicorn..."
systemctl restart gunicorn

echo "✅ Mise à jour terminée !"
