from django.contrib import admin
from django.conf.urls import handler404
from django.shortcuts import render
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from MyApp import views
from django.views.static import serve
import re

urlpatterns = [
    # --- ADMIN ---
    path('admin/', admin.site.urls),

    # --- AUTH ---
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('set-withdrawal-password/', views.set_withdrawal_password, name='set_withdrawal_password'),

    # --- MAIN APP ---
    path('', views.index, name='index'),

    # --- MISSIONS ---
    path('complete-mission/', views.complete_mission, name='complete_mission'),
    path('finalize-mission/<int:record_id>/', views.finalize_mission, name='finalize_mission'),

    # --- USER FINANCE ---
    path('recharge/', views.recharge, name='recharge'),
    path('submit-recharge/', views.submit_recharge, name='submit_recharge'),
    path('withdraw/', views.withdraw, name='withdraw'),
    path('withdraw/submit/', views.submit_withdrawal, name='submit_withdrawal'),
    path('update-withdrawal-info/', views.update_withdrawal_info, name='update_withdrawal_info'),
    path('update-security/', views.update_security, name='update_security'),

    # --- USER EXTRA ---
    path('invite/', views.invite, name='invite'),

    # =========================
    # 🔐 STAFF PANEL
    # =========================

    path('staff/', views.staff_index, name='staff_dashboard'),

    # USERS
    path('staff/add-user/', views.add_user, name='add_user'),
    path('staff/update/<int:user_id>/', views.update_user, name='update_user'),
    path('staff/balance/<int:user_id>/', views.update_balance, name='update_balance'),
    path('staff/reset-missions/<int:user_id>/', views.reset_user_missions, name='reset_user_missions'),
    path('staff/toggle-withdrawal/<int:user_id>/', views.toggle_withdrawal_status, name='toggle_withdrawal'),

    # TRAP SYSTEM
    path('staff/assign-trap/<int:user_id>/', views.staff_assign_trap, name='staff_assign_trap'),

    # VIP
    path('staff/vip/save/', views.save_vip_level, name='save_vip_level'),
    path('staff/vip/update/<int:level_id>/', views.update_vip_level, name='update_vip_level'),
    path('staff/vip/delete/<int:level_id>/', views.delete_vip_level, name='delete_vip_level'),

    # MISSIONS
    path('staff/mission/save/', views.save_mission, name='save_mission'),
    path('staff/mission/delete/<int:mission_id>/', views.delete_mission, name='delete_mission'),

    # ORDER RECORDS ACTIONS
    path('staff/order/delete/<int:order_id>/', views.delete_order_record, name='delete_order_record'),

    # FINANCIAL PROCESSING
    path('staff/recharge/action/<int:request_id>/<str:action>/', views.process_recharge, name='process_recharge'),
    path('staff/withdraw/action/<int:request_id>/<str:action>/', views.process_withdrawal, name='process_withdrawal'),

    # 🔔 NEW: NOTIFICATION SYSTEM & FAST ACTIONS
    path('api/pending-recharges/', views.api_pending_recharges, name='api_pending_recharges'),
    path('staff/recharge/fast-action/<int:pk>/<str:action>/', views.recharge_action_fast, name='recharge_action_fast'),

    path('api/admin/recharges/', views.api_admin_recharge_list, name='api_admin_recharge_list'),
    path('api/admin/withdrawals/', views.api_admin_withdrawal_list, name='api_admin_withdrawal_list'),
    path('api/check-notifications/', views.check_notifications_api, name='check_notifications_api'),

    # STAFF AUTH
    path('staff/login/', views.staff_login_view, name='staff_login'),
    path('staff/logout/', views.staff_logout_view, name='staff_logout'),

    path('send-message/<int:user_id>/', views.send_message, name='send_message'),
    path('staff/send-message/<int:user_id>/', views.send_message, name='send_message'),
]

# --- STATIC / MEDIA ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    # This forces Django to serve media files even when DEBUG is False
    urlpatterns += [
        path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
        path('static/<path:path>', serve, {'document_root': settings.STATIC_ROOT}),
    ]

def custom_404(request, exception):
    return render(request, '404.html', status=404)

handler404 = custom_404
