from __future__ import annotations

import uuid

from django.db import models


class Cart(models.Model):
    owner_key = models.CharField(max_length=64, unique=True)
    version = models.PositiveBigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="KZT")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product_id = models.PositiveBigIntegerField()
    offer_id = models.CharField(max_length=128, blank=True, default="")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    product_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("cart", "product_id", "offer_id"), name="cart_unique_product_offer"
            ),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="cart_item_quantity_gte_1"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="cart_item_price_gte_0"),
        ]


class CartAction(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        CONFIRMED = "confirmed", "Confirmed"
        EXECUTING = "executing", "Executing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner_key = models.CharField(max_length=64, db_index=True)
    dialog_id = models.CharField(max_length=128)
    message_id = models.CharField(max_length=128)
    message_version = models.PositiveBigIntegerField()
    cart = models.ForeignKey(Cart, on_delete=models.PROTECT, related_name="actions")
    expected_cart_version = models.PositiveBigIntegerField()
    product_id = models.PositiveBigIntegerField()
    offer_id = models.CharField(max_length=128, blank=True, default="")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    price_version = models.CharField(max_length=128)
    pricing_context = models.JSONField(default=dict)
    product_snapshot = models.JSONField(default=dict)
    expires_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROPOSED)
    result = models.JSONField(default=dict, blank=True)
    failure_code = models.CharField(max_length=64, blank=True, default="")
    replacement_for = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replacement",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("owner_key", "dialog_id", "message_id", "message_version"),
                name="cart_unique_message_version",
            ),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="cart_action_quantity_gte_1"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="cart_action_price_gte_0"),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=("proposed", "confirmed", "executing", "succeeded", "failed", "expired")
                ),
                name="cart_action_valid_status",
            ),
        ]
        indexes = [
            models.Index(fields=("owner_key", "dialog_id", "status"), name="cart_action_active_idx"),
        ]


class CartMutation(models.Model):
    idempotency_key = models.UUIDField(primary_key=True, editable=False)
    action = models.OneToOneField(CartAction, on_delete=models.PROTECT, related_name="mutation")
    cart = models.ForeignKey(Cart, on_delete=models.PROTECT, related_name="mutations")
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
