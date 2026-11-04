import httpx
from app.core.config import settings

url = "https://openrouter.ai/api/v1/key"

headers = {
    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"
}

try:
    response = httpx.get(url, headers=headers, timeout=20)

    if response.status_code == 200:
        data = response.json()["data"]

        print("OpenRouter connection successful!")
        print("Key label:", data.get("label"))
        print("Free tier:", data.get("is_free_tier"))
        print("Usage:", data.get("usage"))
        print("Remaining limit:", data.get("limit_remaining"))

    elif response.status_code == 401:
        print("Authentication failed. Check your API key.")

    else:
        print("Request failed:", response.status_code)
        print(response.text)

except httpx.RequestError as error:
    print("Connection error:", error)