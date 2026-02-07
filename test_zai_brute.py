import requests
from litellm import completion

API_KEY = "62e38cb58a8d44c583f6400576095ffb.L8PryvFRNqlkoQfO"

# Candidates for OpenAI-compatible base URL
OPENAI_BASES = [
    "https://api.z.ai/v1",
    "https://api.z.ai/api/openai/v1", # Try this
    "https://api.z.ai/api/v1",
    "https://open.bigmodel.cn/api/paas/v4",
]

# Candidates for Anthropic-compatible base URL
ANTHROPIC_BASES = [
    "https://api.z.ai/api/anthropic",
    "https://api.z.ai/v1",
]

print("🔍 BRUTE-FORCE URL CHECKER\n")

# --- CHECK OPENAI PROVIDER (for LiteLLM) ---
print("--- [1] Checking OpenAI Protocol (LiteLLM) ---")
for base in OPENAI_BASES:
    print(f"Trying base: {base} ...", end=" ")
    try:
        response = completion(
            model="openai/glm-4-flash",
            messages=[{"role": "user", "content": "hi"}],
            api_key=API_KEY,
            api_base=base
        )
        print("✅ WORKED!")
        print(f"   Response: {response.choices[0].message.content}\n")
        break
    except Exception as e:
        print("❌ Failed")
        # print(f"   Error: {e}") 

# --- CHECK ANTHROPIC PROVIDER (Raw Requests) ---
print("--- [2] Checking Anthropic Protocol ---")
headers = {
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json"
}
data = {
    "model": "glm-4.7", 
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "hi"}]
}

for base in ANTHROPIC_BASES:
    url = f"{base}/v1/messages"
    print(f"Trying URL: {url} ...", end=" ")
    try:
        res = requests.post(url, json=data, headers=headers, timeout=5)
        if res.status_code == 200:
            print("✅ WORKED!")
            print(f"   Response: {res.json()['content'][0]['text']}\n")
            break
        else:
            print(f"❌ Status {res.status_code}")
            # print(f"   Body: {res.text[:100]}")
    except Exception as e:
        print(f"❌ Error: {e}")
