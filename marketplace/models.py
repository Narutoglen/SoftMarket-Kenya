from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ServiceCategory(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    min_price = models.PositiveIntegerField()
    max_price = models.PositiveIntegerField(null=True, blank=True)
    deposit_amount = models.PositiveIntegerField()
    monthly = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "service categories"

    def __str__(self):
        return self.name


class DeveloperProfile(TimeStampedModel):
    class Status(models.TextChoices):
        APPLIED = "applied", "Applied"
        VETTED = "vetted", "Vetted"
        PAUSED = "paused", "Paused"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    stack = models.CharField(max_length=260)
    portfolio_url = models.URLField(blank=True)
    service_categories = models.ManyToManyField(ServiceCategory, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPLIED)
    availability_score = models.PositiveSmallIntegerField(default=5)
    quality_score = models.PositiveSmallIntegerField(default=5)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class DeveloperApplication(TimeStampedModel):
    name = models.CharField(max_length=160)
    stack = models.CharField(max_length=260)
    portfolio_url = models.URLField()
    converted_profile = models.ForeignKey(
        DeveloperProfile, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class ProjectRequest(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        REVIEWING = "reviewing", "Reviewing"
        MATCHED = "matched", "Matched"
        QUOTED = "quoted", "Quoted"
        DEPOSIT_PENDING = "deposit_pending", "Deposit pending"
        DEPOSIT_PAID = "deposit_paid", "Deposit paid"
        IN_PROGRESS = "in_progress", "In progress"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=40)
    email = models.EmailField()
    service = models.ForeignKey(ServiceCategory, null=True, blank=True, on_delete=models.SET_NULL)
    service_label = models.CharField(max_length=140)
    budget = models.CharField(max_length=80)
    timeline = models.CharField(max_length=80)
    details = models.TextField()
    utm_source = models.CharField(max_length=120, blank=True)
    utm_medium = models.CharField(max_length=120, blank=True)
    utm_campaign = models.CharField(max_length=120, blank=True)
    estimated_min = models.PositiveIntegerField(null=True, blank=True)
    estimated_max = models.PositiveIntegerField(null=True, blank=True)
    deposit_amount = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.NEW)
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.service_label}"


class Assignment(TimeStampedModel):
    class Status(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        ASSIGNED = "assigned", "Assigned"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    project = models.ForeignKey(ProjectRequest, related_name="assignments", on_delete=models.CASCADE)
    developer = models.ForeignKey(DeveloperProfile, related_name="assignments", on_delete=models.CASCADE)
    score = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUGGESTED)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-score", "-created_at"]
        unique_together = [("project", "developer")]

    def __str__(self):
        return f"{self.project} -> {self.developer}"


class Payment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        STK_SENT = "stk_sent", "STK sent"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    project = models.ForeignKey(ProjectRequest, related_name="payments", on_delete=models.CASCADE)
    amount = models.PositiveIntegerField()
    phone = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    merchant_request_id = models.CharField(max_length=120, blank=True)
    checkout_request_id = models.CharField(max_length=120, blank=True, db_index=True)
    mpesa_receipt = models.CharField(max_length=120, blank=True)
    result_code = models.CharField(max_length=20, blank=True)
    result_description = models.TextField(blank=True)
    callback_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.project} - KSh {self.amount} ({self.get_status_display()})"


class NotificationLog(TimeStampedModel):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        SYSTEM = "system", "System"

    channel = models.CharField(max_length=20, choices=Channel.choices)
    recipient = models.CharField(max_length=220)
    subject = models.CharField(max_length=220, blank=True)
    message = models.TextField()
    success = models.BooleanField(default=False)
    provider_response = models.TextField(blank=True)
    project = models.ForeignKey(ProjectRequest, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_channel_display()} to {self.recipient}"


class BlogPost(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class ImagePlacement(models.TextChoices):
        MIDDLE = "middle", "Middle"
        END = "end", "End"

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True)
    category = models.CharField(max_length=80, blank=True, default="")
    author_name = models.CharField(max_length=120, blank=True, default="")
    author_role = models.CharField(max_length=160, blank=True, default="")
    excerpt = models.TextField(max_length=420)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    main_image = models.ImageField(upload_to="blog/main/", blank=True)
    content_image = models.ImageField(upload_to="blog/content/", blank=True)
    content_image_placement = models.CharField(
        max_length=20,
        choices=ImagePlacement.choices,
        default=ImagePlacement.MIDDLE,
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def author_display(self):
        if self.author_name and self.author_role:
            return f"{self.author_name}, {self.author_role}"
        return self.author_name or self.author_role

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    def save(self, *args, **kwargs):
        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)
