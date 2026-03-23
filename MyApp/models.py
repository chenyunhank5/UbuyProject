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

# Apply the validator to the User model
User._meta.get_field('username').validators = [SpaceUnicodeUsernameValidator()]

def generate_invitation_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# 2. VIP LEVEL MODEL
class VipLevel(models.Model):
    level_number = models.IntegerField(unique=True)
    name = models.CharField(max_length=50)
    missions_per_day = models.IntegerField(default=12)
    min_balance = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    max_tasks = models.IntegerField(default=1)
    image = models.ImageField(upload_to='vip_badges/', null=True, blank=True)

    class Meta:
        ordering = ['level_number']

    def __str__(self):
        return f"{self.name}"

# 3. MISSION MODEL
class Mission(models.Model):
    name = models.CharField(max_length=255)
    image_link = models.URLField(max_length=500)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class MissionRecord(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pendiente'),
        ('Completed', 'Completado'),
        ('Scheduled', 'Programado (Trap)'), # New status for traps
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mission_records')
    mission_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Completed')
    created_at = models.DateTimeField(auto_now_add=True)
    image_link = models.URLField(max_length=500, null=True, blank=True)

    # NEW FIELD: This determines which mission number of the day this record belongs to.
    # Used for scheduling "traps" by the admin.
    scheduled_at = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

# 4. PROFILE MODEL
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    invite_code = models.CharField(max_length=12, unique=True, default=generate_invitation_code)
    membership_vip = models.ForeignKey(VipLevel, on_delete=models.SET_NULL, null=True, blank=True)
    credit_points = models.IntegerField(default=100)
    withdrawal_password = models.CharField(max_length=100, blank=True, null=True)
    can_withdraw = models.BooleanField(default=True)
    missions_count = models.IntegerField(default=0)

    # Bank Details
    withdrawal_method = models.CharField(max_length=50, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    bank_phone_number = models.CharField(max_length=50, blank=True, null=True)

    # Recharge Info
    recharge_receiver_name = models.CharField(max_length=100, default="Angel Mishael Rivera Sandoval")
    recharge_qr = models.ImageField(upload_to='recharge_qrs/', blank=True, null=True)
    referred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals')

    def __str__(self):
        return f"{self.user.username}"

# 5. REQUEST MODELS
class RechargeRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    screenshot = models.ImageField(upload_to='recharge_proofs/')
    status = models.CharField(max_length=10, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

class WithdrawalRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

# 6. SIGNALS
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
