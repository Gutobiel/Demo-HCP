from django.urls import path
from . import views

urlpatterns = [
    path("", views.chat_view, name="chat"),
    path("api/chat/", views.chat_api, name="chat_api"),
    # WhatsApp / Evolution API
    path("api/whatsapp/webhook/", views.whatsapp_webhook, name="whatsapp_webhook"),
    path("api/whatsapp/setup/", views.setup_instance, name="whatsapp_setup"),
    path("api/whatsapp/qrcode/", views.get_qrcode_view, name="whatsapp_qrcode"),
]

