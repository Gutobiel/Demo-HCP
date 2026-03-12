from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

from .agent import process_message


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
            # For demonstration, we'll maintain state but format messages to basic dicts.
            if current_state:
                # Reconstruct HumanMessage/AIMessage objects if needed,
                # but our agent currently just appends and expects a list.
                # Let's clean the state to be safe.
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
