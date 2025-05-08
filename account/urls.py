from django.urls import path
from . import views

app_name = 'account'

urlpatterns = [
  path('register/', views.register, name='register'),
  path('login/', views.user_login, name='login'),
  path('profile/', views.profile, name='profile'),
  path('logout/', views.user_logout, name='logout'),
  path('plans/', views.subscription_plans, name='plans'),
  path('subscribe/<int:plan_id>/', views.subscribe_to_plan, name='subscribe'),
 # path('subscriptions/', views.subscription_list, name='subscriptions'),

  path('transactions/', views.transaction_history, name='transactions'),
  path('change-password/', views.change_password, name='change_password'),
#updated
  path('payment/create/<int:plan_id>/', views.create_payment, name='create_payment'),
  path('payment/details/<str:payment_id>/', views.payment_details, name='payment_details'),
  path('payment/check-status/<str:payment_id>/', views.check_payment_status, name='check_payment_status'),
  path('payments/ipn-callback/', views.ipn_callback, name='ipn_callback'),
  path('subscriptions/status/', views.subscription_status, name='subscription_status'),
  path('subscriptions/', views.subscription_plans, name='subscription_plans'),

]