import os
from celery import Celery

# Définir le module de configuration Django par défaut pour 'celery'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# Charger la configuration depuis Django settings avec le préfixe CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Découverte automatique des tasks.py dans chaque application installée
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
