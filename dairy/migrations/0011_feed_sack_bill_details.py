from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def backfill_feed_sack_items(apps, schema_editor):
    FeedSackPurchase = apps.get_model('dairy', 'FeedSackPurchase')
    FeedSackItem = apps.get_model('dairy', 'FeedSackItem')
    rows = []
    for purchase in FeedSackPurchase.objects.all():
        if not FeedSackItem.objects.filter(purchase_id=purchase.id).exists():
            rows.append(
                FeedSackItem(
                    purchase_id=purchase.id,
                    sack_name='Feed sack',
                    price_per_sack=Decimal('0.00'),
                    sack_count=purchase.sack_count,
                )
            )
    FeedSackItem.objects.bulk_create(rows)


class Migration(migrations.Migration):

    dependencies = [
        ('dairy', '0010_businesssetting_data_reset_date'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeedSackItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sack_name', models.CharField(max_length=120)),
                ('price_per_sack', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('sack_count', models.PositiveIntegerField(default=1)),
                (
                    'purchase',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='items',
                        to='dairy.feedsackpurchase',
                    ),
                ),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='FeedSackAdditionalCost',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cost_type', models.CharField(max_length=120)),
                ('amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                (
                    'purchase',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='additional_costs',
                        to='dairy.feedsackpurchase',
                    ),
                ),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.RunPython(backfill_feed_sack_items, migrations.RunPython.noop),
    ]
