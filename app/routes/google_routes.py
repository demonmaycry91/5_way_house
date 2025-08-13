import os
import json
from flask import Blueprint, redirect, url_for, session, request, current_app, flash
from flask_login import login_user
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import requests

from .. import db
from ..models import User, Role

bp = Blueprint('google', __name__, url_prefix='/google')

# --- 常數定義 ---
DRIVE_SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]
LOGIN_SCOPES = [
    'openid', 
    'https://www.googleapis.com/auth/userinfo.email', 
    'https://www.googleapis.com/auth/userinfo.profile'
]

# --- Google 使用者登入流程 ---

@bp.route('/login')
def login():
    """第一步：將使用者重新導向到 Google 的 OAuth 2.0 伺服器進行登入"""
    client_secrets_file = os.path.join(current_app.instance_path, 'client_secret.json')
    org_domain = os.getenv('ORGANIZATION_DOMAIN')

    flow = Flow.from_client_secrets_file(
        client_secrets_file,
        scopes=LOGIN_SCOPES,
        redirect_uri=url_for('google.callback', _external=True)
    )
    
    auth_url_params = {
        'access_type': 'offline',
        'include_granted_scopes': 'true',
    }
    if org_domain:
        auth_url_params['hd'] = org_domain

    authorization_url, state = flow.authorization_url(**auth_url_params)
    session['state'] = state
    return redirect(authorization_url)

@bp.route('/callback')
def callback():
    """第二步：處理來自 Google 的回呼，獲取使用者資訊並登入/註冊"""
    client_secrets_file = os.path.join(current_app.instance_path, 'client_secret.json')
    org_domain = os.getenv('ORGANIZATION_DOMAIN')

    flow = Flow.from_client_secrets_file(
        client_secrets_file,
        scopes=LOGIN_SCOPES,
        state=session['state'],
        redirect_uri=url_for('google.callback', _external=True)
    )
    
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        flash(f'無法從 Google 獲取 Token: {e}', 'danger')
        return redirect(url_for('cashier.login'))

    credentials = flow.credentials
    
    userinfo_response = requests.get(
        'https://www.googleapis.com/oauth2/v1/userinfo',
        headers={'Authorization': f'Bearer {credentials.token}'}
    )
    
    if not userinfo_response.ok:
        flash('無法從 Google 獲取使用者資訊。', 'danger')
        return redirect(url_for('cashier.login'))
        
    user_info = userinfo_response.json()
    google_id = user_info['id']
    email = user_info['email']
    
    if org_domain and not email.endswith(f'@{org_domain}'):
        flash(f'登入失敗。只允許使用 @{org_domain} 網域的帳號。', 'danger')
        return redirect(url_for('cashier.login'))

    user = User.query.filter_by(google_id=google_id).first()
    if user is None:
        user = User(
            username=email.split('@')[0],
            email=email,
            google_id=google_id
        )
        cashier_role = Role.query.filter_by(name='Cashier').first()
        if cashier_role:
            user.roles.append(cashier_role)
        
        db.session.add(user)
        db.session.commit()
        flash('已成功透過 Google 帳號註冊！管理員將會為您指派權限。', 'info')

    login_user(user)
    flash('已成功透過 Google 登入！', 'success')
    return redirect(url_for('cashier.dashboard'))


# --- Google Drive 雲端備份授權流程 ---

@bp.route('/authorize_drive')
def authorize_drive():
    """第一步：將使用者重新導向到 Google 的 OAuth 2.0 伺服器進行雲端授權"""
    client_secrets_file = os.path.join(current_app.instance_path, 'client_secret.json')

    flow = Flow.from_client_secrets_file(
        client_secrets_file,
        scopes=DRIVE_SCOPES,
        redirect_uri=url_for('google.drive_callback', _external=True)
    )
    
    # --- 修正點：加入 prompt='consent' ---
    # 這會強制 Google 每次都顯示授權畫面，並確保回傳 refresh_token
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # <-- 新增這一行
    )
    session['drive_auth_state'] = state
    return redirect(authorization_url)

@bp.route('/drive_callback')
def drive_callback():
    """第二步：處理來自 Google 的回呼，儲存雲端授權憑證"""
    client_secrets_file = os.path.join(current_app.instance_path, 'client_secret.json')
    token_file = os.path.join(current_app.instance_path, 'token.json')

    state = session['drive_auth_state']
    flow = Flow.from_client_secrets_file(
        client_secrets_file,
        scopes=DRIVE_SCOPES,
        state=state,
        redirect_uri=url_for('google.drive_callback', _external=True)
    )
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    with open(token_file, 'w') as token:
        token.write(credentials.to_json())

    flash('已成功連結至您的 Google 帳號以進行雲端備份！', 'success')
    return redirect(url_for('cashier.settings'))
