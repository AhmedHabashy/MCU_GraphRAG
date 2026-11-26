"""Client for OpenRouter's OpenAI-compatible embeddings API.

This is the only module that knows the model provider. Needs OPENROUTER_API_KEY and
EMBEDDING_MODEL in .env (see .env.example). The key is sent only in the Authorization header;
errors name the URL and the provider's message, never the key or the request body.
"""

from dotenv import dotenv_values

from src.graph.neo4j_db import ENV_PATH
from src.utils import JsonHttpClient

OPENROUTER_API = "https://openrouter.ai/api/v1"
SETTINGS = ("OPENROUTER_API_KEY", "EMBEDDING_MODEL")
EMBED_BATCH = 100        # texts per embeddings request


class OpenRouterClient(JsonHttpClient):
    def __init__(self, api_key, embedding_model, session=None, **kwargs):
        super().__init__(session=session, **kwargs)
        self.session.headers["Authorization"] = f"Bearer {api_key}"
        self.embedding_model = embedding_model

    def _post(self, path, body):
        url = f"{OPENROUTER_API}{path}"
        reply = self.post_json(url, body)
        if "error" in reply:
            error = reply["error"]
            raise RuntimeError(f"{url} returned error {error.get('code')}: {str(error.get('message'))[:300]}")
        return reply

    def embed(self, texts, batch_size=EMBED_BATCH):
        """One vector per text, in input order."""
        vectors = []
        for start in range(0, len(texts), batch_size):
            reply = self._post("/embeddings", {"model": self.embedding_model, "input": texts[start:start + batch_size]})
            vectors += [d["embedding"] for d in sorted(reply["data"], key=lambda d: d["index"])]
        return vectors


def from_env(env_path=ENV_PATH):
    values = dotenv_values(env_path)
    missing = [name for name in SETTINGS if not values.get(name)]
    if missing:
        raise RuntimeError(f"Missing from .env: {', '.join(missing)} (see .env.example)")
    return OpenRouterClient(values["OPENROUTER_API_KEY"], values["EMBEDDING_MODEL"])
