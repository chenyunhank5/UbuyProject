from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from decimal import Decimal
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Profile, RechargeRequest, WithdrawalRequest, VipLevel
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth import update_session_auth_hash

# --- PUBLIC REGISTRATION VIEW ---

def register_view(request):
    lang = request.GET.get('lang', 'es')

    if request.method == "POST":
        username = request.POST.get('username')
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        invite_code = request.POST.get('invite_code')

        if Profile.objects.filter(phone_number=phone).exists():
            messages.error(request, "Teléfono ya registrado" if lang == 'es' else "Phone already registered")
            return render(request, 'user/register.html', {'lang': lang})

        try:
            with transaction.atomic():
                new_user = User.objects.create_user(username=username, password=password)
                profile = new_user.profile
                profile.phone_number = phone

                # Assign default VIP level from Database using membership_vip
                default_vip = VipLevel.objects.order_by('level_number').first()
                if default_vip:
                    profile.membership_vip = default_vip

                inviter = Profile.objects.filter(invite_code=invite_code).first()
                if inviter:
                    profile.referred_by = inviter.user

                profile.save()

                auth_login(request, new_user)
                return redirect(f'/?tab=home&lang={lang}')

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, 'user/register.html', {'lang': lang})

# --- USER DASHBOARD ---

@login_required
def index(request):
    current_tab = request.GET.get('tab', 'home')
    lang = request.GET.get('lang', 'es')
    profile, created = Profile.objects.get_or_create(user=request.user)

    withdrawals = WithdrawalRequest.objects.filter(user=request.user).order_by('-created_at')
    recharges = RechargeRequest.objects.filter(user=request.user).order_by('-created_at')
    vip_levels = VipLevel.objects.all().order_by('level_number')

    # Updated to use membership_vip
    user_vip = profile.membership_vip

    show_security_setup = False
    if current_tab == 'withdraw' and not profile.withdrawal_password:
        show_security_setup = True

    # Mission Data Logic - Now correctly containing rates from the VIP level
    active_mission = {
        'product_name': 'ASUS PN64 i7-12700H Barebone Mini PC Bundle / RAM / M.2 NVMe SSD / Win 11 Intel NUC',
        'price': '18,184.41',
        'commission': '10,001.43',
        'shortfall': '7,352.00',
        'image': 'https://down-sg.img.susercontent.com/file/3f0dda3859195bddf309fb8f3813a5fa',
        'commission_rate': user_vip.commission_rate if user_vip else 0,
        'daily_tasks_limit': user_vip.max_tasks if user_vip else 0,
    }

    context = {
        'active_tab': current_tab,
        'profile': profile,
        'lang': lang,
        'show_security_setup': show_security_setup,
        'withdrawals': withdrawals,
        'recharges': recharges,
        'vip_levels': vip_levels,
        'active_mission': active_mission,
    }
    return render(request, 'user/index.html', context)

# --- STAFF MANAGEMENT ---

@staff_member_required
def staff_index(request):
    query = request.GET.get('q', '')
    current_tab = request.GET.get('tab', 'home')

    if query:
        all_users_list = User.objects.filter(
            Q(username__icontains=query) |
            Q(profile__phone_number__icontains=query)
        ).order_by('-date_joined')
    else:
        all_users_list = User.objects.all().order_by('-date_joined')

    vip_levels = VipLevel.objects.all().order_by('level_number')

    context = {
        'tab': current_tab,
        'users': Paginator(all_users_list, 20).get_page(request.GET.get('page')),
        'pending_recharges': RechargeRequest.objects.filter(status='Pending').order_by('-created_at'),
        'pending_withdrawals': WithdrawalRequest.objects.filter(status='Pending').order_by('-created_at'),
        'all_withdrawals': WithdrawalRequest.objects.all().order_by('-created_at'),
        'vip_levels': vip_levels,
        'search_query': query,
    }
    return render(request, 'staff/index.html', context)

@staff_member_required
def add_user(request):
    if request.method == "POST":
        username = request.POST.get('username')
        phone = request.POST.get('phone')
        password = request.POST.get('password')

        if not User.objects.filter(username=username).exists():
            with transaction.atomic():
                new_user = User.objects.create_user(username=username, password=password)
                p = new_user.profile
                p.phone_number = phone

                default_vip = VipLevel.objects.order_by('level_number').first()
                if default_vip:
                    p.membership_vip = default_vip

                p.save()
            messages.success(request, f"User {username} created!")
        else:
            messages.error(request, "Username exists!")
    return redirect('/staff/?tab=users')

