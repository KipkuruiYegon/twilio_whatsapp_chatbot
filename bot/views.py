import os
import requests
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from requests.auth import HTTPBasicAuth
from datetime import datetime
from twilio.rest import Client
from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image
from reportlab.lib.units import inch
from django.templatetags.static import static
from io import BytesIO
from .mpesa_utils import initiate_stk_push
import logging

# Initialize Twilio client
client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

# Authentication credentials for ERP system
AUTH_CREDENTIALS = HTTPBasicAuth('davisapi', 'zheghH5w631+AQ8GkKK6AMTEHGaPHP23aK8okWWQmGE=')

# Function to generate PDF invoice
def generate_and_save_pdf_invoice(order_no, customer_name, items, total_amount, paid=False, shipping_details=None):
    buffer = BytesIO()  # Create an in-memory file
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Add the company logo
    logo_path = static('dSLogo.png')  # Correctly reference the static file
    logo_full_path = os.path.join(settings.BASE_DIR, logo_path.lstrip('/'))
    logo = Image(logo_full_path, 2 * inch, 1 * inch)
    elements.append(logo)

    # Add the title and order details
    title_data = [
        ["Sales Order Invoice"],
        [f"Order No: {order_no}"],
        [f"Customer Name: {customer_name}"],
        [f"Date: {datetime.now().strftime('%Y-%m-%d')}"],
    ]
    if paid:
        title_data.append([f"Status: PAID"])
    else:
        title_data.append([f"Status: UNPAID"])

    title_table = Table(title_data)
    title_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(title_table)

    # Add the item table headers
    data = [["#", "Item", "Quantity", "Price (KES)", "Total (KES)"]]

    # Add the items with numbering
    for idx, item in enumerate(items, start=1):
        data.append([
            idx,
            item['product']['Description'],
            str(item['quantity']),
            f"{item['product']['Unit_Price']:,}",
            f"{item['product']['Unit_Price'] * item['quantity']:,}"
        ])

    # Add the total amount
    data.append(["", "", "", "Total Amount:", f"{total_amount:,} KES"])

    # Add shipping details if paid
    if paid and shipping_details:
        data.append(["", "", "", "Shipping Address:", shipping_details])

    # Create the table
    table = Table(data)
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)  # Rewind the buffer to the beginning so it can be read

    # Save the PDF to file
    pdf_filename = f"{order_no}_invoice{'_paid' if paid else ''}.pdf"
    pdf_path = os.path.join(settings.MEDIA_ROOT, pdf_filename)

    with open(pdf_path, 'wb') as f:
        f.write(buffer.getvalue())

    return pdf_path  # Return the path to the saved PDF file


@csrf_exempt
def get_invoice_pdf(request):
    invoice_no = request.GET.get('invoice_no')

    # Assuming invoices are named like `order_no_invoice.pdf`
    pdf_filename = f"{invoice_no}_invoice.pdf"
    pdf_path = os.path.join(settings.MEDIA_ROOT, pdf_filename)

    if os.path.exists(pdf_path):
        pdf_url = request.build_absolute_uri(f"{settings.MEDIA_URL}{pdf_filename}")
        return JsonResponse({"invoice_url": pdf_url}, status=200)
    else:
        return JsonResponse({"error": "Invoice not found."}, status=404)


# Function to send PDF invoice via WhatsApp
def send_pdf_invoice(request, to, order_no, customer_name, items, total_amount, paid=False):
    pdf_buffer = generate_pdf_invoice(order_no, customer_name, items, total_amount, paid=paid)

    # Save PDF to file
    pdf_filename = f"{order_no}_invoice{'_paid' if paid else ''}.pdf"
    pdf_path = os.path.join(settings.MEDIA_ROOT, pdf_filename)

    with open(pdf_path, 'wb') as f:
        f.write(pdf_buffer.getvalue())

    # Construct the download link
    pdf_url = request.build_absolute_uri(f"{settings.MEDIA_URL}{pdf_filename}")

    # Inform the user to download the invoice
    body = f"Your order has been placed successfully. Download your {'paid ' if paid else ''}invoice here: {pdf_url}"

    # Ensure 'to' is in the E.164 format with the 'whatsapp:' prefix
    from_number = settings.TWILIO_WHATSAPP_NUMBER
    to_number = f"whatsapp:{convert_to_e164(to)}"

    # Send the message via Twilio with the link
    send_twilio_message(to_number, body)

    return True

