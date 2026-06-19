from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
import re
import time

from .agent import process_message
from . import evolution_api

logger = logging.getLogger(__name__)

# Memória temporária para estado das conversas (Dicionário por número de telefone ou session id)
whatsapp_sessions = {}

def chat_view(request):
    """Render the main chat interface."""
    return render(request, "chat.html")

@csrf_exempt
def chat_api(request):
    """API endpoint for the web chat."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_message = data.get("message")
            session_id = data.get("session_id", "web-default")
            
            # Recuperar estado da sessão (ou criar novo)
            session_state = whatsapp_sessions.get(session_id, {})
            
            response_messages, new_state = process_message(user_message, session_state)
            
            # Salvar estado atualizado
            whatsapp_sessions[session_id] = new_state
            
            # Para o web chat, retornar a primeira mensagem de texto
            # e indicar se há imagens pendentes
            text_response = ""
            images = []
            for msg in response_messages:
                if msg["type"] == "text":
                    text_response = msg["content"]
                elif msg["type"] == "image":
                    images.append({"caption": msg.get("caption", "")})
            
            return JsonResponse({"response": text_response, "images": images})
        except Exception as e:
            logger.error(f"Erro na chat_api: {e}")
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Method not allowed"}, status=405)

@csrf_exempt
def whatsapp_webhook(request):
    """Webhook para receber mensagens da Evolution API."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            print("\n========== WEBHOOK ZDG ==========")
            print(json.dumps(data, indent=2))
            print("=================================\n")
            
            # Suporta ZDG (method) ou Evolution Local (event)
            is_zdg = "method" in data
            event_type = data.get("method") if is_zdg else data.get("event")

            if event_type in ["message", "messages.upsert"]:
                msg_info = data.get("msg", {}) if is_zdg else data.get("data", {})
                is_from_me = msg_info.get("key", {}).get("fromMe")
                
                if is_from_me:
                    return JsonResponse({"status": "ignored_self"})

                # ZDG usa "sender_pn" ou "peer_recipient_pn" para o número. Evolution usa "remoteJid".
                key_info = msg_info.get("key", {})
                if is_zdg:
                    remote_raw = key_info.get("sender_pn") or key_info.get("peer_recipient_pn") or key_info.get("remoteJid", "")
                else:
                    remote_raw = key_info.get("remoteJid", "")
                    
                phone_number = remote_raw.split("@")[0] if remote_raw else ""
                
                # Guard: Se não tem número de telefone, ignorar
                if not phone_number:
                    print(f"AVISO: Número de telefone vazio. remote_raw='{remote_raw}', key_info={key_info}")
                    return JsonResponse({"status": "no_phone"})
                
                # Texto da mensagem (pode estar em message.conversation ou extendedTextMessage)
                message_content = msg_info.get("message", {})
                user_text = message_content.get("conversation") or \
                            message_content.get("extendedTextMessage", {}).get("text")

                if not user_text:
                    return JsonResponse({"status": "no_text"})

                logger.info(f"Mensagem recebida de {phone_number}: {user_text}")
                print(f">>> Processando mensagem de {phone_number}: {user_text}")

                # Recuperar ou iniciar estado do agente para este número
                current_state = whatsapp_sessions.get(phone_number, {})
                
                # Processar com o agente
                response_messages, next_state = process_message(user_text, current_state)
                
                # Salvar estado
                whatsapp_sessions[phone_number] = next_state

                # Enviar cada mensagem de resposta em sequência
                for msg in response_messages:
                    if msg["type"] == "text":
                        evolution_api.send_text(phone_number, msg["content"])
                    elif msg["type"] == "image":
                        evolution_api.send_image(phone_number, msg["path"], msg.get("caption", ""))
                    
                    # Pequeno delay entre mensagens para manter ordem no WhatsApp
                    if len(response_messages) > 1:
                        time.sleep(1)

            return JsonResponse({"status": "success"})
        except Exception as e:
            logger.error(f"Erro no webhook: {e}")
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Method not allowed"}, status=405)

def setup_instance(request):
    """View auxiliar para criar instância e configurar webhook."""
    instance_res = evolution_api.create_instance()
    
    # URL do webhook (usando host.docker.internal para alcançar o Django se a Evolution estiver no Docker)
    webhook_url = "http://host.docker.internal:8000/api/whatsapp/webhook/"
    webhook_res = evolution_api.set_webhook(webhook_url)
    
    return JsonResponse({
        "instance": instance_res,
        "webhook": webhook_res
    })

def get_qrcode_view(request):
    """View para mostrar o QR Code de conexão."""
    qr_res = evolution_api.get_qrcode()
    if qr_res.get("success"):
        # Se retornar base64, renderizar uma página simples
        qr_data = qr_res.get("data", {})
        return render(request, "qrcode.html", {"qr_data": qr_data})
    return JsonResponse(qr_res)

def evolution_api_config(request):
    """Mostra configurações da Evolution API."""
    api_key = evolution_api.EVOLUTION_API_KEY
    data = {
        "url": evolution_api.EVOLUTION_API_URL,
        "instance": evolution_api.EVOLUTION_INSTANCE_NAME,
        "api_key": "***" + str(api_key)[-4:] if api_key else None
    }
    return JsonResponse(data)