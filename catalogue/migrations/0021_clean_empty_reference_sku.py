# Generated to clean empty reference_sku strings to NULL

from django.db import migrations


def clean_empty_reference_sku(apps, schema_editor):
    Parfum = apps.get_model('catalogue', 'Parfum')
    Accessoire = apps.get_model('catalogue', 'Accessoire')
    Flacon = apps.get_model('catalogue', 'Flacon')
    DiffuseurParfum = apps.get_model('catalogue', 'DiffuseurParfum')

    Parfum.objects.filter(reference_sku='').update(reference_sku=None)
    Accessoire.objects.filter(reference_sku='').update(reference_sku=None)
    Flacon.objects.filter(reference_sku='').update(reference_sku=None)
    DiffuseurParfum.objects.filter(reference_sku='').update(reference_sku=None)


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0020_add_inspire_de_to_parfum'),
    ]

    operations = [
        migrations.RunPython(clean_empty_reference_sku, reverse_code=migrations.RunPython.noop),
    ]
