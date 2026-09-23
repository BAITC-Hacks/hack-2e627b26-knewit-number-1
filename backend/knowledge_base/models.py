from django.db import models


class KnowledgeEntry(models.Model):
    class Status(models.TextChoices):
        APPROVED = "approved", "Approved"
        APPROVED_WITH_QUALIFICATION = "approved_with_qualification", "Approved with qualification"
        CONFLICTED = "conflicted", "Conflicted"
        MISSING = "missing", "Missing"

    intent = models.CharField(max_length=128)
    variants = models.JSONField(default=list)
    answer_ru = models.TextField(blank=True)
    answer_kk = models.TextField(blank=True)
    source_url = models.URLField(max_length=500)
    verified_at = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=40, choices=Status.choices)
    owner = models.CharField(max_length=128)
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True)
    published = models.BooleanField(default=True)
    conflict_group = models.CharField(max_length=128, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("intent", "is_current", "published")),
            models.Index(fields=("status", "is_current")),
        ]

