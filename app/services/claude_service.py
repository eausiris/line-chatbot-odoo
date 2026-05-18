import json
import logging
from anthropic import Anthropic
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = (
    "You are an AI sales assistant. Analyze customer messages and return JSON only. "
    "No other text outside JSON. "
    "Supported intents: search_product, add_to_cart, set_quantity, view_cart, create_quotation, greeting, other. "
    "IMPORTANT: Distinguish between add_to_cart (add more items) and set_quantity (set exact amount). "
    "Examples: "
    "'add 2 more' -> add_to_cart, quantity: 2. "
    "'set to 2' / 'change to 2' / 'I want only 2' / 'make it 2' -> set_quantity, quantity: 2. "
    "Return format: "
    "{"intent": "search_product", "confidence": 0.95, "
    ""entities": {"product_name": "", "color": "", "quantity": 1}, "
    ""reply_if_clarify": ""}"
)


async def parse_intent(user_message: str, conversation_history: list) -> dict:
    try:
        messages = list(conversation_history[-10:])
        messages.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        raw = response.content[0].text.strip()

        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip())

    except Exception as e:
        logger.error(f"Claude error: {e}")
        return {
            "intent": "other",
            "confidence": 0.0,
            "entities": {},
            "reply_if_clarify": "Please try again"
        }
