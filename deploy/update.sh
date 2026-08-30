#!/usr/bin/env bash
# ============================================================
# update.sh — Script de mise à jour rapide du VPS
# ============================================================
set -e

APP_DIR="/var/www/accessoiresexclusifs"
BRANCH="${1:-master}"

echo "🔄 Mise à jour d'Accessoires Exclusifs API ($BRANCH)..."
cd "$APP_DIR"

git config --global --add safe.directory "$APP_DIR"
git fetch origin
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

source "$APP_DIR/venv/bin/activate"
pip install -r requirements.txt -q
python manage.py collectstatic --noinput -v 0
python manage.py migrate --noinput

cp deploy/gunicorn.service /etc/systemd/system/gunicorn.service
systemctl daemon-reload
systemctl restart gunicorn
systemctl reload nginx

echo "✅ Mise à jour réussie !"
