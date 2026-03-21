"""
Cliente para comunicação com a Evolution API v2.

Gerencia instâncias WhatsApp, envio de mensagens e configuração de webhooks.
"""

import os
import base64
import requests
import logging

logger = logging.getLogger(__name__)

# Configurações obtidas do ambiente ou defaults
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
EVOLUTION_INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME", "hcpneus-bot")

def _headers():
    """Retorna os headers padrão para as requisições."""
    headers = {
        "Content-Type": "application/json",
    }
    if EVOLUTION_API_KEY and EVOLUTION_API_KEY.startswith("ey"):
        headers["Authorization"] = f"Bearer {EVOLUTION_API_KEY}"
    else:
        headers["apikey"] = EVOLUTION_API_KEY
    return headers


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
    """
    name = instance_name or EVOLUTION_INSTANCE_NAME
    if "zdg.com.br" in EVOLUTION_API_URL:
        # ZDG API External Wrapper Abstract URL
        url = EVOLUTION_API_URL
        payload = {
            "number": number,
            "body": text,
            "externalKey": "bot_reply"
        }
    else:
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


def send_image(number, image_path, caption="", instance_name=None):
    """
    Envia uma imagem via WhatsApp a partir de um arquivo local.
    ZDG: multipart form-data (upload de arquivo direto).
    Evolution Local: base64 no JSON.
    """
    name = instance_name or EVOLUTION_INSTANCE_NAME

    if "zdg.com.br" in EVOLUTION_API_URL:
        # ZDG usa multipart form-data com upload de arquivo
        url = EVOLUTION_API_URL
        
        try:
            with open(image_path, "rb") as f:
                files = {
                    "media": ("produto.png", f, "image/png")
                }
                data = {
                    "number": number,
                    "body": caption if caption else "📸",
                    "externalKey": "bot_image",
                    "isClosed": "false"
                }
                # Para multipart, não enviar Content-Type no header (requests seta automaticamente)
                headers = {
                    "Authorization": f"Bearer {EVOLUTION_API_KEY}"
                }
                resp = requests.post(url, files=files, data=data, headers=headers, timeout=30)
                print(f"ZDG send_image response: status={resp.status_code}, body={resp.text[:500]}")
                resp.raise_for_status()
                result = resp.json()
                logger.info(f"Imagem enviada para {number} via ZDG")
                return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"Erro ao enviar imagem para {number} via ZDG: {e}")
            return {"success": False, "error": str(e)}
    else:
        # Evolution API local usa base64 no JSON
        try:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Erro ao ler arquivo de imagem {image_path}: {e}")
            return {"success": False, "error": str(e)}

        url = f"{EVOLUTION_API_URL}/message/sendMedia/{name}"
        payload = {
            "number": number,
            "mediatype": "image",
            "caption": caption,
            "media": f"data:image/png;base64,{image_data}",
            "fileName": "produto.png"
        }

        try:
            resp = requests.post(url, json=payload, headers=_headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Imagem enviada para {number}")
            return {"success": True, "data": data}
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao enviar imagem para {number}: {e}")
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
