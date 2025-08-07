# my_app/routes/google_routes.py (修正版)

import os
from flask import Blueprint, redirect, url_for, session, request, current_app, flash
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import json

bp = Blueprint('google', __name__, url_prefix='/google')

# 只在頂層定義真正不變的常數
SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

@bp.route('/authorize')
def authorize():
    """第一步：將使用者重新導向到 Google 的 OAuth 2.0 伺服器"""
    client_secrets_file = os.path.join(current_app.instance_path, 'client_secret.json')
    
    flow = Flow.from_client_secrets_file(
        client_secrets_file,
        scopes=SCOPES,
        redirect_uri=url_for('google.oauth2callback', _external=True)
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    session['state'] = state
    
    # --- ↓↓↓ 這就是我們新增的除錯指令 ↓↓↓ ---
    print("----------- DEBUG: Authorization URL -----------")
    print(authorization_url)
    print("----------------------------------------------")
    # --- ↑↑↑ 除錯指令結束 ↑↑↑ ---

    return redirect(authorization_url)

@bp.route('/oauth2callback')
def oauth2callback():
    """第二步：處理來自 Google 的回呼"""
    # --- 修正點：將依賴 current_app 的程式碼移入函式內 ---
    client_secrets_file = os.path.join(current_app.instance_path, 'client_secret.json')
    token_file = os.path.join(current_app.instance_path, 'token.json')
    
    state = session['state']
    flow = Flow.from_client_secrets_file(
        client_secrets_file,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for('google.oauth2callback', _external=True)
    )
    flow.fetch_token(authorization_response=request.url)

    # 將憑證儲存到檔案中
    credentials = flow.credentials
    with open(token_file, 'w') as token:
        token.write(credentials.to_json())
    
    flash('已成功連結至您的 Google 帳號！', 'success')
    return redirect(url_for('cashier.settings'))

def get_google_credentials():
    """一個輔助函式，用來讀取和刷新憑證"""
    # --- 修正點：將依賴 current_app 的程式碼移入函式內 ---
    token_file = os.path.join(current_app.instance_path, 'token.json')
    
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # 刷新後，將新的憑證存回檔案
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
        else:
            return None
            
    return creds