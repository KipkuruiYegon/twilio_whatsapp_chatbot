import requests
import base64
import json
from datetime import datetime
from django.conf import settings
import time
import base64
from datetime import datetime


def generate_token():
    """
    This function generates the access token required for M-Pesa API requests.
    """
    consumer_key = settings.MPESA_CONSUMER_KEY
    consumer_secret = settings.MPESA_CONSUMER_SECRET

    # Encode the consumer key and secret
    api_key = base64.b64encode(f"{consumer_key}:{consumer_secret}".encode()).decode()

    headers = {
        "Authorization": f"Basic {api_key}"
    }

    response = requests.get("https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
                            headers=headers)

    if response.status_code == 200:
        access_token = response.json().get("access_token")
        return access_token
    else:
        raise Exception("Failed to generate access token: " + response.text)


def generate_password(timestamp):
    """
    Generates a password for the M-Pesa API based on the provided timestamp.
    """
    passkey = settings.MPESA_PASSKEY
    shortcode = settings.MPESA_SHORTCODE
    data_to_encode = shortcode + passkey + timestamp
    encoded_string = base64.b64encode(data_to_encode.encode('utf-8')).decode('utf-8')
    return encoded_string

def initiate_stk_push(phone_number, amount, account_reference):
    # Generate the current timestamp
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

    # Generate the password using the timestamp
    password = generate_password(timestamp)

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone_number,
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": "https://darajambili.herokuapp.com/express-payment",
        "AccountReference": account_reference,
        "TransactionDesc": "Payment for Order"
    }

    headers = {
        "Authorization": f"Bearer {generate_token()}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        settings.MPESA_API_URL,
        json=payload,
        headers=headers
    )

    return response.json()



