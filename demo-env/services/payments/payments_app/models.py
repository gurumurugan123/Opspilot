from django.db import models
import uuid

class PaymentTransaction(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=64, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Payment {self.id} for Order {self.order_id} ({self.status})"
