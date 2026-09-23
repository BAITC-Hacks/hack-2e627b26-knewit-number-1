import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Cart",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("owner_key", models.CharField(max_length=64, unique=True)),
                ("version", models.PositiveBigIntegerField(default=0)),
                ("currency", models.CharField(default="KZT", max_length=3)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="CartAction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("owner_key", models.CharField(db_index=True, max_length=64)),
                ("dialog_id", models.CharField(max_length=128)),
                ("message_id", models.CharField(max_length=128)),
                ("message_version", models.PositiveBigIntegerField()),
                ("expected_cart_version", models.PositiveBigIntegerField()),
                ("product_id", models.PositiveBigIntegerField()),
                ("offer_id", models.CharField(blank=True, default="", max_length=128)),
                ("quantity", models.PositiveIntegerField()),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=18)),
                ("currency", models.CharField(max_length=3)),
                ("price_version", models.CharField(max_length=128)),
                ("pricing_context", models.JSONField(default=dict)),
                ("product_snapshot", models.JSONField(default=dict)),
                ("expires_at", models.DateTimeField(db_index=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("proposed", "Proposed"),
                            ("confirmed", "Confirmed"),
                            ("executing", "Executing"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("expired", "Expired"),
                        ],
                        default="proposed",
                        max_length=16,
                    ),
                ),
                ("result", models.JSONField(blank=True, default=dict)),
                ("failure_code", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "cart",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="actions", to="cart.cart"),
                ),
                (
                    "replacement_for",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="replacement",
                        to="cart.cartaction",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CartItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product_id", models.PositiveBigIntegerField()),
                ("offer_id", models.CharField(blank=True, default="", max_length=128)),
                ("quantity", models.PositiveIntegerField()),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=18)),
                ("product_snapshot", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "cart",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="cart.cart"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CartMutation",
            fields=[
                ("idempotency_key", models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ("result", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "action",
                    models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="mutation", to="cart.cartaction"),
                ),
                (
                    "cart",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mutations", to="cart.cart"),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="cartaction",
            constraint=models.UniqueConstraint(
                fields=("owner_key", "dialog_id", "message_id", "message_version"),
                name="cart_unique_message_version",
            ),
        ),
        migrations.AddConstraint(
            model_name="cartaction",
            constraint=models.CheckConstraint(condition=models.Q(("quantity__gte", 1)), name="cart_action_quantity_gte_1"),
        ),
        migrations.AddConstraint(
            model_name="cartaction",
            constraint=models.CheckConstraint(condition=models.Q(("unit_price__gte", 0)), name="cart_action_price_gte_0"),
        ),
        migrations.AddConstraint(
            model_name="cartaction",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["proposed", "confirmed", "executing", "succeeded", "failed", "expired"])),
                name="cart_action_valid_status",
            ),
        ),
        migrations.AddIndex(
            model_name="cartaction",
            index=models.Index(fields=["owner_key", "dialog_id", "status"], name="cart_action_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.UniqueConstraint(fields=("cart", "product_id", "offer_id"), name="cart_unique_product_offer"),
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.CheckConstraint(condition=models.Q(("quantity__gte", 1)), name="cart_item_quantity_gte_1"),
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.CheckConstraint(condition=models.Q(("unit_price__gte", 0)), name="cart_item_price_gte_0"),
        ),
    ]
