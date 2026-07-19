import os
import urllib.request, json
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    print("Available models:")
    for m in data['models']:
        if 'generateContent' in m.get('supportedGenerationMethods', []):
            print(m['name'])
except Exception as e:
    print("Error:", e)
