import os
import requests
from litellm import completion

# Config
API_KEY = "62e38cb58a8d44c583f6400576095ffb.L8PryvFRNqlkoQfO"
ZAI_BASE_OPENAI = "https://api.z.ai/v1"
ZAI_BASE_ANTHROPIC = "https://api.z.ai/api/anthropic"

print("🔍 Starting Z.ai connection tests...")

# ---------------------------------------------------------
# TEST 1: OpenAI Protocol (for Lite Mode / Pi)
# ---------------------------------------------------------
print(f"\n[TEST 1] OpenAI Protocol (via LiteLLM)")
print(f"Endpoint: {ZAI_BASE_OPENAI}")
print(f"Model: openai/glm-4-flash")

try:
    response = completion(
        model="openai/glm-4-flash",
        messages=[{"role": "user", "content": "Hello, are you GLM?"}],
        api_key=API_KEY,
        api_base=ZAI_BASE_OPENAI
    )
    print("✅ SUCCESS!")
    print(f"Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ FAILED: {e}")

# ---------------------------------------------------------
# TEST 2: Anthropic Protocol (for Pro Mode / Mac)
# ---------------------------------------------------------
print(f"\n[TEST 2] Anthropic Protocol (Raw Request)")
print(f"Endpoint: {ZAI_BASE_ANTHROPIC}/v1/messages")

headers = {
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json"
}

data = {
    "model": "glm-4.7",  # Assuming they map this, or maybe "claude-3-5-sonnet"
    "max_tokens": 1024,
    "messages": [
        {"role": "user", "content": "Hello via Anthropic protocol!"}
    ]
}

try:
    # Note: Append /v1/messages because base url usually doesn't include it in clients
    url = f"{ZAI_BASE_ANTHROPIC}/v1/messages"
    res = requests.post(url, json=data, headers=headers)
    
    if res.status_code == 200:
        print("✅ SUCCESS!")
        print(f"Response: {res.json()['content'][0]['text']}")
    else:
        print(f"❌ FAILED: Status {res.status_code}")
        print(f"Body: {res.text}")
        
except Exception as e:
    print(f"❌ EXCEPTION: {e}")
