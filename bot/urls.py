from django.urls import path
from . import views
from .views import (
    whatsapp_webhook,
    place_order,
    confirm_order,
)

urlpatterns = [
    # Main entry point for the chatbot webhook
    path('whatsapp-webhook/', whatsapp_webhook, name='whatsapp_webhook'),

    # Endpoint to place an order (this is called within the chatbot flow, but you might expose it if needed)
    path('place-order/', place_order, name='place_order'),

    # Endpoint to confirm an order (this is also part of the chatbot flow)
    path('confirm-order/', confirm_order, name='confirm_order'),

]

