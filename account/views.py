from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import CustomUserCreationForm, DepositForm, EmailAuthenticationForm
from .models import UserProfile, Deposit, Transactions, SubscriptionPlan, Subscription
from django.db.models import Sum
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from core.models import Campaign, Cryptocurrency  # Add this import
import logging
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.conf import settings
from .nowpayments import NowPaymentsAPI
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import json
from time import sleep
import time

logger = logging.getLogger(__name__)


# User registration view
def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user)

            login(request, user)
            


            messages.success(request, 'Account created successfully. Please log in.')
            return redirect('account:profile')
        else:
            logger.debug(f'Form errors: {form.errors}')  # Log form errors
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserCreationForm()

    return render(request, 'account/register.html', {'form': form})


# User login view
from django.contrib.auth.forms import AuthenticationForm
def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)

            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                return redirect('account:profile')  # Redirect to your dashboard or home page
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    return render(request, 'account/login.html', {'form': form})



# User logout view
@login_required
def user_logout(request):
    logout(request)
    messages.success(request, 'Logged out successfully.')
    return redirect('account:login')


@login_required
def profile(request):
    user_profile = UserProfile.get_profile(request.user)

    # Get completed deposits
    deposits = Deposit.objects.filter(user=request.user, payment_status='COMPLETED')
    total_deposits = sum(
        deposit.subscription_plan.price for deposit in deposits if deposit.subscription_plan
    )

    # Get transactions
    transactions = Transactions.objects.filter(
        user=request.user
    ).select_related('subscription__plan')

    # Safely handle campaigns_count (skip if Campaign model is unavailable)
    try:
        from core.models import Campaign
        campaigns_count = Campaign.objects.filter(user=request.user).count()
    except ImportError:
        campaigns_count = 0

    context = {
        'user_profile': user_profile,
        'total_deposits': total_deposits,
        'total_transactions': len(deposits),
        'transactions': transactions,
        'campaigns_count': campaigns_count,
    }
    return render(request, 'account/profile.html', context)


# Subscription plans view
@login_required
def subscription_plans(request):
    """Display available subscription plans"""
    plans = SubscriptionPlan.objects.all()
    
    # Check if user has active subscription
    user_profile = request.user.userprofile
    has_active_subscription = user_profile.has_active_subscription
    
    context = {
        'plans': plans,
        'has_active_subscription': has_active_subscription
    }
    return render(request, 'account/subscription_plans.html', context)

# Subscribe to plan view
@login_required
def subscribe_to_plan(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    # Remove deposit creation from here
    return redirect('account:create_payment', plan_id=plan.id)

# Transaction history view
@login_required
def transaction_history(request):
    deposits = Deposit.objects.filter(
        user=request.user
    ).select_related('subscription_plan').order_by('-created_at')

    # Calculate total amount from completed deposits - fix status to payment_status
    total_amount = sum(
        deposit.subscription_plan.price 
        for deposit in deposits 
        if deposit.payment_status == 'COMPLETED'
    )

    return render(request, 'account/transactions.html', {
        'deposits': deposits,
        'total_amount': total_amount
    })

# Change password view
@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keeps the user logged in
            messages.success(request, 'Your password was successfully updated!')
            logger.info(f'Password updated for user {user}')
            return redirect('account:profile')  # Redirect to profile page or another page after success
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'account/change_password.html', {'form': form})

def notify_admins_of_pending_payment(deposit):
    User = get_user_model()
    admins = User.objects.filter(is_superuser=True)
    
    subject = "New Subscription Payment Pending"
    message = f"""
    A new payment is pending approval:
    User: {deposit.user.username}
    Plan: {deposit.subscription_plan}
    Amount: ${deposit.amount}
    """
    
    admin_emails = [admin.email for admin in admins if admin.email]
    if admin_emails:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=admin_emails,
            fail_silently=True
        )




################################################### PAYMENT VIEWS ####################################################



