import json
import redis.asyncio as redis
from app.config import get_settings

settings = get_settings()


class SessionService:
    def __init__(self):
        self.redis = redis.from_url(settings.redis_url, decode_responses=True)
        self.ttl = settings.session_ttl_seconds

    def _key(self, user_id: str) -> str:
        return f"line_session:{user_id}"

    async def get_session(self, user_id: str) -> dict:
        try:
            data = await self.redis.get(self._key(user_id))
            if data:
                return json.loads(data)
        except Exception:
            pass
        return {"cart": [], "history": [], "last_viewed_product": None}

    async def save_session(self, user_id: str, session: dict) -> None:
        await self.redis.setex(
            self._key(user_id),
            self.ttl,
            json.dumps(session, ensure_ascii=False)
        )

    async def add_to_cart(self, user_id: str, product: dict, qty: int = 1) -> None:
        session = await self.get_session(user_id)
        for item in session["cart"]:
            if item["product_id"] == product["id"]:
                item["qty"] += qty
                await self.save_session(user_id, session)
                return
        session["cart"].append({
            "product_id": product["id"],
            "name": product["name"],
            "price_unit": product["price"],
            "qty": qty,
        })
        await self.save_session(user_id, session)

    async def clear_cart(self, user_id: str) -> None:
        session = await self.get_session(user_id)
        session["cart"] = []
        await self.save_session(user_id, session)

    async def append_history(self, user_id: str, role: str, content: str) -> None:
        session = await self.get_session(user_id)
        session["history"].append({"role": role, "content": content})
        session["history"] = session["history"][-20:]
        await self.save_session(user_id, session)


session_service = SessionService()