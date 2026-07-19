import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq()

models = client.models.list()
for m in models.data:
    print(m.id)