@staff_member_required
def update_user(request, user_id):
    if request.method == "POST":
        target_user = get_object_or_404(User, id=user_id)
        p = target_user.profile

        # Update Basic User Data
        target_user.username = request.POST.get('username')
        new_pw = request.POST.get('new_password')
        if new_pw:
            target_user.set_password(new_pw)
        target_user.save()

        # Update Profile Data
        p.phone_number = request.POST.get('phone')
        p.invite_code = request.POST.get('invite_code')
        p.credit_points = int(request.POST.get('credit', 100))

        # --- VIP UPDATE LOGIC ---
        vip_id = request.POST.get('vip')  # CHECK THIS NAME IN YOUR HTML

        if vip_id and vip_id != '0':
            try:
                selected_vip = VipLevel.objects.get(id=vip_id)
                p.membership_vip = selected_vip
            except (VipLevel.DoesNotExist, ValueError):
                messages.error(request, f"VIP Level ID {vip_id} not found.")

        # Ensure they always have at least the lowest level
        if not p.membership_vip:
            p.membership_vip = VipLevel.objects.order_by('level_number').first()

        # Update Security & Bank Info
        p.withdrawal_password = request.POST.get('withdrawal_password')
        p.bank_name = request.POST.get('bank_name')
        p.account_name = request.POST.get('account_name')
        p.account_number = request.POST.get('account_number')
        p.bank_phone_number = request.POST.get('bank_phone_number')
        p.recharge_receiver_name = request.POST.get('recharge_receiver_name')

        # Handle QR Code
        if request.POST.get('delete_qr') == 'on':
            if p.recharge_qr:
                p.recharge_qr.delete(save=False)
            p.recharge_qr = None

        if 'recharge_qr' in request.FILES:
            p.recharge_qr = request.FILES['recharge_qr']

        p.save()
        messages.success(request, f"User {target_user.username} updated successfully!")

    return redirect('/staff/?tab=users')

@staff_member_required
def update_balance(request, user_id):
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)
        amount = Decimal(request.POST.get('amount', '0'))
        if request.POST.get('action') == 'add': user.profile.balance += amount
        else: user.profile.balance -= amount
        user.profile.save()
    return redirect('/staff/?tab=users')

# --- VIP MANAGEMENT ---

@staff_member_required
def save_vip_level(request, level_id=None):
    if request.method == "POST":
        if level_id:
            vip = get_object_or_404(VipLevel, id=level_id)
        else:
            vip = VipLevel()

        try:
            # Basic Data
            vip.level_number = int(request.POST.get('level_number'))
            vip.name = request.POST.get('name')
            vip.min_balance = Decimal(request.POST.get('min_balance', '0'))
            vip.commission_rate = Decimal(request.POST.get('commission_rate', '0'))
            vip.max_tasks = int(request.POST.get('max_tasks', '1'))

            # Handle the Image Upload
            if 'image' in request.FILES:
                vip.image = request.FILES['image']

            vip.save()
            messages.success(request, f"VIP Level {vip.name} saved successfully!")
        except Exception as e:
            messages.error(request, f"Error saving VIP: {str(e)}")

    return redirect('/staff/?tab=vip')

@staff_member_required
def delete_vip_level(request, level_id):
    vip = get_object_or_404(VipLevel, id=level_id)
    name = vip.name
    vip.delete()
    messages.success(request, f"VIP Level {name} deleted!")
    return redirect('/staff/?tab=vip')

@staff_member_required
def update_vip_level(request, level_id):
    return save_vip_level(request, level_id)

# --- RECHARGE & WITHDRAWAL ---

@login_required
def recharge(request):
    return render(request, 'user/recharge.html', {
        'profile': request.user.profile,
        'lang': request.GET.get('lang', 'es')
    })

@login_required
def submit_recharge(request):
    lang = request.GET.get('lang', 'es')
    if request.method == "POST":
        amount = request.POST.get('amount')
        screenshot = request.FILES.get('proof')
        if amount and screenshot:
            RechargeRequest.objects.create(user=request.user, amount=Decimal(amount), screenshot=screenshot)
            messages.success(request, "Recarga enviada" if lang == 'es' else "Recharge sent")
            return redirect(f'/?tab=recharge&lang={lang}')
    return redirect(f'/?tab=recharge&lang={lang}')

@login_required
def withdraw(request):
    return render(request, 'user/withdraw.html', {
        'profile': request.user.profile,
        'lang': request.GET.get('lang', 'es')
    })

@login_required
def submit_withdrawal(request):
    lang = request.GET.get('lang', 'es')
    if request.method == "POST":
        p = request.user.profile
        if not p.can_withdraw:
            msg = "Los retiros están deshabilitados para su cuenta." if lang == 'es' else "Withdrawals are disabled for your account."
            messages.error(request, msg)
            return redirect(f'/?tab=withdraw&lang={lang}')

        amount = Decimal(request.POST.get('amount', '0'))
        password = request.POST.get('password')

        if p.withdrawal_password == password and p.balance >= amount and amount >= 50:
            with transaction.atomic():
                p.balance -= amount
                p.save()
                WithdrawalRequest.objects.create(user=request.user, amount=amount)
            messages.success(request, "Retiro exitoso" if lang == 'es' else "Withdrawal successful")
            return redirect(f'/?tab=withdraw&lang={lang}')

        messages.error(request, "Error en el retiro")
    return redirect(f'/?tab=withdraw&lang={lang}')

