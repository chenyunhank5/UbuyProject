import string
import random
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.validators import UnicodeUsernameValidator

# 1. CUSTOM VALIDATOR
class SpaceUnicodeUsernameValidator(UnicodeUsernameValidator):
    regex = r'^[\w.@+ -]+$'
    message = "Enter a valid username. This value may contain only letters, numbers, spaces, and @/./+/-/_ characters."

# Apply the validator to the default User model
User._meta.get_field('username').validators = [SpaceUnicodeUsernameValidator()]

# 2. UTILITY FUNCTIONS
def generate_invitation_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

class VipLevel(models.Model):
    level_number = models.IntegerField(unique=True) # e.g., 1, 2, 3
    name = models.CharField(max_length=50)          # e.g., "VIP 1"
    min_balance = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    max_tasks = models.IntegerField(default=1)
    # The new image field for the badge
    image = models.ImageField(upload_to='vip_badges/', null=True, blank=True)

    class Meta:
        ordering = ['level_number']

    def __str__(self):
        return f"{self.name} (Min: {self.min_balance})"

# 3. PROFILE MODEL
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    invite_code = models.CharField(max_length=12, unique=True, default=generate_invitation_code)

    # --- UPDATED: RENAMED TO membership_vip TO BYPASS DATABASE CONFLICTS ---
    membership_vip = models.ForeignKey(VipLevel, on_delete=models.SET_NULL, null=True, blank=True)

    credit_points = models.IntegerField(default=100)

    # Withdrawal Security
    withdrawal_password = models.CharField(max_length=100, blank=True, null=True, help_text="PIN stored as string")
    can_withdraw = models.BooleanField(default=True)

    # Bank Details
    withdrawal_method = models.CharField(max_length=50, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    bank_phone_number = models.CharField(max_length=50, blank=True, null=True)

    # Admin Controlled Recharge Info
    recharge_receiver_name = models.CharField(
        max_length=100,
        default="Angel Mishael Rivera Sandoval"
    )
    recharge_qr = models.ImageField(upload_to='recharge_qrs/', blank=True, null=True)

    # Referral Tracking
    referred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals')

    def __str__(self):
        return f"{self.user.username} ({self.phone_number})"

# 4. RECHARGE REQUEST MODEL
class RechargeRequest(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    screenshot = models.ImageField(upload_to='recharge_proofs/')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.amount} ({self.status})"

# 5. WITHDRAWAL REQUEST MODEL
class WithdrawalRequest(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Withdrawal: {self.user.username} - {self.amount} ({self.status})"

# 6. SIGNALS
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
