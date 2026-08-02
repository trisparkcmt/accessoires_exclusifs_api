from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0014_diffuseurparfum'),
        ('utilisateur', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='favori',
            name='produit_fini_essence',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='favoris', to='catalogue.produitfiniessence'),
        ),
        migrations.AddConstraint(
            model_name='favori',
            constraint=models.UniqueConstraint(condition=models.Q(('produit_fini_essence__isnull', False)), fields=('client', 'produit_fini_essence'), name='unique_favori_produit_fini_essence'),
        ),
    ]
