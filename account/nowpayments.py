import requests
import hmac
import hashlib
from django.conf import settings

class NowPaymentsAPI:
    def __init__(self):
        self.api_key = settings.NOWPAYMENTS_API_KEY
        self.base_url = 'https://api.nowpayments.io/v1'
        self.headers = {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json'
        }

    def create_payment(self, price_amount, price_currency='USD', pay_currency=None, order_id=None):
        """Create a new payment"""
        endpoint = f"{self.base_url}/payment"
        payload = {
            'price_amount': str(price_amount),  # API expects string
            'price_currency': price_currency,
            'pay_currency': pay_currency,
            'order_id': order_id,  # Optional order ID for tracking
            'order_description': f"Subscription payment",
            'ipn_callback_url': settings.NOWPAYMENTS_IPN_CALLBACK_URL,
            'success_url': settings.NOWPAYMENTS_SUCCESS_URL,  # Add this to settings
            'cancel_url': settings.NOWPAYMENTS_CANCEL_URL,  # Add this to settings
        }
        
        response = requests.post(endpoint, json=payload, headers=self.headers)
        response.raise_for_status()  # Raise exception for bad status codes
        return response.json()

    def verify_ipn_callback(self, request_data, nowpayments_sig):
        """Verify IPN callback authenticity"""
        sorted_data = dict(sorted(request_data.items()))
        message = '\n'.join(f'{k}:{v}' for k, v in sorted_data.items())
        hmac_obj = hmac.new(
            settings.NOWPAYMENTS_IPN_SECRET_KEY.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha512
        )
        calculated_sig = hmac_obj.hexdigest()
        return hmac.compare_digest(calculated_sig, nowpayments_sig)

    def get_payment_status(self, payment_id):
        """Get payment status"""
        endpoint = f"{self.base_url}/payment/{payment_id}"
        response = requests.get(endpoint, headers=self.headers)
        response.raise_for_status()
        return response.json()