# Utility function to convert phone number to E.164 format
def convert_to_e164(phone_number):
    phone_number = phone_number.strip()

    # Remove any non-digit characters
    phone_number = ''.join(filter(str.isdigit, phone_number))

    # Convert local numbers (starting with '0') to the correct format
    if len(phone_number) == 10 and phone_number.startswith('0'):
        phone_number = '254' + phone_number[1:]
    elif len(phone_number) == 12 and phone_number.startswith('254'):
        # Kenyan number already in the correct format
        return phone_number
    elif not phone_number.startswith('254'):
        # If the number does not match expected patterns, return None to indicate an error
        return None

    return phone_number



def convert_to_e164(phone_number):
    phone_number = phone_number.strip()

    # Remove any non-digit characters (optional, depending on your use case)
    phone_number = ''.join(filter(str.isdigit, phone_number))

    if len(phone_number) == 10 and phone_number.startswith('0'):
        # Local Kenyan number, replace leading '0' with '+254'
        phone_number = '+254' + phone_number[1:]
    elif len(phone_number) == 12 and phone_number.startswith('254'):
        # Kenyan number already in international format, add '+'
        phone_number = '+' + phone_number
    elif not phone_number.startswith('+'):
        # If the number does not match expected patterns, return None to indicate an error
        return None

    return phone_number


# Function to collect missing customer details
def collect_missing_details(request):
    if not request.session.get('customer_name'):
        request.session['step'] = 'name'
        return "Please provide your name."
    if not request.session.get('customer_no'):
        request.session['step'] = 'customer_no'
        return "Please provide your customer number."
    if not request.session.get('phone_no'):
        request.session['step'] = 'phone_no'
        return "Please provide your phone number."
    if not request.session.get('shipping_address'):
        request.session['step'] = 'shipping_address'
        return "Please provide your shipping address."
    return None


# Function to handle M-Pesa callback
@csrf_exempt
def mpesa_callback(request):
    data = json.loads(request.body)

    if data.get('Body').get('stkCallback').get('ResultCode') == 0:
        # Payment was successful
        callback_metadata = data['Body']['stkCallback']['CallbackMetadata']['Item']
        phone_number = next(item['Value'] for item in callback_metadata if item['Name'] == 'PhoneNumber')
        order_no = next(item['Value'] for item in callback_metadata if item['Name'] == 'AccountReference')
        amount = next(item['Value'] for item in callback_metadata if item['Name'] == 'Amount')

        # Fetch the relevant data to generate the PAID invoice
        cart = request.session.get('cart', [])
        customer_name = request.session.get('customer_name')
        shipping_address = request.session.get('shipping_address')

        # Generate and send the PAID invoice
        send_pdf_invoice(request, phone_number, order_no, customer_name, cart, amount, paid=True)

        # Clear session after order is complete
        request.session.flush()

        return HttpResponse(status=200)
    else:
        return HttpResponse(status=400)


def search_products(search_query):
    url = f"https://bctest.dayliff.com:7048/BC160/ODataV4/Company('KENYA')/ItemsAPI?$filter=contains(Description, '{search_query}')"
    headers = {"Content-Type": "application/json"}

    response = requests.get(url, headers=headers, auth=AUTH_CREDENTIALS)

    # Log the full response for debugging
    print("API Status Code:", response.status_code)
    print("API Response:", response.text)

    if response.status_code == 200:
        products = response.json().get('value', [])

        if products:
            product_list = ["Here are the products we found related to your search:\n"]
            for i, prod in enumerate(products, start=1):
                price = f"{prod['Unit_Price']:,} KES"
                product_list.append(
                    f"  {i}. {prod['No']}: {prod['Description']} - {price} (Stock: {prod['Inventory']})")

            product_list_str = "\n".join(product_list)
            max_length = 4096
            if len(product_list_str) > max_length:
                messages = [product_list_str[i:i + max_length] for i in range(0, len(product_list_str), max_length)]
            else:
                messages = [product_list_str]

            messages[
                -1] += "\n\nPlease reply with the product number and quantity to add to your cart. Example: add PKM060 2"
            return messages
        else:
            return ["Sorry, we couldn't find any products matching your search."]
    else:
        return ["There was an error fetching products. Please try again later."]


