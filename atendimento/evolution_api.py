"""
Cliente para comunicação com a Evolution API v2.

Gerencia instâncias WhatsApp, envio de mensagens e configuração de webhooks.
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)

# Configurações obtidas do ambiente ou defaults
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
EVOLUTION_INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME", "hcpneus-bot")

def _headers():
    """Retorna os headers padrão para as requisições."""
    return {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }


def create_instance(instance_name=None):
    """
    Cria uma nova instância na Evolution API.
    POST /instance/create
    """
    name = instance_name or EVOLUTION_INSTANCE_NAME
    url = f"{EVOLUTION_API_URL}/instance/create"
    payload = {
        "instanceName": name,
        "integration": "WHATSAPP-BAILEYS",
        "qrcode": True,
    }

    try:
        resp = requests.post(url, json=payload, headers=_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Instância '{name}' criada com sucesso.")
        return {"success": True, "data": data}
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao criar instância: {e}")
        return {"success": False, "error": str(e)}

def get_qrcode(instance_name=None):
    """
    Obtém o QR code para conectar o WhatsApp.
    GET /instance/connect/{instance}
    """
    name = instance_name or EVOLUTION_INSTANCE_NAME
    url = f"{EVOLUTION_API_URL}/instance/connect/{name}"

    try:
        resp = requests.get(url, headers=_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return {"success": True, "data": data}
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao obter QR code: {e}")
        return {"success": False, "error": str(e)}


def send_text(number, text, instance_name=None):
    """
    Envia uma mensagem de texto via WhatsApp.
    POST /message/sendText/{instance}
    """
    name = instance_name or EVOLUTION_INSTANCE_NAME
    url = f"{EVOLUTION_API_URL}/message/sendText/{name}"
    payload = {
        "number": number,
        "text": text,
    }

    try:
        resp = requests.post(url, json=payload, headers=_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Mensagem enviada para {number}")
        return {"success": True, "data": data}
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao enviar mensagem para {number}: {e}")
        return {"success": False, "error": str(e)}


def set_webhook(webhook_url, instance_name=None):
    """
    Configura o webhook para receber eventos da instância.
    POST /webhook/set/{instance}
    """
    name = instance_name or EVOLUTION_INSTANCE_NAME
    url = f"{EVOLUTION_API_URL}/webhook/set/{name}"
    payload = {
        "webhook": {
            "enabled": True,
            "url": webhook_url,
            "webhookByEvents": False,
            "events": [
                "MESSAGES_UPSERT",
            ],
        }
    }

    try:
        resp = requests.post(url, json=payload, headers=_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Webhook configurado: {webhook_url}")
        return {"success": True, "data": data}
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao configurar webhook: {e}")
        return {"success": False, "error": str(e)}
