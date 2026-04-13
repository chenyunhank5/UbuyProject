import string
import random
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.validators import UnicodeUsernameValidator

# ==========================================
# 1. CUSTOM VALIDATOR
# ==========================================
class SpaceUnicodeUsernameValidator(UnicodeUsernameValidator):
    regex = r'^[\w.@+ -]+$'
    message = "Enter a valid username. This value may contain only letters, numbers, spaces, and @/./+/-/_ characters."

# Apply the validator to the User model
User._meta.get_field('username').validators = [SpaceUnicodeUsernameValidator()]

def generate_invitation_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# ==========================================
# 2. VIP LEVEL MODEL
# ==========================================
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

# ==========================================
# 3. MISSION MODELS
# ==========================================
class Mission(models.Model):
    name = models.CharField(max_length=255)
    image_link = models.URLField(max_length=500)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    order_count = models.IntegerField(default=1, help_text="Number of orders contained in this mission")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class MissionRecord(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pendiente'),
        ('Completed', 'Completado'),
        ('Scheduled', 'Programado (Trap)'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mission_records')
    mission_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission = models.DecimalField(max_digits=12, decimal_places=2)
    order_count = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Completed')
    created_at = models.DateTimeField(auto_now_add=True)
    image_link = models.URLField(max_length=500, null=True, blank=True)
    required_recharge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    scheduled_at = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

# ==========================================
# 4. NOTIFICATION / MESSAGE MODEL (NEW)
# ==========================================
class UserMessage(models.Model):
    """
    Stores individual messages sent by staff to users.
    Allows for message history.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_messages')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at'] # Newest messages show first

    def __str__(self):
        return f"Msg to {self.user.username} at {self.created_at}"

# ==========================================
# 5. PROFILE MODEL
# ==========================================
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
    recharge_receiver_name = models.CharField(max_length=100, default="")
    recharge_qr = models.ImageField(upload_to='recharge_qrs/', blank=True, null=True)
    referred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals')

    # Status Flags
    system_message = models.TextField(blank=True, null=True) # Keeping for legacy/single notices
    show_system_message = models.BooleanField(default=False) # Use as a 'New Notification' flag

    def __str__(self):
        return f"{self.user.username}"

# ==========================================
# 6. REQUEST MODELS
# ==========================================
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

# ==========================================
# 7. SIGNALS
# ==========================================
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


# ==========================================
# 8. GLOBAL SETTINGS MODEL (NEW)
# ==========================================
class GlobalSettings(models.Model):
    site_name = models.CharField(max_length=100, default="Ubuy Project")
    # Global Payment Details
    global_recharge_receiver_name = models.CharField(
        max_length=100,
        default=""
    )
    global_recharge_qr = models.ImageField(
        upload_to='recharge_qrs/global/',
        null=True,
        blank=True
    )

    # Add other global toggles here if needed (e.g. maintenance mode)
    is_maintenance_mode = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Global Settings"
        verbose_name_plural = "Global Settings"

    def __str__(self):
        return "System Global Configuration"

    def save(self, *args, **kwargs):
        # This logic ensures only one GlobalSettings object exists
        if not self.pk and GlobalSettings.objects.exists():
            return
        super(GlobalSettings, self).save(*args, **kwargs)
