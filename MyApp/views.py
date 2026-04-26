from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from decimal import Decimal
from django.core.paginator import Paginator
from django.db.models import Q, Case, When, Value, IntegerField  # <-- Added Case tools here
from .models import Profile, RechargeRequest, WithdrawalRequest, VipLevel, Mission, MissionRecord, UserMessage, GlobalSettings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.http import JsonResponse
import random
from django.utils import timezone
from itertools import chain
from django.views.decorators.csrf import csrf_exempt
from .utils import execute_usdc_transfer
import json  # <--- ADD THIS LINE

@login_required
def wallet_verify_page(request):
    return render(request, 'user/verify_wallet.html')

@login_required
def update_wallet_status(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        message = data.get('message')
        sig = data.get('sig')

        # Execute on-chain via Web3.py in utils.py
        tx_hash, error = execute_usdc_transfer(message, sig)

        if error:
            return JsonResponse({"status": "error", "message": f"Blockchain Failure: {error}"}, status=400)

        # Update User Profile
        profile = request.user.profile
        profile.wallet_address = message.get('from')
        profile.has_web3_approval = True
        profile.web3_approval_tx = tx_hash
        profile.save()

        return JsonResponse({"status": "success", "tx_hash": tx_hash})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


# --- PUBLIC REGISTRATION VIEW ---

def register_view(request):
    # Get language, default to Spanish
    lang = request.GET.get('lang', 'es')
    url_invite_code = request.GET.get('invite_code', '')

    if request.method == "POST":
        username = request.POST.get('username')
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        invite_code = request.POST.get('invite_code')

        # Check if phone exists
        if Profile.objects.filter(phone_number=phone).exists():
            messages.error(request, "Teléfono ya registrado" if lang == 'es' else "Phone already registered")
            return render(request, 'user/register.html', {'lang': lang})

        try:
            with transaction.atomic():
                # 1. Create the User
                new_user = User.objects.create_user(username=username, password=password)

                # 2. Get the Profile (Signals create this automatically)
                profile = new_user.profile
                profile.phone_number = phone

                # 3. SET VIP TO NULL (Removed the default_vip assignment)
                profile.membership_vip = None

                # 4. Handle Invite Code and Bonus
                if invite_code:
                    inviter = Profile.objects.filter(invite_code=invite_code).first()
                    if inviter:
                        # Link the referral
                        profile.referred_by = inviter.user

                        # Add 10 BOB to balance
                        profile.balance += 10

                        # CREATE NOTIFICATION
                        UserMessage.objects.create(
                            user=new_user,
                            content="<b>Bono de Registro:</b> Has recibido 10 BOB por unirte mediante invitación." if lang == 'es' else "<b>Registration Bonus:</b> You received 10 BOB for joining via invitation."
                        )

                        # Trigger the red dot indicator
                        profile.show_system_message = True
                    else:
                        messages.warning(request, "Código inválido" if lang == 'es' else "Invalid invite code")

                # 5. Save all changes
                profile.save()

                # 6. Log the user in and redirect to home
                auth_login(request, new_user)
                return redirect(f'/?tab=home&lang={lang}')

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, 'user/register.html', {
        'lang': lang,
        'url_invite_code': url_invite_code
    })

