from django.db import models
import uuid

class Order(models.Model):
    STATUS_CHOICES = [
        ("CREATED", "Created"),
        ("PAID", "Paid"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item_id = models.CharField(max_length=64)
    quantity = models.IntegerField(default=1)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="CREATED")
    payment_id = models.CharField(max_length=64, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Order {self.id} ({self.status})"
