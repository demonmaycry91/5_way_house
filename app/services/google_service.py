# app/services/google_service.py (循環匯入修正版)

import os
# --- [關鍵修正 1] ---
# 不再從 run.py 匯入 app，而是從 app 套件的 __init__.py 匯入 create_app 工廠函式
from app import create_app
from flask import current_app
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from datetime import datetime

# --- [關鍵修正 2] ---
# 呼叫工廠函式，為這個模組 (也就是背景 Worker) 建立一個獨立的 app 實例
# 這樣背景任務就可以透過這個 app 實例來建立自己的應用程式上下文 (app_context)
# app = create_app()

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
REPORTS_FOLDER_NAME = "Cashier_System_Reports"


def get_google_creds():
    # 這個函式內的 current_app 會在 app_context 中被正確解析
    token_file = os.path.join(current_app.instance_path, "token.json")
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                app.logger.error(f"!!! 刷新 Google 憑證失敗: {e}")
                return None
        else:
            app.logger.warning("!!! 找不到有效的 Google 憑證檔案。")
            return None
    return creds


def get_services():
    creds = get_google_creds()
    if not creds:
        return None, None
    drive_service = build("drive", "v3", credentials=creds)
    sheets_service = build("sheets", "v4", credentials=creds)
    return drive_service, sheets_service


def find_or_create_folder(drive_service, folder_name):
    response = (
        drive_service.files()
        .list(
            q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id)",
        )
        .execute()
    )
    files = response.get("files", [])
    if files:
        return files[0].get("id")
    else:
        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        folder = (
            drive_service.files().create(body=folder_metadata, fields="id").execute()
        )
        return folder.get("id")


def find_or_create_spreadsheet(drive_service, sheets_service, folder_id, location):
    year = datetime.now().year
    file_name = f"{location}_{year}_transactions.xlsx"

    response = (
        drive_service.files()
        .list(
            q=f"name='{file_name}' and '{folder_id}' in parents and trashed=false",
            fields="files(id)",
        )
        .execute()
    )
    files = response.get("files", [])
    if files:
        return files[0].get("id")
    else:
        spreadsheet_metadata = {"properties": {"title": file_name}}
        spreadsheet = (
            sheets_service.spreadsheets()
            .create(body=spreadsheet_metadata, fields="spreadsheetId")
            .execute()
        )
        spreadsheet_id = spreadsheet.get("spreadsheetId")
        app.logger.info(f"成功建立新的試算表: {file_name} (ID: {spreadsheet_id})")

        file = (
            drive_service.files().get(fileId=spreadsheet_id, fields="parents").execute()
        )
        previous_parents = ",".join(file.get("parents"))
        drive_service.files().update(
            fileId=spreadsheet_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields="id, parents",
        ).execute()
        app.logger.info(f"成功將試算表移動至資料夾 ID: {folder_id}")
        return spreadsheet_id


def ensure_sheet_with_header_exists(
    sheets_service, spreadsheet_id, sheet_name, header_row
):
    spreadsheet = (
        sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    )
    sheet_exists = any(
        sheet["properties"]["title"] == sheet_name
        for sheet in spreadsheet.get("sheets", [])
    )

    if not sheet_exists:
        app.logger.info(f"工作表 '{sheet_name}' 不存在，正在建立並寫入標題...")
        requests = [{"addSheet": {"properties": {"title": sheet_name}}}]
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()

        header_body = {"values": [header_row]}
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="USER_ENTERED",
            body=header_body,
        ).execute()
        app.logger.info(f"成功為 '{sheet_name}' 寫入標題列")


def append_data(sheets_service, spreadsheet_id, sheet_name, data_row):
    body = {"values": [data_row]}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()
    app.logger.info(f"成功將資料附加到 '{sheet_name}'")


def write_transaction_to_sheet_task(location_name, transaction_data, header_row):
    """【背景任務】將單筆交易寫入 Google Sheet。"""
    # --- [最終修正 3] ---
    # 在任務執行時，才建立 app 並推入其上下文
    app = create_app()
    with app.app_context():
        try:
            drive_service, sheets_service = get_services()
            if not drive_service:
                return

            folder_id = find_or_create_folder(drive_service, REPORTS_FOLDER_NAME)
            if not folder_id:
                return

            spreadsheet_id = find_or_create_spreadsheet(
                drive_service, sheets_service, folder_id, location_name
            )
            if not spreadsheet_id:
                return

            month_sheet_name = datetime.now().strftime("%Y年%m月")
            ensure_sheet_with_header_exists(
                sheets_service, spreadsheet_id, month_sheet_name, header_row
            )
            append_data(
                sheets_service, spreadsheet_id, month_sheet_name, transaction_data
            )
        except Exception as e:
            current_app.logger.error(f"!!! [背景任務] 寫入交易紀錄到 Google Sheet 時發生嚴重錯誤: {e}")


def write_report_to_sheet_task(location_name, report_data, header_row):
    """【背景任務】將每日摘要寫入 Google Sheet。"""
    app = create_app()
    with app.app_context():
        try:
            drive_service, sheets_service = get_services()
            if not drive_service:
                return

            folder_id = find_or_create_folder(drive_service, REPORTS_FOLDER_NAME)
            if not folder_id:
                return

            spreadsheet_id = find_or_create_spreadsheet(
                drive_service, sheets_service, folder_id, location_name
            )
            if not spreadsheet_id:
                return

            summary_sheet_name = "每日摘要"
            ensure_sheet_with_header_exists(
                sheets_service, spreadsheet_id, summary_sheet_name, header_row
            )
            append_data(sheets_service, spreadsheet_id, summary_sheet_name, report_data)
        except Exception as e:
            current_app.logger.error(f"!!! [背景任務] 寫入每日摘要到 Google Sheet 時發生嚴重錯誤: {e}")