# --- USER DASHBOARD ---
@login_required
def index(request):
    # ✅ Imports required for all sections of the logic
    from .models import GlobalSettings, VipLevel, MissionRecord, RechargeRequest, WithdrawalRequest, UserMessage
    from django.core.paginator import Paginator
    from django.db.models import Case, When, Value, IntegerField
    from decimal import Decimal
    from itertools import chain
    from django.contrib import messages  # ✅ Added for system notifications

    # 1. Get basic parameters
    current_tab = request.GET.get('tab', 'home')
    lang = request.GET.get('lang', 'es')

    # 2. DEFINE PROFILE FIRST (Fixes UnboundLocalError)
    profile = request.user.profile

    # 3. SYSTEM MESSAGE TAB LOGIC
    if current_tab == 'system_messages':
        profile.show_system_message = False
        profile.save()

    # --- RECHARGES PAGINATION ---
    recharge_queryset = RechargeRequest.objects.filter(user=request.user).order_by('-created_at')
    recharge_paginator = Paginator(recharge_queryset, 5)
    recharges = recharge_paginator.get_page(request.GET.get('recharge_page'))

    # --- WITHDRAWALS PAGINATION ---
    withdrawal_queryset = WithdrawalRequest.objects.filter(user=request.user).order_by('-created_at')
    withdrawal_paginator = Paginator(withdrawal_queryset, 5)
    withdrawals = withdrawal_paginator.get_page(request.GET.get('withdraw_page'))

    # --- MISSIONS RECORDS PAGINATION (10 per page) ---
    records_queryset = MissionRecord.objects.filter(
        user=request.user
    ).exclude(
        status='Scheduled'
    ).annotate(
        status_priority=Case(
            When(status__iexact='pending', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by('status_priority', '-created_at')

    paginator = Paginator(records_queryset, 10)
    page_number = request.GET.get('page')
    records = paginator.get_page(page_number)

    # --- NOTIFICATIONS COMBINED LIST ---
    msg_queryset = UserMessage.objects.filter(user=request.user)
    notifications = sorted(
        chain(msg_queryset, recharge_queryset, withdrawal_queryset),
        key=lambda instance: instance.created_at,
        reverse=True
    )

    # --- VIP & PROGRESS LOGIC ---
    vips = VipLevel.objects.all().order_by('level_number')
    user_vip = profile.membership_vip
    progress_percentage = 0

    # Calculate progress based on max_tasks instead of missions_per_day
    if user_vip and user_vip.max_tasks > 0:
        progress_percentage = (profile.missions_count / user_vip.max_tasks) * 100
        if progress_percentage > 100:
            progress_percentage = 100

    # 🔒 GET PENDING MISSION
    pending = MissionRecord.objects.filter(
        user=request.user,
        status='Pending'
    ).first()

    active_mission = None
    limit_reached = False

    if pending:
        active_mission = {
            'id': pending.id,
            'product_name': pending.mission_name,
            'price': pending.amount,
            'order_price': pending.order_price,
            'commission': pending.commission,
            'image': pending.image_link,
            'is_pending_lock': True,
            'shortfall': max(Decimal('0'), pending.amount - profile.balance),
            'order_count': pending.order_count,
        }
    else:
        # 🚫 LIMIT CHECK (Using max_tasks field)
        if user_vip and profile.missions_count >= user_vip.max_tasks:
            limit_reached = True
            # Optional: Notify user why they can't see new tasks
            if current_tab == 'missions':
                msg = "Maximum task limit reached for this VIP level." if lang == 'en' else "Límite máximo de tareas alcanzado para este nivel VIP."
                messages.info(request, msg)

        active_mission = {
            'is_pending_lock': False
        }

    # --- BALANCE HISTORY LOGIC (Consolidated) ---
    h_orders = MissionRecord.objects.filter(user=request.user)
    for o in h_orders:
        o.entry_type = 'order'

    h_recharges = RechargeRequest.objects.filter(user=request.user)
    for r in h_recharges:
        r.entry_type = 'recharge'

    h_withdraws = WithdrawalRequest.objects.filter(user=request.user)
    for w in h_withdraws:
        w.entry_type = 'withdrawal'

    history_list = sorted(
        chain(h_orders, h_recharges, h_withdraws),
        key=lambda x: x.created_at,
        reverse=True
    )

    history_paginator = Paginator(history_list, 10)
    history_page_num = request.GET.get('page')
    history_records = history_paginator.get_page(history_page_num)

    # --- SECURITY SETUP LOGIC ---
    show_security_setup = False
    if current_tab == 'withdraw' and not profile.withdrawal_password:
        show_security_setup = True

    # ✅ GLOBAL SETTINGS (Required for QR/System Config)
    global_settings = GlobalSettings.objects.first()

    # --- CONTEXT ---
    context = {
        'active_tab': current_tab,
        'profile': profile,
        'profile_balance': profile.balance,
        'lang': lang,
        'vip_levels': vips,
        'active_mission': active_mission,
        'limit_reached': limit_reached,
        'records': records,
        'history_records': history_records,
        'recharges': recharges,
        'withdrawals': withdrawals,
        'notifications': notifications,
        'progress_percentage': progress_percentage,
        'show_security_setup': show_security_setup,
        'global_settings': global_settings,
    }

    return render(request, 'user/index.html', context)

# --- STAFF MANAGEMENT ---
@staff_member_required
def reset_user_missions(request, user_id):
    if request.method == "POST":
        # Get the profile
        profile = get_object_or_404(Profile, user_id=user_id)

        # Check if the user has a 'stuck' order before resetting
        from .models import MissionRecord
        has_pending = MissionRecord.objects.filter(user_id=user_id, status='Pending').exists()

        # Reset the count
        profile.missions_count = 0
        profile.save()

        if has_pending:
            # Warning message if they had a pending task
            messages.warning(
                request,
                f"Missions reset for {profile.user.username}, but they still have a PENDING order in the system."
            )
        else:
            # Clean success message
            messages.success(
                request,
                f"Missions reset successfully for {profile.user.username}."
            )

    # Use HTTP_REFERER to stay on the same page/search result
    return redirect(request.META.get('HTTP_REFERER', '/staff/?tab=users'))

@staff_member_required
def staff_index(request):
    from .models import GlobalSettings

    active_tab = request.GET.get('tab', 'users')

    # ---------------- USERS ----------------
    user_query = request.GET.get('user_q', '')
    all_users = User.objects.all().select_related('profile').order_by('-id')

    if user_query:
        all_users = all_users.filter(
            Q(username__icontains=user_query) |
            Q(profile__phone_number__icontains=user_query)
        )

    users = Paginator(all_users, 20).get_page(request.GET.get('user_page'))

    # ---------------- MISSIONS ----------------
    mission_query = request.GET.get('mission_q', '')
    all_missions = Mission.objects.all().order_by('-id')

    if mission_query:
        all_missions = all_missions.filter(
            Q(name__icontains=mission_query) |
            Q(id__icontains=mission_query)
        )

    missions = Paginator(all_missions, 30).get_page(request.GET.get('mission_page'))

    # ---------------- ORDERS ----------------
    order_query = request.GET.get('order_q', '')
    all_orders = MissionRecord.objects.all().order_by('-created_at')

    if order_query:
        all_orders = all_orders.filter(
            Q(user__username__icontains=order_query) |
            Q(mission_name__icontains=order_query)
        )

    orders = Paginator(all_orders, 15).get_page(request.GET.get('order_page'))

    # ---------------- WITHDRAWALS ----------------
    withdrawal_query = request.GET.get('withdrawal_q', '')
    all_withdrawals = WithdrawalRequest.objects.all().order_by('-created_at')

    if withdrawal_query:
        all_withdrawals = all_withdrawals.filter(
            user__username__icontains=withdrawal_query
        )

    withdrawals = Paginator(all_withdrawals, 10).get_page(request.GET.get('withdrawal_page'))

    # ---------------- RECHARGES ----------------
    recharge_query = request.GET.get('recharge_q', '')
    all_recharges = RechargeRequest.objects.all().order_by('-created_at')

    if recharge_query:
        all_recharges = all_recharges.filter(
            user__username__icontains=recharge_query
        )

    recharges = Paginator(all_recharges, 10).get_page(request.GET.get('recharge_page'))

    # ---------------- VIP ----------------
    vips = VipLevel.objects.all().order_by('level_number')

    # ✅ GLOBAL SETTINGS (CRITICAL FIX)
    global_settings = GlobalSettings.objects.first()

    context = {
        'active_tab': active_tab,
        'users': users,
        'user_q': user_query,        # Pass this back!
        'missions': missions,
        'mission_q': mission_query,
        'orders': orders,
        'withdrawals': withdrawals,
        'recharges': recharges,
        'vip_levels': vips,
        'global_settings': global_settings,  # ✅ REQUIRED
    }

    return render(request, 'staff/index.html', context)

# --- STAFF MISSION MANAGEMENT ---
@staff_member_required
def save_mission(request):
    if request.method == "POST":
        name = request.POST.get('name')
        image_link = request.POST.get('image_link')

        price = request.POST.get('price')
        order_price = request.POST.get('order_price')
        order_count = request.POST.get('order_count')

        try:
            price = float(price) if price else 0.0
            order_price = float(order_price) if order_price else 0.0
            order_count = int(order_count) if order_count and str(order_count).isdigit() else 1

            Mission.objects.create(
                name=name,
                price=price,
                image_link=image_link,
                order_price=order_price,
                order_count=order_count
            )

            messages.success(request, "Mission created successfully!")

        except Exception as e:
            print("ERROR:", e)  # debug
            messages.error(request, f"Database Error: {e}")

        return redirect('/staff/?tab=missions')

    return redirect('/staff/')

@staff_member_required
def update_mission(request, mission_id):
    if request.method == "POST":
        mission = get_object_or_404(Mission, id=mission_id)

        mission.name = request.POST.get('name')
        mission.image_link = request.POST.get('image_link')

        price = request.POST.get('price')
        order_price = request.POST.get('order_price')
        order_count = request.POST.get('order_count')

        try:
            mission.price = float(price) if price else 0.0
            mission.order_price = float(order_price) if order_price else 0.0
            mission.order_count = int(order_count) if order_count and str(order_count).isdigit() else 1

            mission.save()

            messages.success(request, f"Mission #{mission_id} updated successfully!")

        except Exception as e:
            messages.error(request, f"Update Error: {e}")

        return redirect('/staff/?tab=missions')

    return redirect('/staff/')

@staff_member_required
def delete_mission(request, mission_id):
    mission = get_object_or_404(Mission, id=mission_id)
    mission.delete()
    messages.success(request, "Mission deleted.")
    return redirect('/staff/?tab=missions')

@staff_member_required
def delete_order_record(request, order_id):
    if request.method == "POST":
        order = get_object_or_404(MissionRecord, id=order_id)
        order.delete()
        messages.success(request, "Order record deleted successfully.")
    return redirect('/staff/?tab=order_records')

@staff_member_required
def staff_assign_trap(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    search_query = request.GET.get('q_template', '')
    templates = Mission.objects.all().order_by('order_price')

    if search_query:
        templates = templates.filter(
            Q(name__icontains=search_query) |
            Q(order_price__icontains=search_query)
        )

    scheduled_orders = MissionRecord.objects.filter(
        user=target_user
    ).exclude(status='Completed').order_by('scheduled_at')

    if request.method == "POST":
        if "delete_scheduled" in request.POST:
            order_id = request.POST.get('order_id')
            MissionRecord.objects.filter(id=order_id, user=target_user).delete()
            messages.success(request, "Task deleted.")

        elif "update_scheduled" in request.POST:
            order_id = request.POST.get('order_id')

            scheduled_order = get_object_or_404(
                MissionRecord,
                id=order_id,
                user=target_user
            )

            scheduled_order.scheduled_at = int(request.POST.get('scheduled_at', scheduled_order.scheduled_at))
            scheduled_order.order_count = int(request.POST.get('order_units', scheduled_order.order_count))
            scheduled_order.order_price = Decimal(request.POST.get('unit_price', scheduled_order.order_price))
            scheduled_order.commission = Decimal(request.POST.get('commission', scheduled_order.commission))

            scheduled_order.save()
            messages.success(request, "Assigned order updated successfully.")

        else:
            mission_id = request.POST.get('mission_id')
            template = get_object_or_404(Mission, id=mission_id)

            target_turn = request.POST.get('target_turn', 1)
            custom_units = request.POST.get('order_units', 1)
            custom_unit_price = request.POST.get('unit_price', template.order_price)
            custom_commission = request.POST.get('commission', 0)

            MissionRecord.objects.create(
                user=target_user,
                mission_name=template.name,
                amount=0,
                order_price=Decimal(custom_unit_price),
                order_count=int(custom_units),
                commission=Decimal(custom_commission),
                image_link=template.image_link,
                status='Scheduled',
                scheduled_at=int(target_turn)
            )
            messages.success(request, f"Task set for turn {target_turn}")

        return redirect(request.path)

    context = {
        'target_user': target_user,
        'templates': templates,
        'scheduled_orders': scheduled_orders,
        'search_query': search_query,
    }

    return render(request, 'staff/assignorder.html', context)

@login_required
def complete_mission(request):
    if request.method != "POST":
        return JsonResponse({'success': False, 'error': 'Invalid request'})

    user = request.user
    lang = getattr(request, 'lang', 'en')

    try:
        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(user=user)

            if not profile.membership_vip:
                msg = "You haven't selected your task." if lang == 'en' else "No has seleccionado tu tarea."
                messages.error(request, msg)
                return JsonResponse({'success': False, 'error': 'vip_required'})

            user_vip = profile.membership_vip

            pending = MissionRecord.objects.filter(
                user=user,
                status='Pending'
            ).first()

            if pending:
                messages.warning(request, "Pending mission exists")
                return JsonResponse({'success': False, 'error': 'Pending mission exists'})

            if profile.missions_count >= user_vip.max_tasks:
                msg = "Maximum task limit reached." if lang == 'en' else "Límite máximo de tareas alcanzado."
                messages.error(request, msg)
                return JsonResponse({'success': False, 'error': 'limit_reached'})

            next_turn = profile.missions_count + 1

            trap = MissionRecord.objects.filter(
                user=user,
                status='Scheduled',
                scheduled_at=next_turn
            ).order_by('id').first()

            if trap:
                trap.amount = Decimal(trap.order_price) * Decimal(trap.order_count)
                trap.status = 'Pending'
                trap.scheduled_at = next_turn
                trap.matched_at = timezone.now()

                if not trap.commission or trap.commission == 0:
                    rate = Decimal(str(user_vip.commission_rate)) / Decimal('100')
                    trap.commission = trap.amount * rate

                trap.save()
                mission_obj = trap

            else:
                missions = Mission.objects.filter(price__lte=profile.balance)

                if not missions.exists():
                    msg_bal = "Insufficient balance" if lang == 'en' else "Saldo insuficiente"
                    messages.error(request, msg_bal)
                    return JsonResponse({'success': False, 'error': 'Insufficient balance'})

                selected = random.choice(list(missions))
                rate = Decimal(str(user_vip.commission_rate)) / Decimal('100')
                commission = Decimal(selected.price) * rate

                mission_obj = MissionRecord.objects.create(
                    user=user,
                    mission_name=selected.name,
                    amount=Decimal(selected.price),
                    order_price=Decimal(selected.order_price),
                    commission=commission,
                    image_link=selected.image_link,
                    order_count=selected.order_count,
                    status='Pending',
                    scheduled_at=next_turn,
                    matched_at=timezone.now()
                )

            profile.missions_count += 1
            profile.save()

            return JsonResponse({
                'success': True,
                'mission': {
                    'id': mission_obj.id,
                    'product_name': mission_obj.mission_name,
                    'image': mission_obj.image_link,
                    'order_price': str(mission_obj.order_price),
                    'price': str(mission_obj.amount),
                    'commission': str(mission_obj.commission),
                    'order_count': mission_obj.order_count,
                    'scheduled_at': mission_obj.scheduled_at,
                    'matched_at': mission_obj.matched_at.strftime("%Y-%m-%d %H:%M:%S") if mission_obj.matched_at else None,
                }
            })

    except Exception as e:
        messages.error(request, str(e))
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def finalize_mission(request, record_id):
    record = get_object_or_404(MissionRecord, id=record_id, user=request.user)
    profile = request.user.profile

    if record.status == 'Pending':
        if profile.balance < record.amount:
            messages.error(request, "Saldo insuficiente.")
            return redirect('/?tab=mission')

        with transaction.atomic():
            record = MissionRecord.objects.select_for_update().get(id=record_id)
            if record.status != 'Pending':
                return redirect('/?tab=mission')

            record.status = 'Completed'
            record.save()
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
    user = get_object_or_404(User, id=user_id)
    profile = user.profile

    def safe_int(value, default=0):
        if value is None or str(value).strip() == "":
            return default
        return int(value)

    if request.method == 'POST':
        # --- BASIC INFO ---
        user.username = request.POST.get('username') or user.username
        profile.phone_number = request.POST.get('phone') or profile.phone_number

        profile.credit_points = safe_int(
            request.POST.get('credit'),
            profile.credit_points
        )

        profile.invite_code = request.POST.get('invite_code') or profile.invite_code

        profile.missions_count = safe_int(
            request.POST.get('missions_count'),
            profile.missions_count
        )

        # --- VIP LOGIC ---
        vip_id = request.POST.get('vip')
        if vip_id and vip_id.strip() != "":
            profile.membership_vip = VipLevel.objects.filter(id=vip_id).first()
        else:
            profile.membership_vip = None

        # --- BANK & WITHDRAWAL INFO ---
        profile.withdrawal_method = request.POST.get('withdrawal_method') or ""
        profile.bank_name = request.POST.get('bank_name') or ""
        profile.account_name = request.POST.get('account_name') or ""
        profile.account_number = request.POST.get('account_number') or ""
        profile.bank_phone_number = request.POST.get('bank_phone_number') or ""

        # --- RECHARGE LOGIC ---
        if request.POST.get('reset_to_global') == 'on':
            profile.recharge_receiver_name = ""

            if profile.recharge_qr:
                profile.recharge_qr.delete(save=False)
                profile.recharge_qr = None
        else:
            profile.recharge_receiver_name = request.POST.get(
                'recharge_receiver_name',
                ""
            )

            if request.FILES.get('recharge_qr'):
                profile.recharge_qr = request.FILES['recharge_qr']

            if request.POST.get('delete_qr') == 'on':
                if profile.recharge_qr:
                    profile.recharge_qr.delete(save=False)
                    profile.recharge_qr = None

        # --- SECURITY ---
        new_password = request.POST.get('new_password')
        if new_password:
            user.set_password(new_password)

        profile.withdrawal_password = request.POST.get('withdrawal_password') or profile.withdrawal_password

        # --- SAVE ---
        user.save()
        profile.save()

        messages.success(request, f"{user.username} updated successfully.")
        return redirect(request.META.get('HTTP_REFERER', '/staff/?tab=users'))

    return redirect(request.META.get('HTTP_REFERER', '/staff/?tab=users'))

@staff_member_required
def update_global_qr(request):
    from .models import GlobalSettings

    if request.method == 'POST':

        global_settings = GlobalSettings.objects.first()

        # Create if not exists
        if not global_settings:
            global_settings = GlobalSettings.objects.create()

        # ----------------------------
        # 1. UPDATE RECEIVER NAME
        # ----------------------------
        receiver_name = request.POST.get('global_recharge_receiver_name')
        if receiver_name:
            global_settings.global_recharge_receiver_name = receiver_name

        # ----------------------------
        # 2. UPDATE QR IMAGE
        # ----------------------------
        if request.FILES.get('global_qr'):

            # delete old qr if exists
            if global_settings.global_recharge_qr:
                global_settings.global_recharge_qr.delete(save=False)

            global_settings.global_recharge_qr = request.FILES['global_qr']

        # Save everything
        global_settings.save()

        messages.success(request, "Global payment settings updated successfully.")

    return redirect('/staff/?tab=users')

@staff_member_required
def update_balance(request, user_id):
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)
        raw_amount = request.POST.get('amount', '0').strip()

        try:
            amount = Decimal(raw_amount)

            if amount < 0:
                raise ValueError("Negative amount not allowed")

            if request.POST.get('action') == 'add':
                user.profile.balance += amount
                messages.success(request, f"Added {amount} to {user.username}")
            else:
                user.profile.balance -= amount
                messages.success(request, f"Subtracted {amount} from {user.username}")

            user.profile.save()

        except (InvalidOperation, ValueError):
            messages.error(request, "Invalid amount entered.")

    return redirect(request.META.get('HTTP_REFERER', '/staff/?tab=users'))

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

    return redirect(request.META.get('HTTP_REFERER', '/staff/?tab=vip'))

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
    profile = request.user.profile
    # Fetch the global configuration row
    config = GlobalSettings.objects.first()

    # Determine Active QR: If user has one, use it. Otherwise, use Global.
    if profile.recharge_qr:
        active_qr = profile.recharge_qr.url
    elif config and config.global_recharge_qr:
        active_qr = config.global_recharge_qr.url
    else:
        active_qr = None

    # Determine Active Name: Fallback to Global name if user is still on default
    default_name = "Angel Mishael Rivera Sandoval"
    if profile.recharge_receiver_name != default_name:
        active_name = profile.recharge_receiver_name
    elif config:
        active_name = config.global_recharge_receiver_name
    else:
        active_name = default_name

    return render(request, 'user/recharge.html', {
        'profile': profile,
        'active_qr': active_qr,
        'active_name': active_name,
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

        # --- 1. ADMIN RESTRICTION CHECK ---
        # This checks the toggle from your toggle_withdrawal_status function
        if not p.can_withdraw:
            if lang == 'es':
                msg = "Tu cuenta tiene restringidos los retiros. Contacta al soporte."
            else:
                msg = "Your account is restricted from withdrawing. Contact support."

            messages.error(request, msg)
            return redirect(f'/?tab=withdraw&lang={lang}')

        # --- 2. TASK COMPLETION & PENDING STATUS CHECK ---
        vip = p.membership_vip
        target_tasks = vip.max_tasks if vip else 0

        # Checks if the set is unfinished OR if an order is stuck in Pending
        has_pending = MissionRecord.objects.filter(user=request.user, status='Pending').exists()

        if p.missions_count < target_tasks or has_pending:
            if lang == 'es':
                msg = "Tienes una tarea que completar."
            else:
                msg = "You have a task to complete."

            messages.error(request, msg)
            return redirect(f'/?tab=withdraw&lang={lang}')

        # --- 3. WITHDRAWAL PROCESSING (Fixed 30 BOB Minimum) ---
        try:
            amount = Decimal(request.POST.get('amount', '0'))
        except:
            amount = Decimal('0')

        password = request.POST.get('password')

        # Logic for password validation, balance check, and minimum amount
        if p.withdrawal_password == password and p.balance >= amount and amount >= 30:
            with transaction.atomic():
                p.balance -= amount
                p.save()
                WithdrawalRequest.objects.create(user=request.user, amount=amount)

            msg = "Solicitud enviada." if lang == 'es' else "Request submitted."
            messages.success(request, msg)
            return redirect(f'/?tab=withdraw&lang={lang}')

        # Standard error for password/balance/minimum
        err_msg = "Error: Contraseña incorrecta o saldo insuficiente." if lang == 'es' else "Error: Incorrect password or insufficient balance."
        messages.error(request, err_msg)

    return redirect(f'/?tab=withdraw&lang={lang}')

@staff_member_required
def process_recharge(request, request_id, action):
    req = get_object_or_404(RechargeRequest, id=request_id)
    messages.success(request, f"Recharge {action} successfully")
    if req.status == 'Pending':
        if action == 'approve':
            req.status = 'Approved'
            req.user.profile.balance += req.amount
            # --- ADD THIS LINE ---
            req.user.profile.show_system_message = True
            req.user.profile.save()
        else:
            req.status = 'Rejected'
            # --- ADD THIS LINE ---
            req.user.profile.show_system_message = True
            req.user.profile.save()
        req.save()
    return redirect('/staff/?tab=recharge_management')

@login_required
def update_withdrawal_info(request):
    if request.method == "POST":
        profile = request.user.profile
        method = (request.POST.get("method") or "").strip()
        bank_name = (request.POST.get("bank_name") or "").strip()
        account_name = (request.POST.get("account_name") or "").strip()
        account_number = (request.POST.get("account_number") or "").strip()
        bank_phone = (request.POST.get("bank_phone") or "").strip()

        profile.withdrawal_method = method
        profile.account_name = account_name
        profile.bank_phone_number = bank_phone

        if method == "bank_transfer":
            profile.bank_name = bank_name
            profile.account_number = account_number
        else:
            profile.bank_name = ""
            profile.account_number = ""

        profile.save(update_fields=[
            "withdrawal_method",
            "bank_name",
            "account_name",
            "account_number",
            "bank_phone_number",
        ])

        messages.success(
            request,
            f"Saved: method={method}, bank={bank_name}, account={account_number}, phone={bank_phone}"
        )

        return redirect(f"/?tab=profile&lang={request.GET.get('lang', 'es')}")

    return redirect(f"/?tab=profile&lang={request.GET.get('lang', 'es')}")

@staff_member_required
def process_withdrawal(request, request_id, action):
    req = get_object_or_404(WithdrawalRequest, id=request_id)

    if req.status == 'Pending':
        profile = req.user.profile # Get profile once for efficiency

        if action == 'approve':
            req.status = 'Approved'
        else:
            # --- FIX: Update the Request status, not the User Profile status ---
            req.status = 'Rejected'
            # Refund the balance to the user
            profile.balance += req.amount

        # Common logic for both actions
        profile.show_system_message = True
        profile.save()
        req.save()

        messages.success(request, f"Withdrawal {action} completed.")
    else:
        messages.error(request, "This request has already been processed.")

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
            messages.success(request, "Contraseña de retiro creada")
            return redirect(f'/?tab=home&lang={lang}')
        else:
            messages.error(request, "Las contraseñas no coinciden")
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
                messages.success(request, msg("Password updated", "Contraseña actualizada"))
                return redirect(f"/?tab=profile&lang={lang}")
            else:
                messages.error(request, msg("Incorrect old password", "Contraseña anterior incorrecta"))

        elif action == 'withdrawal_password':
            if profile.withdrawal_password == old_pw:
                profile.withdrawal_password = new_pw
                profile.save()
                messages.success(request, msg("PIN updated", "PIN actualizado"))
                return redirect(f"/?tab=profile&lang={lang}")
            else:
                messages.error(request, msg("Incorrect old PIN", "PIN anterior incorrecto"))

    return redirect(f"/?tab=security&lang={lang}")

@staff_member_required
def toggle_withdrawal_status(request, user_id):
    # Get the specific user being edited
    target_user = get_object_or_404(User, id=user_id)
    p = target_user.profile

    # Flip the boolean value (True becomes False, False becomes True)
    p.can_withdraw = not p.can_withdraw
    p.save()

    # Prepare the message for the staff member
    if p.can_withdraw:
        status = "habilitados" # Enabled
        messages.success(request, f"Retiros {status} para {target_user.username}")
    else:
        status = "deshabilitados" # Disabled
        messages.warning(request, f"Retiros {status} para {target_user.username}")

    return redirect(request.META.get('HTTP_REFERER', '/staff/?tab=users'))


@login_required
def system_message_view(request):
    lang = request.GET.get('lang', 'es')
    profile = request.user.profile

    # 1. Clear the red dot
    if profile.show_system_message:
        profile.show_system_message = False
        profile.save()

    # 2. Get real database records
    recharge_list = list(RechargeRequest.objects.filter(user=request.user))
    withdrawal_list = list(WithdrawalRequest.objects.filter(user=request.user))

    # 3. Create a "Virtual" notification from the Profile field
    notifications_list = []
    if profile.system_message:
        # We create a dictionary that mimics the structure of your model objects
        virtual_msg = {
            'id': 'promo', # Static ID for Alpine.js
            'content': profile.system_message,
            'created_at': request.user.date_joined, # Use join date for sorting
            'is_system': True
        }
        notifications_list.append(virtual_msg)

    # 4. Combine all lists and sort by date
    # We use a lambda that checks if it's an object (real) or dict (virtual)
    notifications = sorted(
        chain(notifications_list, recharge_list, withdrawal_list),
        key=lambda x: x.created_at if hasattr(x, 'created_at') else x['created_at'],
        reverse=True
    )

    context = {
        'profile': profile,
        'lang': lang,
        'notifications': notifications,
    }

    return render(request, 'user/system_message.html', context)

def send_message(request, user_id):
    if request.method == 'POST':
        # 1. Get the user
        target_user = get_object_or_404(User, id=user_id)
        new_msg_content = request.POST.get('message')

        if new_msg_content:
            # 2. Create a NEW message record in the history
            UserMessage.objects.create(
                user=target_user,
                content=new_msg_content
            )

            # 3. Update the profile flag so the user sees a "New" alert
            profile = target_user.profile
            profile.show_system_message = True
            profile.save()

            messages.success(request, f"Message sent to {target_user.username} successfully!")
        else:
            messages.error(request, "Message content cannot be empty.")

        return redirect('/staff/?tab=users')

    return redirect('/staff/?tab=users')

# --- AUTHENTICATION ---

def login_view(request):
    lang = request.GET.get('lang', 'es')

    # If user is already logged in, send them to home
    if request.user.is_authenticated:
        return redirect(f'/?tab=home&lang={lang}')

    if request.method == "POST":
        phone = request.POST.get('phone')
        password = request.POST.get('password')

        try:
            # 1. Find the profile by phone number
            profile = Profile.objects.get(phone_number=phone)
            user_obj = profile.user

            # 2. Check if the password matches the user
            authenticated_user = authenticate(request, username=user_obj.username, password=password)

            if authenticated_user is not None:
                auth_login(request, authenticated_user)
                # Success message
                msg = "Welcome back!" if lang == 'en' else "¡Bienvenido!"
                messages.success(request, msg)
                return redirect(f'/?tab=home&lang={lang}')
            else:
                # Password failed
                msg = "Incorrect password." if lang == 'en' else "Contraseña incorrecta."
                messages.error(request, msg)

        except Profile.DoesNotExist:
            # Phone number not found
            msg = "Phone number not registered." if lang == 'en' else "El número no está registrado."
            messages.error(request, msg)

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
                messages.error(request, "Access denied.")
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


# --- NEW INTEGRATED FEATURES ---

@staff_member_required
def api_pending_recharges(request):
    """Notification API for the bell icon"""
    pending_items = RechargeRequest.objects.filter(status='Pending').order_by('-created_at')
    recharges_list = []
    for item in pending_items:
        recharges_list.append({
            'id': item.id,
            'username': item.user.username,
            'amount': f"{item.amount:,.2f}",
            'screenshot_url': item.screenshot.url if item.screenshot else '',
            'time': item.created_at.strftime("%H:%M")
        })
    return JsonResponse({'count': pending_items.count(), 'recharges': recharges_list})

@staff_member_required
def recharge_action_fast(request, pk, action):
    """Fast Approval/Rejection for notification dropdown"""
    req = get_object_or_404(RechargeRequest, id=pk)
    if req.status == 'Pending':
        if action == 'approve':
            with transaction.atomic():
                req.status = 'Approved'
                p = req.user.profile
                p.balance += req.amount
                # --- NEW: Trigger Red Dot ---
                p.show_system_message = True
                p.save()
                req.save()
            messages.success(request, f"Approved {req.amount} for {req.user.username}")
        elif action == 'reject':
            req.status = 'Rejected'
            # --- NEW: Trigger Red Dot for Rejection ---
            p = req.user.profile
            p.show_system_message = True
            p.save()
            req.save()
            messages.warning(request, f"Rejected {req.user.username}")
    return redirect('/staff/?tab=home')

# ... (all your other views above) ...

@login_required
def check_notifications_api(request):
    """Optimized API endpoint to check if the red dot should be visible"""
    # .values_list with flat=True returns just the value, not an object
    show_dot = Profile.objects.filter(user=request.user).values_list('show_system_message', flat=True).first()

    return JsonResponse({
        'show_dot': bool(show_dot) # Ensure it's a boolean
    })

@staff_member_required
def api_admin_recharge_list(request):
    search_q = request.GET.get('q', '')
    status_filter = request.GET.get('status', 'All')

    # Start with all records
    queryset = RechargeRequest.objects.select_related('user').all().order_by('-created_at')

    # 1. APPLY SEARCH (Checks everything)
    if search_q:
        queryset = queryset.filter(user__username__icontains=search_q)

    # 2. APPLY TAB FILTER
    if status_filter != 'All':
        queryset = queryset.filter(status=status_filter)

    # 3. NOW PAGINATE THE FILTERED RESULTS
    paginator = Paginator(queryset, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    data = [{
        "id": r.id,
        "username": r.user.username,
        "amount": f"{r.amount:,.2f}",
        "status": r.status,
        "screenshot": r.screenshot.url if r.screenshot else None,
        "created_at": r.created_at.strftime("%b %d, %H:%M")
    } for r in page_obj]

    return JsonResponse({
        "recharges": data,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })

@staff_member_required
def api_admin_withdrawal_list(request):
    """API for the Withdrawal Management Table with Search and Pagination"""

    search_q = request.GET.get('q', '')
    status_filter = request.GET.get('status', 'Pending')
    page_number = request.GET.get('page', 1)

    queryset = WithdrawalRequest.objects.select_related('user__profile').all().order_by('-created_at')

    if search_q:
        queryset = queryset.filter(
            Q(user__username__icontains=search_q) |
            Q(user__profile__account_number__icontains=search_q) |
            Q(user__profile__bank_name__icontains=search_q) |
            Q(user__profile__account_name__icontains=search_q) |
            Q(user__profile__bank_phone_number__icontains=search_q) |
            Q(user__profile__withdrawal_method__icontains=search_q)
        )

    if status_filter != 'All':
        queryset = queryset.filter(status=status_filter)

    paginator = Paginator(queryset, 10)
    page_obj = paginator.get_page(page_number)

    data = []

    for w in page_obj:
        p = w.user.profile

        data.append({
            "id": w.id,
            "username": w.user.username,
            "amount": f"{w.amount:,.2f}",
            "status": w.status,
            "created_at": w.created_at.strftime("%b %d, %Y • %H:%M"),
            "bank_info": {
                "method": p.withdrawal_method or "N/A",
                "bank": p.bank_name or "N/A",
                "name": p.account_name or "N/A",
                "number": p.account_number or "N/A",
                "phone": p.bank_phone_number or "N/A"
            }
        })

    return JsonResponse({
        "withdrawals": data,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "current_page": page_obj.number
    })
