from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
import re

from .hc_agent import HCPneusAI
from . import evolution_api
from .knowledge_base import popula_lancedb

logger = logging.getLogger(__name__)

# Garantir que a base de conhecimento vetorial está pronta (LanceDB)
# Em produção, isso deveria rodar uma vez no setup do projeto
try:
    popula_lancedb()
except Exception as e:
    logger.warning(f"Aviso ao popular LanceDB: {e}")

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
            
            # Criar agente com a sessão persistente
            agent = HCPneusAI.build_agent(session_id=session_id)
            
            # Processar mensagem (Agno retorna um run_response)
            run_response = agent.run(user_message)
            response_text = run_response.content
            
            return JsonResponse({"response": response_text})
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
            # A estrutura da Evolution API v2 para MESSAGES_UPSERT
            if data.get("event") == "messages.upsert":
                msg_info = data.get("data", {})
                is_from_me = msg_info.get("key", {}).get("fromMe")
                
                if is_from_me:
                    return JsonResponse({"status": "ignored_self"})

                remote_jid = msg_info.get("key", {}).get("remoteJid")
                # Extrair o número sem o @s.whatsapp.net
                phone_number = remote_jid.split("@")[0]
                
                # Texto da mensagem (pode estar em message.conversation ou extendedTextMessage)
                message_content = msg_info.get("message", {})
                user_text = message_content.get("conversation") or \
                            message_content.get("extendedTextMessage", {}).get("text")

                if not user_text:
                    return JsonResponse({"status": "no_text"})

                logger.info(f"Mensagem recebida de {phone_number}: {user_text}")

                logger.info(f"Mensagem recebida de {phone_number}: {user_text}")

                # Criar agente com a sessão persistente (número do telefone)
                agent = HCPneusAI.build_agent(session_id=phone_number)
                
                # Processar com o agente
                run_response = agent.run(user_text)
                ai_response = run_response.content

                # Enviar resposta de volta via Evolution API
                evolution_api.send_text(phone_number, ai_response)

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