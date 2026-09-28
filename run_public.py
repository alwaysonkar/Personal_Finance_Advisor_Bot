import os

from dotenv import load_dotenv
from pyngrok import conf, ngrok

from app import app

load_dotenv()

PORT = 5000

token = os.getenv("NGROK_AUTHTOKEN")
if not token:
    raise SystemExit("NGROK_AUTHTOKEN is missing in .env")

conf.get_default().auth_token = token
tunnel = ngrok.connect(PORT)
print("Public URL:", tunnel.public_url)

# debug=False, the reloader breaks the ngrok tunnel
app.run(port=PORT, debug=False)