def select_product(cart, selected_product_no, quantity):
    url = f"https://bctest.dayliff.com:7048/BC160/ODataV4/Company('KENYA')/ItemsAPI?$filter=No%20eq%20%27{selected_product_no}%27"
    headers = {"Content-Type": "application/json"}

    response = requests.get(url, headers=headers, auth=AUTH_CREDENTIALS)
    if response.status_code == 200:
        products = response.json().get('value', [])
        if products:
            product = products[0]
            # Add product and quantity to the cart
            cart.append({"product": product, "quantity": quantity})
            return f"Added {quantity} of {product['Description']} to your cart. Please reply with your name to proceed."
        else:
            return "The selected product could not be found."
    else:
        return "There was an error adding the product to your cart."



# Define a logger
logger = logging.getLogger(__name__)
# Place Order and Create Invoice
@csrf_exempt
def place_order(request, cart):
    # Collect any missing details before placing the order
    missing_details_message = collect_missing_details(request)
    if missing_details_message:
        return JsonResponse({"message": missing_details_message}, status=400)

    customer_no = request.session.get('customer_no')
    customer_name = request.session.get('customer_name')
    phone_no = request.session.get('phone_no')  # No conversion needed
    shipping_address = request.session.get('shipping_address')

    # Validate that the phone number is in the correct format
    if not phone_no.startswith('254') or len(phone_no) != 12:
        return JsonResponse({"error": "Invalid phone number format. Please provide the number in the format 2547XXXXXXXX."}, status=400)

    # Log the formatted phone number for verification
    logger.info(f"Phone number used for ERP and STK Push: {phone_no}")

    # Create the sales order header
    sales_order_data = {
        "Document_Type": "Order",
        "Sell_to_Customer_No": customer_no,
        "Sell_to_Customer_Name": customer_name,
        "Sell_to_Phone_No": phone_no,
        "Document_Date": datetime.now().strftime('%Y-%m-%d'),
        "Posting_Date": datetime.now().strftime('%Y-%m-%d'),
        "Order_Date": datetime.now().strftime('%Y-%m-%d'),
        "Sell_to_Address": shipping_address,
        "Location_Code": "21510",  # Replace with your actual location code
    }

    url = "https://bctest.dayliff.com:7048/BC160/ODataV4/Company('KENYA')/Sales_Order"
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, json=sales_order_data, headers=headers, auth=AUTH_CREDENTIALS)

    if response.status_code == 201:
        order_response = response.json()
        order_no = order_response['No']
        total_amount = sum(item['product']['Unit_Price'] * item['quantity'] for item in cart)

        # Trigger MPESA STK Push directly with the given phone number
        stk_response = initiate_stk_push(phone_no, total_amount, order_no)

        logger.info(f"STK Response: {stk_response}")

        if 'ResponseCode' in stk_response and stk_response['ResponseCode'] == '0':
            cart.clear()
            return JsonResponse({
                "invoice": f"Order {order_no} has been placed successfully. Please complete the payment on your phone.",
                "order_no": order_no
            }, status=201)
        else:
            error_message = stk_response.get('errorMessage', 'Unknown error')
            return JsonResponse({"error": f"Failed to initiate payment: {error_message}"}, status=400)
    else:
        return JsonResponse({"error": response.json()}, status=response.status_code)


