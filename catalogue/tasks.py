import logging
from celery import shared_task
from django.apps import apps
from catalogue.utils import compress_image_to_webp

logger = logging.getLogger('catalogue')


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    autoretry_for=(Exception,),
)
def compress_model_images_async(self, app_label, model_name, instance_id, field_names):
    """
    Tâche Celery pour compresser et convertir les images d'un modèle en WebP en arrière-plan
    sans bloquer la requête HTTP de l'administrateur.
    """
    try:
        model = apps.get_model(app_label, model_name)
        instance = model.objects.get(pk=instance_id)
        fields_to_update = []

        for field_name in field_names:
            image_field = getattr(instance, field_name, None)
            if image_field and getattr(image_field, 'name', None):
                # Si l'image n'est pas déjà en .webp
                if not image_field.name.lower().endswith('.webp'):
                    new_content = compress_image_to_webp(image_field)
                    if new_content:
                        image_field.save(new_content.name, new_content, save=False)
                        fields_to_update.append(field_name)

        if fields_to_update:
            instance.save(update_fields=fields_to_update)
            logger.info(f"[CELERY IMAGES] Compression réussie pour {model_name} #{instance_id}: {fields_to_update}")
        return True
    except Exception as exc:
        logger.warning(f"[CELERY IMAGES] Échec compression pour {model_name} #{instance_id}: {exc}")
        raise exc
