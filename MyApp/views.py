from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from decimal import Decimal
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Profile, RechargeRequest, WithdrawalRequest, VipLevel, Mission, MissionRecord
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth import update_session_auth_hash
import random

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

    profile = request.user.profile
    user_vip = profile.membership_vip

    progress_percentage = 0
    if user_vip and user_vip.missions_per_day > 0:
        progress_percentage = (profile.missions_count / user_vip.missions_per_day) * 100

    vips = VipLevel.objects.all().order_by('level_number')

    records = MissionRecord.objects.filter(
        user=request.user
    ).order_by('-created_at')

    # 🔒 GET PENDING MISSION
    pending = MissionRecord.objects.filter(
        user=request.user,
        status='Pending'
    ).first()

    active_mission = None
    limit_reached = False

    if pending:
        # ✅ LOCKED STATE
        active_mission = {
            'id': pending.id,
            'product_name': pending.mission_name,
            'price': pending.amount,
            'commission': pending.commission,
            'image': pending.image_link,
            'is_pending_lock': True,
            'shortfall': max(Decimal('0'), pending.amount - profile.balance),
        }

    else:
        # 🚫 LIMIT CHECK
        if user_vip and profile.missions_count >= user_vip.missions_per_day:
            limit_reached = True

        # ✅ IMPORTANT: still send safe object
        active_mission = {
            'is_pending_lock': False
        }

    context = {
        'active_tab': current_tab,
        'profile': profile,
        'lang': lang,
        'vip_levels': vips,
        'active_mission': active_mission,
        'limit_reached': limit_reached,
        'records': records,
        'progress_percentage': progress_percentage,
    }

    return render(request, 'user/index.html', context)

# --- STAFF MANAGEMENT ---
@staff_member_required
def reset_user_missions(request, user_id):
    if request.method == "POST":
        user_profile = get_object_or_404(Profile, user_id=user_id)
        user_profile.missions_count = 0
        user_profile.save()
        messages.success(request, f"Missions reset for {user_profile.user.username}")
    return redirect('/staff/?tab=users')

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
    missions = Mission.objects.all().order_by('-created_at')

    context = {
        'tab': current_tab,
        'users': Paginator(all_users_list, 20).get_page(request.GET.get('page')),
        'pending_recharges': RechargeRequest.objects.filter(status='Pending').order_by('-created_at'),
        'pending_withdrawals': WithdrawalRequest.objects.filter(status='Pending').order_by('-created_at'),
        'all_withdrawals': WithdrawalRequest.objects.all().order_by('-created_at'),
        'vip_levels': vip_levels,
        'missions': missions,
        'search_query': query,
    }
    return render(request, 'staff/index.html', context)

# --- STAFF MISSION MANAGEMENT ---
@staff_member_required
def save_mission(request):
    if request.method == "POST":
        name = request.POST.get('name')
        price = request.POST.get('price')
        image_link = request.POST.get('image_link')

        try:
            Mission.objects.create(
                name=name,
                price=price,
                image_link=image_link
            )
            messages.success(request, "Mission created successfully!")
        except Exception as e:
            messages.error(request, f"Database Error: {e}")

        return redirect('/staff/?tab=missions')
    return redirect('/staff/')

@staff_member_required
def delete_mission(request, mission_id):
    mission = get_object_or_404(Mission, id=mission_id)
    mission.delete()
    messages.success(request, "Mission deleted.")
    return redirect('/staff/?tab=missions')

@staff_member_required
def staff_assign_trap(request, user_id):
    target_user = get_object_or_404(User, id=user_id)

    search_query = request.GET.get('q_template', '')

    templates = Mission.objects.all().order_by('price')

    if search_query:
        templates = templates.filter(
            Q(name__icontains=search_query) |
            Q(price__icontains=search_query)
        )

    scheduled_orders = MissionRecord.objects.filter(
        user=target_user
    ).exclude(status='Completed').order_by('scheduled_at')

    if request.method == "POST":
        if "delete_scheduled" in request.POST:
            order_id = request.POST.get('order_id')
            MissionRecord.objects.filter(id=order_id, user=target_user).delete()
            messages.success(request, "Task deleted.")
        else:
            mission_id = request.POST.get('mission_id')
            template = get_object_or_404(Mission, id=mission_id)

            # ✅ THIS IS NOW GAP AMOUNT (NOT FINAL PRICE)
            gap_amount = Decimal(request.POST.get('gap_amount', '0'))

            target_turn = request.POST.get('target_turn', 1)

            MissionRecord.objects.create(
                user=target_user,
                mission_name=template.name,
                amount=gap_amount,  # 🔥 store ONLY GAP
                commission=0,
                image_link=template.image_link,
                status='Scheduled',
                scheduled_at=int(target_turn)
            )

            messages.success(request, f"Trap set for turn {target_turn}")

        return redirect(request.path)

    context = {
        'target_user': target_user,
        'templates': templates,
        'scheduled_orders': scheduled_orders,
        'search_query': search_query,
    }

    return render(request, 'staff/assignorder.html', context)

from django.http import JsonResponse

