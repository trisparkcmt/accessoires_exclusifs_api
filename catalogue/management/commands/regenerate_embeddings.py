from django.core.management.base import BaseCommand
from django.db import transaction
from catalogue.models import Essence, Parfum, Accessoire
from catalogue.signals import _build_essence_embedding_text, _build_parfum_embedding_text, _build_accessoire_embedding_text, _generate_ollama_embedding


class Command(BaseCommand):
    help = 'Régénère les embeddings pour toutes les essences, parfums et accessoires existants.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Début de la régénération des embeddings...'))

        with transaction.atomic():
            self._regenerate_embeddings_for_model(Essence, _build_essence_embedding_text, 'essence')
            self._regenerate_embeddings_for_model(Parfum, _build_parfum_embedding_text, 'parfum')
            self._regenerate_embeddings_for_model(Accessoire, _build_accessoire_embedding_text, 'accessoire')

        self.stdout.write(self.style.SUCCESS('Régénération des embeddings terminée.'))

    def _regenerate_embeddings_for_model(self, model_cls, build_text_fn, label):
        qs = model_cls.objects.filter(actif=True)
        total = qs.count()
        self.stdout.write(f'  - {total} {label}s à traiter...')

        for index, instance in enumerate(qs.iterator(), start=1):
            text = build_text_fn(instance)
            embedding = _generate_ollama_embedding(text)
            if embedding is not None:
                model_cls.objects.filter(pk=instance.pk).update(embedding=embedding)
                self.stdout.write(self.style.SUCCESS(f'    [{index}/{total}] {label} {instance.pk} mis à jour'))
            else:
                self.stdout.write(self.style.WARNING(f'    [{index}/{total}] {label} {instance.pk} impossible à générer'))
