import requests

API_KEY = "62e38cb58a8d44c583f6400576095ffb.L8PryvFRNqlkoQfO"
BASE_URL = "https://api.z.ai/api/anthropic"

MODELS_TO_TRY = [
    "glm-4.7", # We know this worked before
    "glm-4-flash-x",
    "glm-4-air",
    "glm-zero-preview",
    "claude-3-5-sonnet-20240620", # Maybe mapping
    "claude-3-haiku-20240307",
]

print("🔍 Testing Model Names on Z.ai (Anthropic Protocol)...\n")

headers = {
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json"
}

for model_name in MODELS_TO_TRY:
    print(f"👉 Trying model: '{model_name}' ...", end=" ")
    
    data = {
        "model": model_name,
        "max_tokens": 10,
        "messages": [{"role": "user", "content": "hi"}]
    }
    
    try:
        res = requests.post(f"{BASE_URL}/v1/messages", json=data, headers=headers, timeout=5)
        if res.status_code == 200:
            print("✅ OK!")
            # print(f"   Response: {res.json()}")
        else:
            err = res.json().get('error', {}).get('message', res.text)
            print(f"❌ Fail ({res.status_code}): {err}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