@csrf_exempt
def whatsapp_webhook(request):
    incoming_message = request.POST.get('Body')
    sender = request.POST.get('From')
    cart = request.session.get('cart', [])
    step = request.session.get('step', 'menu')

    # Handle greetings and show the main menu
    if incoming_message.lower() in ['hi', 'hello', 'hey']:
        response_message = handle_greetings()
        request.session['step'] = 'menu'

    # Handle menu selections
    elif step == 'menu' and incoming_message in ["1", "2", "3", "4"]:
        if incoming_message == "1":
            response_message = "Please enter the product description to search:"
            request.session['step'] = 'searching'
        elif incoming_message == "2":
            response_message = get_business_info("2")
        elif incoming_message == "3":
            response_message = get_business_info("3")
        elif incoming_message == "4":
            response_message = "Please enter your order number:"
            request.session['step'] = 'checking_order'

    # Handle product search
    elif step == 'searching':
        messages = search_products(incoming_message)
        for message in messages:
            send_twilio_message(sender, message)
        request.session['step'] = 'selecting'
        return JsonResponse({"message": "Product list sent."})

    # Handle order status check
    elif step == 'checking_order':
        order_id = incoming_message.strip()
        response_message = confirm_order(order_id)
        request.session['step'] = 'menu'

    # Handle product selection
    elif step == 'selecting' and incoming_message.lower().startswith("add"):
        parts = incoming_message.split()
        if len(parts) >= 3:
            product_no = parts[1]
            quantity = int(parts[2])
            response_message = select_product(cart, product_no, quantity)
            request.session['cart'] = cart
            request.session['step'] = 'name'

    # Handle customer name input
    elif step == 'name':
        customer_name = incoming_message.strip()
        request.session['customer_name'] = customer_name
        response_message = "Thank you. Please provide your customer number."
        request.session['step'] = 'customer_no'

    # Handle customer number input
    elif step == 'customer_no':
        customer_no = incoming_message.strip()
        request.session['customer_no'] = customer_no
        response_message = "Thank you. Please provide your phone number."
        request.session['step'] = 'phone_no'

    # Handle phone number input
    elif step == 'phone_no':
        phone_no = incoming_message.strip()
        request.session['phone_no'] = phone_no
        response_message = "Thank you. Please provide your shipping address."
        request.session['step'] = 'shipping_address'

    # Handle shipping address input
    elif step == 'shipping_address':
        shipping_address = incoming_message.strip()
        request.session['shipping_address'] = shipping_address
        response_message = "Thank you. Please reply 'order' to place your order."
        request.session['step'] = 'ready_to_order'

    # Handle placing order
    elif incoming_message.lower() == "order" and step == 'ready_to_order':
        response_json = place_order(request, cart)
        response_message = response_json.content.decode("utf-8")


    # Handle order status check

    elif step == 'checking_order':

        order_id = incoming_message.strip()

        response_message = confirm_order(order_id)

        # Get the invoice PDF link

        pdf_filename = f"{order_id}_invoice.pdf"

        pdf_url = request.build_absolute_uri(f"{settings.MEDIA_URL}{pdf_filename}")

        response_message += f"\nDownload your invoice here: {pdf_url}"

        request.session['step'] = 'menu'

    else:
        response_message = "Sorry, I didn't understand that command. Please select from the menu options."

    # Send the response back to the user via Twilio
    send_twilio_message(sender, response_message)

    return JsonResponse({"message": response_message})





# bot/views.py

def handle_greetings():
    return (
        "Welcome to Davis & Shirtliff! How can we assist you today?\n"
        "1. Search Item\n"
        "2. Our Working Hours\n"
        "3. Our Branches\n"
        "4. Check Order"
    )
def send_twilio_message(to, body, media_url=None):
    # Twilio message limit
    max_message_length = 1600

    # Split the body into chunks of max_message_length
    if len(body) > max_message_length:
        messages = [body[i:i + max_message_length] for i in range(0, len(body), max_message_length)]
    else:
        messages = [body]

    # Send each message part individually
    for message_part in messages:
        client.messages.create(
            body=message_part,
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            to=to
        )

    # Send the media URL (PDF link) if provided
    if media_url:
        print(f"Sending media URL: {media_url}")  # Add this line for debugging
        client.messages.create(
            body="Please download your invoice using the following link.",
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            to=to,
            media_url=[media_url]
        )



def confirm_order(order_id):
    url = f"https://bctest.dayliff.com:7048/BC160/ODataV4/Company('KENYA')/Sales_Order?$filter=No%20eq%20%27{order_id}%27"
    headers = {"Content-Type": "application/json"}

    response = requests.get(url, headers=headers, auth=AUTH_CREDENTIALS)

    if response.status_code == 200:
        order_details = response.json().get('value', [])
        if order_details:
            order = order_details[0]
            status = order.get('Status', 'Unknown')
            total_amount = order.get('Amount_Including_VAT', 'N/A')
            response_message = (
                f"Your order {order_id} is confirmed.\n"
                f"Status: {status}\n"
                f"Total paid Amount: {total_amount:,} KES"
            )
        else:
            response_message = f"No order found with ID {order_id}."
    else:
        response_message = f"Failed to retrieve order status for {order_id}. Please try again later."

    return response_message
