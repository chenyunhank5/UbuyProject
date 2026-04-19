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

                # 3. Assign the first VIP level by default
                default_vip = VipLevel.objects.order_by('level_number').first()
                if default_vip:
                    profile.membership_vip = default_vip

                # 4. Handle Invite Code and Bonus
                if invite_code:
                    inviter = Profile.objects.filter(invite_code=invite_code).first()
                    if inviter:
                        # Link the referral
                        profile.referred_by = inviter.user

                        # Add 10 BOB to balance
                        profile.balance += 10

                        # CREATE NOTIFICATION IN EXISTING UserMessage MODEL
                        # We use 'content' because that is the field in your model
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
        'url_invite_code': url_invite_code # Pass it to the template
    })

# --- USER DASHBOARD ---
@login_required
def index(request):
    # ✅ ADDED: import inside function (safe if you forgot at top)
    from .models import GlobalSettings

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
    user_vip = profile.membership_vip
    progress_percentage = 0
    if user_vip and user_vip.missions_per_day > 0:
        progress_percentage = (profile.missions_count / user_vip.missions_per_day) * 100

    vips = VipLevel.objects.all().order_by('level_number')

    # 🔒 GET PENDING MISSION
    pending = MissionRecord.objects.filter(
        user=request.user,
        status='Pending'
    ).first()

    active_mission = None
    limit_reached = False

    if pending:
        # ✅ Check if 'pending' (MissionRecord model) actually has order_price
        active_mission = {
            'id': pending.id,
            'product_name': pending.mission_name,
            'price': pending.amount,
            'order_price': pending.order_price, # <--- Ensure this field exists in MissionRecord model
            'commission': pending.commission,
            'image': pending.image_link,
            'is_pending_lock': True,
            'shortfall': max(Decimal('0'), pending.amount - profile.balance),
            'order_count': pending.order_count,
        }
    else:
        # 🚫 LIMIT CHECK
        if user_vip and profile.missions_count >= user_vip.missions_per_day:
            limit_reached = True

        active_mission = {
            'is_pending_lock': False
        }

    # --- NEW: COMBINED BALANCE HISTORY LOGIC ---

    # 1. Orders
    h_orders = MissionRecord.objects.filter(user=request.user)
    for o in h_orders:
        o.entry_type = 'order'

    # 2. Recharges
    h_recharges = RechargeRequest.objects.filter(user=request.user)
    for r in h_recharges:
        r.entry_type = 'recharge'

    # 3. Withdrawals
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

    # ✅ ✅ ADDED: GET GLOBAL SETTINGS (THIS FIXES YOUR QR ISSUE)
    global_settings = GlobalSettings.objects.first()

    # --- CONTEXT ---
    context = {
        'active_tab': current_tab,
        'profile': profile,
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
        user_profile = get_object_or_404(Profile, user_id=user_id)
        user_profile.missions_count = 0
        user_profile.save()
        messages.success(request, f"Missions reset for {user_profile.user.username}")
    return redirect('/staff/?tab=users')

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
        'missions': missions,
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
        else:
            mission_id = request.POST.get('mission_id')
            template = get_object_or_404(Mission, id=mission_id)

            # Manual inputs from your new HTML form
            target_turn = request.POST.get('target_turn', 1)
            custom_units = request.POST.get('order_units', 1)
            custom_unit_price = request.POST.get('unit_price', template.order_price)
            custom_commission = request.POST.get('commission', 0)

            MissionRecord.objects.create(
                user=target_user,
                mission_name=template.name,
                amount=0, # Gap amount removed as per your request
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
    # Using your original template name to fix the TemplateDoesNotExist error
    return render(request, 'staff/assignorder.html', context)

@login_required
def complete_mission(request):
    if request.method != "POST":
        return JsonResponse({'success': False, 'error': 'Invalid request'})

    user = request.user
    try:
        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(user=user)
            user_vip = profile.membership_vip

            # Check for existing pending tasks
            pending = MissionRecord.objects.filter(user=user, status='Pending').first()
            if pending:
                return JsonResponse({'success': False, 'error': 'Pending mission exists'})

            next_turn = profile.missions_count + 1

            # 1. Check if there is a "Trap" scheduled
            trap = MissionRecord.objects.filter(
                user=user,
                status='Scheduled',
                scheduled_at=next_turn
            ).first()

            if trap:
                # IMPORTANT: Find the template to get the correct order_price
                template = Mission.objects.filter(name=trap.mission_name).first()

                trap.amount = profile.balance + trap.amount
                trap.status = 'Pending'

                # Copy values from template to the Record
                if template:
                    trap.order_price = template.order_price
                    trap.order_count = template.order_count

                rate = Decimal(str(user_vip.commission_rate)) / Decimal('100')
                trap.commission = trap.amount * rate
                trap.save()

                mission_obj = trap # Use this for the response
            else:
                # 2. Random Match Logic
                missions = Mission.objects.filter(price__lte=profile.balance)
                if not missions.exists():
                    return JsonResponse({'success': False, 'error': 'Insufficient balance'})

                selected = random.choice(list(missions))
                rate = Decimal(str(user_vip.commission_rate)) / Decimal('100')
                commission = selected.price * rate

                # Create the record and EXPLICITLY save order_price
                mission_obj = MissionRecord.objects.create(
                    user=user,
                    mission_name=selected.name,
                    amount=selected.price,
                    order_price=selected.order_price, # <--- THIS SAVES IT TO DB
                    commission=commission,
                    image_link=selected.image_link,
                    order_count=selected.order_count,
                    status='Pending'
                )

            profile.missions_count += 1
            profile.save()

            # Return the data to your JavaScript
            return JsonResponse({
                'success': True,
                'mission': {
                    'product_name': mission_obj.mission_name,
                    'image': mission_obj.image_link,
                    'order_price': str(mission_obj.order_price),
                    'price': str(mission_obj.amount),
                    'commission': str(mission_obj.commission),
                    'order_count': mission_obj.order_count
                }
            })

    except Exception as e:
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

    if request.method == 'POST':
        user.username = request.POST.get('username')
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

        # --- RECHARGE LOGIC (ENHANCED) ---

        # Check if the "Reset to Global" checkbox was ticked
        if request.POST.get('reset_to_global') == 'on':
            # 1. Wipe the custom name
            profile.recharge_receiver_name = ""
            # 2. Delete the custom QR file if it exists
            if profile.recharge_qr:
                profile.recharge_qr.delete(save=False)
                profile.recharge_qr = None
        else:
            # Normal behavior: Update name if provided
            profile.recharge_receiver_name = request.POST.get('recharge_receiver_name', "")

            # QR upload (Only if not resetting)
            if request.FILES.get('recharge_qr'):
                profile.recharge_qr = request.FILES['recharge_qr']

            # Individual QR Delete logic (your original code)
            if request.POST.get('delete_qr') == 'on':
                if profile.recharge_qr:
                    profile.recharge_qr.delete(save=False)
                    profile.recharge_qr = None

        # --- END RECHARGE LOGIC ---

        # Password
        if request.POST.get('new_password'):
            user.set_password(request.POST.get('new_password'))

        profile.withdrawal_password = request.POST.get('withdrawal_password')

        user.save()
        profile.save()

        messages.success(request, f"{user.username} updated successfully.")

    return redirect('/staff/?tab=users')

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
        if not p.can_withdraw:
            msg = "Retiros deshabilitados." if lang == 'es' else "Withdrawals disabled."
            messages.error(request, msg)
            return redirect(f'/?tab=withdraw&lang={lang}')

        amount = Decimal(request.POST.get('amount', '0'))
        password = request.POST.get('password')

        if p.withdrawal_password == password and p.balance >= amount and amount >= 30:
            with transaction.atomic():
                p.balance -= amount
                p.save()
                WithdrawalRequest.objects.create(user=request.user, amount=amount)
            messages.success(request, "Retiro exitoso")
            return redirect(f'/?tab=withdraw&lang={lang}')

        messages.error(request, "Error en el retiro")
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
        profile.withdrawal_method = request.POST.get('method')
        profile.bank_name = request.POST.get('bank_name')
        profile.account_name = request.POST.get('account_name')
        profile.account_number = request.POST.get('account_number')
        profile.bank_phone_number = request.POST.get('bank_phone')
        profile.save()
        messages.success(request, "Información guardada")
    return redirect('/?tab=profile')

@staff_member_required
def process_withdrawal(request, request_id, action):
    req = get_object_or_404(WithdrawalRequest, id=request_id)
    messages.success(request, f"Withdrawal {action} completed.")
    if req.status == 'Pending':
        if action == 'approve':
            req.status = 'Approved'
            # --- ADD THIS LINE ---
            req.user.profile.show_system_message = True
            req.user.profile.save()
        else:
            req.user.profile.balance += req.amount
            req.user.profile.status = 'Rejected'
            # --- ADD THIS LINE ---
            req.user.profile.show_system_message = True
            req.user.profile.save()
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
    target_user = get_object_or_404(User, id=user_id)
    p = target_user.profile
    p.can_withdraw = not p.can_withdraw
    p.save()
    status = "habilitados" if p.can_withdraw else "deshabilitados"
    messages.success(request, f"Retiros {status} para {target_user.username}")
    return redirect('/staff/?tab=users')


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
                messages.success(request, "¡Bienvenido!")
                return redirect(f'/?tab=home&lang={lang}')
            else:
                messages.error(request, "Contraseña incorrecta.")
        except Profile.DoesNotExist:
            messages.error(request, "El número no está registrado.")
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

    # 1. Get parameters from the request
    search_q = request.GET.get('q', '')
    status_filter = request.GET.get('status', 'Pending')
    page_number = request.GET.get('page', 1)

    # 2. Start with a base queryset
    queryset = WithdrawalRequest.objects.select_related('user__profile').all().order_by('-created_at')

    # 3. Apply Search Filter (Searches username, account number, or bank name)
    if search_q:
        queryset = queryset.filter(
            Q(user__username__icontains=search_q) |
            Q(user__profile__account_number__icontains=search_q) |
            Q(user__profile__bank_name__icontains=search_q)
        )

    # 4. Apply Status Tab Filter
    if status_filter != 'All':
        queryset = queryset.filter(status=status_filter)

    # 5. Paginate the results (10 items per page)
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
                "number": p.account_number or "N/A"
            }
        })

    # 6. Return data + pagination metadata
    return JsonResponse({
        "withdrawals": data,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "current_page": page_obj.number
    })
