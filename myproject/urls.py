from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from MyApp import views

urlpatterns = [
    # --- ADMIN INTERFACE ---
    path('admin/', admin.site.urls),

    # --- AUTHENTICATION ---
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('set-withdrawal-password/', views.set_withdrawal_password, name='set_withdrawal_password'),

    # --- USER MOBILE APP (MAIN) ---
    path('', views.index, name='index'),

    # --- STAFF DASHBOARD & USER MANAGEMENT ---
    path('staff/', views.staff_index, name='staff_dashboard'),
    path('staff/update/<int:user_id>/', views.update_user, name='update_user'),
    path('staff/balance/<int:user_id>/', views.update_balance, name='update_balance'),
    path('staff/add-user/', views.add_user, name='add_user'),

    # --- VIP MANAGEMENT ---
    # Create new
    path('staff/vip/save/', views.save_vip_level, name='save_vip_level'),

    # Update existing (Matches the /update/ path used in the Edit Modal)
    path('staff/vip/update/<int:level_id>/', views.save_vip_level, name='update_vip_level'),

    # Delete (Matches the name used in the Table)
    path('staff/vip/delete/<int:level_id>/', views.delete_vip_level, name='delete_vip_level'),

    # --- USER FINANCIAL ACTIONS ---
    path('recharge/', views.recharge, name='recharge'),
    path('submit-recharge/', views.submit_recharge, name='submit_recharge'),
    path('withdraw/', views.withdraw, name='withdraw'),
    path('withdraw/submit/', views.submit_withdrawal, name='submit_withdrawal'),
    path('update-withdrawal-info/', views.update_withdrawal_info, name='update_withdrawal_info'),
    path('update-security/', views.update_security, name='update_security'),

    # Financial Processing (Staff Side)
    path('staff/withdraw/action/<int:request_id>/<str:action>/', views.process_withdrawal, name='process_withdrawal'),
    path('staff/recharge/action/<int:request_id>/<str:action>/', views.process_recharge, name='process_recharge'),
    path('staff/toggle-withdrawal/<int:user_id>/', views.toggle_withdrawal_status, name='toggle_withdrawal'),

    # --- USER SOCIAL/PROFILE ---
    path('invite/', views.invite, name='invite'),
]

# --- MEDIA & STATIC SERVING ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
