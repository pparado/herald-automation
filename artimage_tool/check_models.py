import os
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("--- AVAILABLE MODELS FOR YOUR KEY ---")
for m in client.models.list():
    # We only care about models that can generate images
    if 'generate_images' in m.supported_actions or 'generateImage' in m.supported_actions or 'image' in m.name.lower():
        print(f"MODEL NAME: {m.name}")
        print(f"SUPPORTED ACTIONS: {m.supported_actions}\n")