@login_required
def create_payment(request, plan_id):
    """Create a payment for a subscription plan"""
    plan = get_object_or_404(SubscriptionPlan, pk=plan_id)
    
    if request.method == 'POST':
        # Initialize NowPayments API
        nowpayments_api = NowPaymentsAPI()
        
        # Get selected cryptocurrency from form (if applicable)
        pay_currency = request.POST.get('pay_currency', 'BTC')  # Default to BTC
        
        try:
            # Create payment through NowPayments API
            payment_data = nowpayments_api.create_payment(
                price_amount=plan.price,
                price_currency='USD',  # Change if your primary currency is different
                pay_currency=pay_currency,
                order_id=f"sub_{request.user.id}_{plan.id}_{timezone.now().timestamp()}"
            )

     # Create deposit record in database
            deposit = Deposit.objects.create(
                payment_id=payment_data['payment_id'],
                user=request.user,
                subscription_plan=plan,
                pay_address=payment_data['pay_address'],
                pay_amount=payment_data['pay_amount'],
                pay_currency=payment_data['pay_currency'],
                price_amount=payment_data['price_amount'],
                price_currency=payment_data['price_currency'],
                payment_status='WAITING'
            )

            return redirect('account:payment_details', payment_id=deposit.payment_id)
        except Exception as e:
            logger.error(f"Error creating payment: {str(e)}")
            messages.error(request, f"Payment creation failed: {str(e)}")
            return redirect('account:subscription_plans')
        
    cryptocurrencies = [
        {'code': 'BTC', 'name': 'Bitcoin'},
        {'code': 'ETH', 'name': 'Ethereum'},
        {'code': 'LTC', 'name': 'Litecoin'},
        {'code': 'USDTBSC', 'name': 'USDT(BEP20)'},
        {'code': 'USDTTRC20', 'name': 'USDT(TRC20)'},
        {'code': 'DOGE', 'name': 'Dogecoin'},
        {'code': 'XRP', 'name': 'Ripple'},
        {'code': 'TRX', 'name': 'Tron'},
        {'code': 'SOL', 'name': 'Solana'},
        {'code': 'MATIC', 'name': 'Polygon'},
        # Add more cryptocurrencies as needed
    ]
    
    context = {
        'plan': plan,
        'cryptocurrencies': cryptocurrencies
    }
    return render(request, 'account/create_payment.html', context)



@login_required
def payment_details(request, payment_id):
    """Display payment details and status"""
    deposit = get_object_or_404(Deposit, payment_id=payment_id, user=request.user)
    
    # If payment is not completed, check the current status
    if deposit.payment_status != 'COMPLETED':
        try:
            nowpayments_api = NowPaymentsAPI()
            payment_status = nowpayments_api.get_payment_status(deposit.payment_id)
            
            # Update deposit status if changed
            if payment_status['payment_status'] != deposit.payment_status:
                deposit.payment_status = payment_status['payment_status']
                deposit.save()
                
                # If payment is now completed, create subscription
                if deposit.payment_status == 'COMPLETED' and deposit.subscription_plan:
                    _create_or_extend_subscription(deposit)
                    messages.success(request, "Payment completed! Your subscription has been activated.")
        except Exception as e:
            logger.error(f"Error checking payment status: {str(e)}")
    
    context = {
        'deposit': deposit,
        'now': timezone.now()
    }
    return render(request, 'account/payment_details.html', context)

from .models import NOWPAYMENTS_STATUS_MAPPING



@csrf_exempt
@require_POST
def ipn_callback(request):
    """Handle NOWPayments IPN callbacks"""
    try:
        # Verify the request
        request_data = json.loads(request.body)
        logger.info(f"Received IPN callback: {request_data}")

        payment_id = request_data.get('payment_id')
        nowpayments_status = request_data.get('payment_status', '').lower()

        if not payment_id:
            logger.error("No payment_id in IPN callback")
            return HttpResponse(status=400)

        # Get the translated status
        internal_status = NOWPAYMENTS_STATUS_MAPPING.get(nowpayments_status)
        if not internal_status:
            logger.error(f"Unknown payment status: {nowpayments_status}")
            return HttpResponse(status=400)

        logger.info(f"Translating status '{nowpayments_status}' to '{internal_status}'")

        try:
            with transaction.atomic():
                deposit = Deposit.objects.select_for_update().get(payment_id=payment_id)
                
                # Update deposit
                deposit.payment_status = internal_status
                deposit.ipn_received = True  # Set IPN received flag
                deposit.save()

                logger.info(f"Updated deposit {payment_id}: status={internal_status}, ipn_received=True")

                # If payment is completed, handle subscription
                if internal_status == 'COMPLETED':
                    _create_or_extend_subscription(deposit)
                    logger.info(f"Created/extended subscription for deposit {payment_id}")

            return HttpResponse("OK", status=200)

        except Deposit.DoesNotExist:
            logger.error(f"Deposit not found for payment_id: {payment_id}")
            return HttpResponse(status=404)

    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return HttpResponse(status=400)
    except Exception as e:
        logger.error(f"Error processing IPN: {str(e)}", exc_info=True)
        return HttpResponse(status=500)
    