@staff_member_required
def process_recharge(request, request_id, action):
    req = get_object_or_404(RechargeRequest, id=request_id)
    if req.status == 'Pending':
        if action == 'approve':
            req.status = 'Approved'
            req.user.profile.balance += req.amount
            req.user.profile.save()
        else: req.status = 'Rejected'
        req.save()
    return redirect('/staff/?tab=users')

@login_required
def update_withdrawal_info(request):
    if request.method == "POST":
        profile = request.user.profile
        profile.withdrawal_method = request.POST.get('method')
        profile.bank_name = request.POST.get('bank_name')
        profile.account_name = request.POST.get('account_name')
        profile.account_number = request.POST.get('account_number')
        profile.bank_phone_number = request.POST.get('bank_phone')
        profile.save()
        messages.success(request, "Información guardada" if request.GET.get('lang') != 'en' else "Information saved")
    return redirect('/?tab=profile')

@staff_member_required
def process_withdrawal(request, request_id, action):
    req = get_object_or_404(WithdrawalRequest, id=request_id)
    if req.status == 'Pending':
        if action == 'approve': req.status = 'Approved'
        else:
            req.user.profile.balance += req.amount
            req.user.profile.save()
            req.status = 'Rejected'
        req.save()
    return redirect('/staff/?tab=withdrawals')

@login_required
def invite(request):
    return render(request, 'user/invite.html', {'lang': request.GET.get('lang', 'es')})

@login_required
def set_withdrawal_password(request):
    lang = request.GET.get('lang', 'es')
    profile = request.user.profile
    if request.method == "POST":
        new_password = request.POST.get('withdrawal_password')
        confirm_password = request.POST.get('confirm_password')
        if new_password == confirm_password:
            profile.withdrawal_password = new_password
            profile.save()
            messages.success(request, "Contraseña de retiro creada" if lang == 'es' else "Withdrawal password created")
            return redirect(f'/?tab=home&lang={lang}')
        else:
            messages.error(request, "Las contraseñas no coinciden" if lang == 'es' else "Passwords do not match")
    return render(request, 'user/create_withdrawal_password.html', {'lang': lang})

def update_security(request):
    profile = request.user.profile
    lang = request.GET.get('lang', 'es')
    def msg(en, es): return en if lang == 'en' else es

    if request.method == 'POST':
        action = request.POST.get('action')
        old_pw = request.POST.get('old_password')
        new_pw = request.POST.get('new_password')
        confirm_pw = request.POST.get('confirm_password')

        if new_pw != confirm_pw:
            messages.error(request, msg("Passwords do not match", "Las contraseñas no coinciden"))
            return redirect(f"/?tab=security&lang={lang}")

        if action == 'login_password':
            if request.user.check_password(old_pw):
                request.user.set_password(new_pw)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, msg("Password updated successfully", "Contraseña actualizada con éxito"))
                return redirect(f"/?tab=profile&lang={lang}")
            else:
                messages.error(request, msg("Incorrect old password", "Contraseña anterior incorrecta"))

        elif action == 'withdrawal_password':
            if profile.withdrawal_password == old_pw:
                profile.withdrawal_password = new_pw
                profile.save()
                messages.success(request, msg("PIN updated successfully", "PIN actualizado con éxito"))
                return redirect(f"/?tab=profile&lang={lang}")
            else:
                messages.error(request, msg("Incorrect old PIN", "PIN anterior incorrecto"))

    return redirect(f"/?tab=security&lang={lang}")

@staff_member_required
def toggle_withdrawal_status(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    p = target_user.profile
    p.can_withdraw = not p.can_withdraw
    p.save()
    status = "habilitados" if p.can_withdraw else "deshabilitados"
    messages.success(request, f"Retiros {status} para {target_user.username}")
    return redirect('/staff/?tab=users')

# --- AUTHENTICATION ---

def login_view(request):
    lang = request.GET.get('lang', 'es')
    if request.user.is_authenticated:
        return redirect(f'/?tab=home&lang={lang}')

    if request.method == "POST":
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        try:
            profile = Profile.objects.get(phone_number=phone)
            user_obj = profile.user
            authenticated_user = authenticate(request, username=user_obj.username, password=password)
            if authenticated_user is not None:
                auth_login(request, authenticated_user)
                messages.success(request, "¡Bienvenido!" if lang == 'es' else "Welcome!")
                return redirect(f'/?tab=home&lang={lang}')
            else:
                messages.error(request, "Contraseña incorrecta." if lang == 'es' else "Incorrect password.")
        except Profile.DoesNotExist:
            messages.error(request, "El número no está registrado." if lang == 'es' else "Phone not registered.")
    return render(request, 'user/login.html', {'lang': lang})

def logout_view(request):
    auth_logout(request)
    return redirect('login')