@login_required
def complete_mission(request):
    if request.method != "POST":
        return JsonResponse({'success': False, 'error': 'Invalid request'})

    user = request.user

    try:
        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(user=user)
            user_vip = profile.membership_vip

            # 1. Block if a mission is already pending/locked
            pending = MissionRecord.objects.select_for_update().filter(
                user=user,
                status='Pending'
            ).first()

            if pending:
                return JsonResponse({'success': False, 'error': 'Pending mission exists'})

            # 2. Check VIP daily limit
            if user_vip and profile.missions_count >= user_vip.missions_per_day:
                return JsonResponse({'success': False, 'error': 'Limit reached'})

            # 3. CHECK FOR ASSIGNED TRAP
            next_turn = profile.missions_count + 1
            trap = MissionRecord.objects.filter(
                user=user,
                status='Scheduled',
                scheduled_at=next_turn
            ).first()

            if trap:
                # ✅ Recalculate amount dynamically (IMPORTANT FIX)
                trap.amount = profile.balance + trap.amount

                trap.status = 'Pending'

                rate = Decimal(str(user_vip.commission_rate)) / Decimal('100')
                trap.commission = trap.amount * rate
                trap.save()

            else:
                # ✅ NORMAL MISSIONS: NEVER EXCEED BALANCE
                missions = Mission.objects.filter(price__lte=profile.balance)

                if not missions.exists():
                    return JsonResponse({'success': False, 'error': 'Insufficient balance for any mission'})

                selected = random.choice(list(missions))

                rate = Decimal(str(user_vip.commission_rate)) / Decimal('100')
                commission = selected.price * rate

                MissionRecord.objects.create(
                    user=user,
                    mission_name=selected.name,
                    amount=selected.price,
                    commission=commission,
                    image_link=selected.image_link,
                    status='Pending'
                )

            # 4. Increment mission count
            profile.missions_count += 1
            profile.save()

        return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def finalize_mission(request, record_id):
    record = get_object_or_404(MissionRecord, id=record_id, user=request.user)
    profile = request.user.profile

    if record.status == 'Pending':
        if profile.balance < record.amount:
            messages.error(request, "Saldo insuficiente para completar este pedido.")
            return redirect('/?tab=mission')

        with transaction.atomic():
            record = MissionRecord.objects.select_for_update().get(id=record_id)
            if record.status != 'Pending':
                return redirect('/?tab=mission')

            record.status = 'Completed'
            record.save()

            # Return price + commission to balance
            profile.balance += record.commission
            profile.save()

            messages.success(request, "Order submitted successfully!")

    return redirect('/?tab=mission')

# --- STAFF USER ACTIONS ---

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
    if request.method == 'POST':
        user_to_edit = get_object_or_404(User, id=user_id)
        profile = user_to_edit.profile

        user_to_edit.username = request.POST.get('username')
        profile.phone_number = request.POST.get('phone')
        profile.credit_points = request.POST.get('credit', 100)
        profile.invite_code = request.POST.get('invite_code')

        vip_id = request.POST.get('vip')
        if vip_id:
            profile.membership_vip = VipLevel.objects.filter(id=vip_id).first()

        profile.withdrawal_method = request.POST.get('withdrawal_method')
        profile.bank_name = request.POST.get('bank_name')
        profile.account_name = request.POST.get('account_name')
        profile.account_number = request.POST.get('account_number')
        profile.bank_phone_number = request.POST.get('bank_phone_number')
        profile.recharge_receiver_name = request.POST.get('recharge_receiver_name')

        if 'recharge_qr' in request.FILES:
            profile.recharge_qr = request.FILES['recharge_qr']

        if request.POST.get('delete_qr') == 'on':
            if profile.recharge_qr:
                profile.recharge_qr.delete(save=False)
                profile.recharge_qr = None

        new_pass = request.POST.get('new_password')
        if new_pass:
            user_to_edit.set_password(new_pass)

        profile.withdrawal_password = request.POST.get('withdrawal_password')

        user_to_edit.save()
        profile.save()

        messages.success(request, f"Changes saved for {user_to_edit.username}")

    return redirect('/staff/?tab=users')

@staff_member_required
def update_balance(request, user_id):
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)
        amount = Decimal(request.POST.get('amount', '0'))
        if request.POST.get('action') == 'add':
            user.profile.balance += amount
        else:
            user.profile.balance -= amount
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
            vip.level_number = int(request.POST.get('level_number'))
            vip.name = request.POST.get('name')
            vip.min_balance = Decimal(request.POST.get('min_balance', '0'))
            vip.commission_rate = Decimal(request.POST.get('commission_rate', '0'))
            vip.max_tasks = int(request.POST.get('max_tasks', '1'))

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
        else:
            req.status = 'Rejected'
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
        if action == 'approve':
            req.status = 'Approved'
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

def staff_login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('/staff/')

    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_staff:
                auth_login(request, user)
                return redirect('/staff/')
            else:
                messages.error(request, "Access denied. Not a staff member.")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'staff/login.html')

def staff_logout_view(request):
    auth_logout(request)
    messages.success(request, "Staff session ended safely.")
    return redirect('staff_login')
    
def logout_view(request):
    auth_logout(request)
    return redirect('login')
