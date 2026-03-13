from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
import re

from .agent import process_message
from . import evolution_api

logger = logging.getLogger(__name__)

# Estado das conversas por número de telefone (em memória)
# Em produção, usar Redis ou banco de dados
whatsapp_sessions = {}


def chat_view(request):
    """Render the main chat interface."""
    return render(request, "chat.html")


@csrf_exempt
def chat_api(request):
    """API Endpoint to receive messages from the frontend and interact with LangGraph."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_message = data.get("message", "")

            if not user_message:
                return JsonResponse({"error": "Mensagem vazia"}, status=400)

            # Retrieve or initialize session state
            current_state = request.session.get("agent_state", None)

            # Since LangChain messages aren't natively JSON serializable,
            # we need to reconstruct them or use a simpler state representation.
            if current_state:
                from langchain_core.messages import HumanMessage, AIMessage

                reconstructed_messages = []
                for msg in current_state.get("messages", []):
                    if msg["type"] == "human":
                        reconstructed_messages.append(
                            HumanMessage(content=msg["content"])
                        )
                    else:
                        reconstructed_messages.append(AIMessage(content=msg["content"]))
                current_state["messages"] = reconstructed_messages

            # Call agent
            ai_response, new_state = process_message(user_message, current_state)

            # Serialize the state back to session
            serializable_messages = []
            for msg in new_state["messages"]:
                msg_type = (
                    "human" if hasattr(msg, "type") and msg.type == "human" else "ai"
                )
                serializable_messages.append({"type": msg_type, "content": msg.content})

            new_state["messages"] = serializable_messages
            request.session["agent_state"] = new_state

            return JsonResponse({"response": ai_response})

        except Exception as e:
            print(f"Erro no chat form: {e}")
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Apenas POST"}, status=405)


# ===== WhatsApp / Evolution API Views =====


def _clean_html(text):
    """Remove tags HTML da resposta do agente para enviar texto limpo no WhatsApp."""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<b>(.*?)</b>", r"*\1*", text)  # <b> → *bold* (WhatsApp)
    text = re.sub(r"<i>(.*?)</i>", r"_\1_", text)   # <i> → _italic_ (WhatsApp)
    text = re.sub(r"<[^>]+>", "", text)              # remove outras tags
    return text.strip()


def _serialize_state(state):
    """Converte o estado do agente para formato serializável."""
    serializable = dict(state)
    serializable_messages = []
    for msg in state.get("messages", []):
        msg_type = "human" if hasattr(msg, "type") and msg.type == "human" else "ai"
        serializable_messages.append({"type": msg_type, "content": msg.content})
    serializable["messages"] = serializable_messages
    return serializable


def _deserialize_state(state_dict):
    """Reconstrói os objetos de mensagem do LangChain a partir do estado salvo."""
    from langchain_core.messages import HumanMessage, AIMessage

    restored = dict(state_dict)
    reconstructed_messages = []
    for msg in state_dict.get("messages", []):
        if msg["type"] == "human":
            reconstructed_messages.append(HumanMessage(content=msg["content"]))
        else:
            reconstructed_messages.append(AIMessage(content=msg["content"]))
    restored["messages"] = reconstructed_messages
    return restored


@csrf_exempt
def whatsapp_webhook(request):
    """
    Webhook que recebe eventos da Evolution API (MESSAGES_UPSERT).
    Processa a mensagem com o agente e envia a resposta de volta via WhatsApp.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Apenas POST"}, status=405)

    try:
        data = json.loads(request.body)
        logger.info(f"Webhook recebido: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")

        event = data.get("event")

        # Só processa eventos de mensagem nova
        if event != "messages.upsert":
            return JsonResponse({"status": "ignored", "event": event})

        message_data = data.get("data", {})

        # Ignora mensagens enviadas por nós mesmos (fromMe=True)
        key = message_data.get("key", {})
        if key.get("fromMe", False):
            return JsonResponse({"status": "ignored", "reason": "own message"})

        # Extrai o número do remetente e o texto da mensagem
        remote_jid = key.get("remoteJid", "")
        # Extrai apenas o número (remove @s.whatsapp.net)
        phone_number = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid

        # Extrai o texto - pode estar em diferentes campos dependendo do tipo
        msg_obj = message_data.get("message", {})
        user_text = (
            msg_obj.get("conversation")
            or msg_obj.get("extendedTextMessage", {}).get("text")
            or ""
        )

        if not user_text:
            logger.info(f"Mensagem sem texto de {phone_number}, ignorando.")
            return JsonResponse({"status": "ignored", "reason": "no text"})

        logger.info(f"Mensagem de {phone_number}: {user_text}")

        # Recupera ou inicializa o estado da conversa para este número
        current_state = None
        if phone_number in whatsapp_sessions:
            current_state = _deserialize_state(whatsapp_sessions[phone_number])

        # Processa a mensagem com o agente
        ai_response, new_state = process_message(user_text, current_state)

        # Salva o estado atualizado
        whatsapp_sessions[phone_number] = _serialize_state(new_state)

        # Limpa HTML e envia a resposta via WhatsApp
        clean_response = _clean_html(ai_response)
        result = evolution_api.send_text(phone_number, clean_response)

        if result["success"]:
            logger.info(f"Resposta enviada para {phone_number}")
        else:
            logger.error(f"Erro ao enviar resposta: {result.get('error')}")

        return JsonResponse({"status": "ok", "response_sent": result["success"]})

    except Exception as e:
        logger.exception(f"Erro no webhook WhatsApp: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def setup_instance(request):
    """
    Cria uma instância na Evolution API e configura o webhook.
    Acessar via GET: /api/whatsapp/setup/
    """
    # 1. Tentar criar instância (pode já existir)
    create_result = evolution_api.create_instance()
    instance_info = None

    if create_result["success"]:
        instance_info = create_result.get("data")
        logger.info("Instância criada com sucesso.")
    else:
        # Se falhou com 403/409, a instância já existe - tudo bem, continua
        logger.warning(f"Criação falhou (instância pode já existir): {create_result.get('error')}")
        instance_info = {"note": "Instância já existente, pulando criação."}

    # 2. Configurar webhook apontando para este servidor Django
    # host.docker.internal permite que o container Docker acesse o host
    webhook_url = "http://host.docker.internal:8000/api/whatsapp/webhook/"
    webhook_result = evolution_api.set_webhook(webhook_url)

    return JsonResponse({
        "status": "ok",
        "instance": instance_info,
        "webhook": webhook_result.get("data") if webhook_result["success"] else webhook_result.get("error"),
        "webhook_ok": webhook_result["success"],
        "next_step": "Acesse /api/whatsapp/qrcode/ para escanear o QR code com seu WhatsApp",
    })


def get_qrcode_view(request):
    """
    Retorna o QR code para conectar o WhatsApp.
    Acessar via GET: /api/whatsapp/qrcode/
    """
    from django.http import HttpResponse

    result = evolution_api.get_qrcode()

    if not result["success"]:
        return JsonResponse({
            "status": "error",
            "error": result.get("error"),
            "tip": "Acesse /api/whatsapp/setup/ primeiro para criar a instância.",
        }, status=500)

    qr_data = result.get("data", {})
    base64_qr = qr_data.get("base64", "")
    qr_code_string = qr_data.get("code", "")
    pairing_code = qr_data.get("pairingCode", "")
    count = qr_data.get("count", 0)

    # Se o response contém um base64, renderiza diretamente
    if base64_qr:
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Conectar WhatsApp - HC Pneus</title>
        <meta http-equiv="refresh" content="30">
        </head>
        <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;font-family:Arial,sans-serif;background:#111;color:#fff;">
            <h1>📱 Escanear QR Code</h1>
            <p>Abra o WhatsApp → Dispositivos Conectados → Conectar Dispositivo</p>
            <img src="{base64_qr}" alt="QR Code" style="width:300px;height:300px;border-radius:12px;margin:20px 0;"/>
            <p style="color:#888;">A página atualiza automaticamente a cada 30s.</p>
        </body>
        </html>
        """
        return HttpResponse(html)

    # Se tem o código QR em texto, usa JS para renderizar
    if qr_code_string:
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Conectar WhatsApp - HC Pneus</title>
        <meta http-equiv="refresh" content="30">
        <script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js"></script>
        </head>
        <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;font-family:Arial,sans-serif;background:#111;color:#fff;">
            <h1>📱 Escanear QR Code</h1>
            <p>Abra o WhatsApp → Dispositivos Conectados → Conectar Dispositivo</p>
            <canvas id="qrcode" style="border-radius:12px;margin:20px 0;"></canvas>
            {f'<p style="color:#0f0;font-size:1.5em;letter-spacing:4px;">Código: <b>{pairing_code}</b></p>' if pairing_code else ''}
            <p style="color:#888;">Tentativa: {count} | A página atualiza automaticamente.</p>
            <script>
                QRCode.toCanvas(document.getElementById('qrcode'), '{qr_code_string}', {{
                    width: 300,
                    margin: 2,
                    color: {{ dark: '#000', light: '#fff' }}
                }});
            </script>
        </body>
        </html>
        """
        return HttpResponse(html)

    # Nenhum QR disponível — pode estar conectado ou em estado intermediário
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Conectar WhatsApp - HC Pneus</title>
    <meta http-equiv="refresh" content="5">
    </head>
    <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;font-family:Arial,sans-serif;background:#111;color:#fff;">
        <h1>⏳ Aguardando QR Code...</h1>
        <p>O QR code está sendo gerado. A página atualiza automaticamente.</p>
        <p style="color:#888;">Se demorar mais de 30s, tente acessar /api/whatsapp/setup/ novamente.</p>
        <pre style="color:#666;max-width:500px;overflow:auto;">{json.dumps(qr_data, indent=2)}</pre>
    </body>
    </html>
    """
    return HttpResponse(html)


