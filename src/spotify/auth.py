import secrets
import hashlib
import base64
import webbrowser
import urllib.parse
import httpx2
import os 
import signal
import uvicorn
from fastapi import FastAPI

import json
from pathlib import Path

TOKEN_FILE = Path.home() / ".config" / "spotify" / "token.json"

def is_signed_in():
    return TOKEN_FILE.exists()

def login():
    code_verifier = secrets.token_hex(32)
    text_bytes = code_verifier.encode('utf-8')
    hashed = hashlib.sha256(text_bytes).digest()
    
    code_challenge = base64.urlsafe_b64encode(hashed).decode('utf-8').rstrip('=')

    client_id = '8efd28def12e4772815042b5e7111a5f'
    redirect_uri = 'http://127.0.0.1:8080'
    scope = 'user-read-private user-read-email'
    auth_url = "https://accounts.spotify.com/authorize"

    params = {
        'response_type': 'code',
        'client_id': client_id,
        'scope': scope,
        'code_challenge_method': 'S256',
        'code_challenge': code_challenge,
        'redirect_uri': redirect_uri,
    }

    auth_url = auth_url + "?" + urllib.parse.urlencode(params)

    app = FastAPI()
    
    codes = {
        'auth_code': None,
        'access_token': None
    }

    @app.get("/")
    async def callback(code: str):
        codes['auth_code'] = code
        url = "https://accounts.spotify.com/api/token"

        payload = {
            'client_id': client_id,
            'grant_type': 'authorization_code',
            'code': code, 
            'redirect_uri': redirect_uri,
            'code_verifier': code_verifier,
        }

        async with httpx2.AsyncClient(http2=True) as client:
            response = await client.post(url, data=payload)
            data = response.json()
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_FILE.write_text(json.dumps(data))
            codes['access_token'] = data['access_token']
        server.should_exit = True
        
        return {"message": "Login successful. You can close this tab."}

    webbrowser.open_new(auth_url)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8080))
    server.run()

    return codes['access_token']