def _create_or_extend_subscription(deposit):
    """Helper function to create or extend subscription"""
    with transaction.atomic():
        # Check for existing subscription
        existing_subscription = Subscription.objects.filter(
            user=deposit.user,
            is_active=True
        ).first()

        if existing_subscription:
            # Extend existing subscription
            existing_subscription.end_date += timezone.timedelta(days=deposit.subscription_plan.duration_days)
            existing_subscription.save()
            logger.info(f"Extended subscription for user {deposit.user.id}")
        else:
            # Create new subscription
            subscription = Subscription.objects.create(
                user=deposit.user,
                plan=deposit.subscription_plan,
                is_active=True,
                start_date=timezone.now(),
                end_date=timezone.now() + timezone.timedelta(days=deposit.subscription_plan.duration_days)
            )
            logger.info(f"Created new subscription {subscription.id} for user {deposit.user.id}")

        # Create transaction record
        Transactions.objects.create(
            user=deposit.user,
            subscription=subscription,
            status='COMPLETED'
        )
@login_required
def subscription_status(request):
    """View subscription status"""
    user = request.user
    try:
        subscriptions = Subscription.objects.filter(
            user=user,
            is_active=True,
            end_date__gt=timezone.now()
        ).order_by('-end_date')
        
        transactions = Transactions.objects.filter(
            user=user,
            status='COMPLETED'
        ).order_by('-created_at')[:10]  # Show last 10 transactions
        
    except Exception as e:
        subscriptions = []
        transactions = []
        logger.error(f"Error retrieving subscription data: {str(e)}")
        messages.error(request, "Unable to retrieve subscription information.")
    
    context = {
        'subscriptions': subscriptions,
        'transactions': transactions,
        'now': timezone.now()
    }
    return render(request, 'account/subscription_status.html', context)

@login_required
def check_payment_status(request, payment_id):
    """Check payment status with polling"""
    logger.info(f"Checking status for payment {payment_id}")
    
    timeout = 900  # 5 minutes timeout
    interval = 10  # Check every 10 seconds
    start_time = time.time()
    
    try:
        while True:
            deposit = get_object_or_404(Deposit, payment_id=payment_id, user=request.user)
            nowpayments_api = NowPaymentsAPI()
            
            payment_data = nowpayments_api.get_payment_status(payment_id)
            logger.info(f"NOWPayments response: {payment_data}")
            
            nowpayments_status = payment_data.get('payment_status', '').lower()
            internal_status = NOWPAYMENTS_STATUS_MAPPING.get(nowpayments_status, 'PENDING')
            
            logger.info(f"Status translation: {nowpayments_status} -> {internal_status}")
            
            if internal_status != deposit.payment_status:
                deposit.payment_status = internal_status
                deposit.save()
                logger.info(f"Updated deposit status to {internal_status}")
                
                if internal_status == 'COMPLETED':
                    _create_or_extend_subscription(deposit)
                    break

            if time.time() - start_time > timeout:
                logger.warning(f"Payment check timed out for payment_id: {payment_id}")
                break

            sleep(interval)

        return JsonResponse({
            'status': internal_status,
            'lastUpdated': deposit.updated_at.strftime('%B %d, %Y, %I:%M %p')
        })

    except Exception as e:
        logger.error(f"Error checking status: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)