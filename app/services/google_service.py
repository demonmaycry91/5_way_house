# my_app/services/google_service.py (最終修正版)

import os
from flask import current_app
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from datetime import datetime

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
REPORTS_FOLDER_NAME = 'Cashier_System_Reports'

def get_google_creds():
    token_file = os.path.join(current_app.instance_path, 'token.json')
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                print(f"!!! 刷新 Google 憑證失敗: {e}")
                return None
        else:
            print("!!! 找不到有效的 Google 憑證檔案。")
            return None
    return creds

def get_services():
    creds = get_google_creds()
    if not creds:
        return None, None
    drive_service = build('drive', 'v3', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    return drive_service, sheets_service

def find_or_create_folder(drive_service, folder_name):
    response = drive_service.files().list(q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false", fields='files(id)').execute()
    files = response.get('files', [])
    if files:
        return files[0].get('id')
    else:
        folder_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
        folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
        return folder.get('id')

def find_or_create_spreadsheet(drive_service, sheets_service, folder_id, location):
    year = datetime.now().year
    file_name = f"{location}_{year}_transactions.xlsx"
    
    response = drive_service.files().list(q=f"name='{file_name}' and '{folder_id}' in parents and trashed=false", fields='files(id)').execute()
    files = response.get('files', [])
    if files:
        return files[0].get('id')
    else:
        # --- ↓↓↓ 這就是我們的修正點 ↓↓↓ ---
        # 1. 先建立試算表 (不指定 parents)
        spreadsheet_metadata = {'properties': {'title': file_name}}
        spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet_metadata, fields='spreadsheetId').execute()
        spreadsheet_id = spreadsheet.get('spreadsheetId')
        print(f"成功建立新的試算表: {file_name} (ID: {spreadsheet_id})")

        # 2. 再用 Drive API 將檔案移動到指定資料夾
        file = drive_service.files().get(fileId=spreadsheet_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents'))
        drive_service.files().update(
            fileId=spreadsheet_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
        print(f"成功將試算表移動至資料夾 ID: {folder_id}")
        return spreadsheet_id
        # --- ↑↑↑ 修正結束 ↑↑↑ ---

def ensure_sheet_with_header_exists(sheets_service, spreadsheet_id, sheet_name, header_row):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_exists = any(sheet['properties']['title'] == sheet_name for sheet in spreadsheet.get('sheets', []))
    
    if not sheet_exists:
        print(f"工作表 '{sheet_name}' 不存在，正在建立並寫入標題...")
        requests = [{'addSheet': {'properties': {'title': sheet_name}}}]
        sheets_service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': requests}).execute()
        
        header_body = {'values': [header_row]}
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A1",
            valueInputOption='USER_ENTERED', body=header_body
        ).execute()
        print(f"成功為 '{sheet_name}' 寫入標題列")

def append_data(sheets_service, spreadsheet_id, sheet_name, data_row):
    body = {'values': [data_row]}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A1",
        valueInputOption='USER_ENTERED', insertDataOption='INSERT_ROWS', body=body
    ).execute()
    print(f"成功將資料附加到 '{sheet_name}'")

def write_transaction_to_sheet(app_context, location, transaction_data, header_row):
    """【主要呼叫函式】將單筆交易寫入 Google Sheet (設計為可在背景執行緒中運作)"""
    with app_context:
        try:
            drive_service, sheets_service = get_services()
            if not drive_service: return

            folder_id = find_or_create_folder(drive_service, REPORTS_FOLDER_NAME)
            if not folder_id: return

            spreadsheet_id = find_or_create_spreadsheet(drive_service, sheets_service, folder_id, location)
            if not spreadsheet_id: return

            month_sheet_name = datetime.now().strftime('%Y年%m月')
            ensure_sheet_with_header_exists(sheets_service, spreadsheet_id, month_sheet_name, header_row)
            append_data(sheets_service, spreadsheet_id, month_sheet_name, transaction_data)
        except Exception as e:
            print(f"!!! [背景任務] 寫入交易紀錄到 Google Sheet 時發生嚴重錯誤: {e}")

def write_report_to_sheet(app_context, location, report_data, header_row):
    """【主要呼叫函式】將每日摘要寫入 Google Sheet (設計為可在背景執行緒中運作)"""
    with app_context:
        try:
            drive_service, sheets_service = get_services()
            if not drive_service: return

            folder_id = find_or_create_folder(drive_service, REPORTS_FOLDER_NAME)
            if not folder_id: return
            
            spreadsheet_id = find_or_create_spreadsheet(drive_service, sheets_service, folder_id, location)
            if not spreadsheet_id: return

            summary_sheet_name = '每日摘要'
            ensure_sheet_with_header_exists(sheets_service, spreadsheet_id, summary_sheet_name, header_row)
            append_data(sheets_service, spreadsheet_id, summary_sheet_name, report_data)
        except Exception as e:
            print(f"!!! [背景任務] 寫入每日摘要到 Google Sheet 時發生嚴重錯誤: {e}")