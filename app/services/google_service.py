import os
from app import create_app
from flask import current_app
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from datetime import datetime
# *** 優化點：匯入 HttpError 以便捕捉特定的 API 錯誤 ***
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
REPORTS_FOLDER_NAME = "Cashier_System_Reports"


def get_google_creds():
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
                current_app.logger.error(f"!!! 刷新 Google 憑證失敗: {e}")
                return None
        else:
            current_app.logger.warning("!!! 找不到有效的 Google 憑證檔案。")
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
    # (此函式邏輯不變，省略)
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
    # (此函式邏輯不變，省略)
    year = datetime.now().year
    file_name = f"{location}_{year}_transactions" # 檔名移除了 .xlsx

    response = (
        drive_service.files()
        .list(
            q=f"name='{file_name}' and '{folder_id}' in parents and trashed=false and mimeType='application/vnd.google-apps.spreadsheet'",
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
        current_app.logger.info(f"成功建立新的試算表: {file_name} (ID: {spreadsheet_id})")

        # 將檔案移動到指定資料夾
        file_metadata = drive_service.files().get(fileId=spreadsheet_id, fields='parents').execute()
        previous_parents = ",".join(file_metadata.get('parents'))
        drive_service.files().update(
            fileId=spreadsheet_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
        current_app.logger.info(f"成功將試算表移動至資料夾 ID: {folder_id}")
        return spreadsheet_id


def ensure_sheet_with_header_exists(
    sheets_service, spreadsheet_id, sheet_name, header_row
):
    # (此函式邏輯不變，省略)
    spreadsheet = (
        sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    )
    sheet_exists = any(
        sheet["properties"]["title"] == sheet_name
        for sheet in spreadsheet.get("sheets", [])
    )

    if not sheet_exists:
        current_app.logger.info(f"工作表 '{sheet_name}' 不存在，正在建立並寫入標題...")
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
        current_app.logger.info(f"成功為 '{sheet_name}' 寫入標題列")


def append_data(sheets_service, spreadsheet_id, sheet_name, data_row):
    # (此函式邏輯不變，省略)
    body = {"values": [data_row]}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()
    current_app.logger.info(f"成功將資料附加到 '{sheet_name}'")


def write_transaction_to_sheet_task(location_name, transaction_data, header_row):
    """【背景任務】將單筆交易寫入 Google Sheet。"""
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
        # *** 優化點：捕捉特定的 Google API 錯誤 ***
        except HttpError as e:
            # 解碼 Google 回傳的詳細錯誤內容
            error_details = e.content.decode('utf-8')
            current_app.logger.error(f"!!! [背景任務] Google API HTTP 錯誤: {e.resp.status} {e.resp.reason}, 詳細資訊: {error_details}")
            # 在此處可以加入更進階的處理，例如：
            # if e.resp.status in [401, 403]:
            #     # 權限問題，可能需要通知管理員重新授權
            #     notify_admin("Google API 權限失效，請重新連結帳號。")
        except Exception as e:
            current_app.logger.error(f"!!! [背景任務] 寫入交易紀錄到 Google Sheet 時發生未預期的嚴重錯誤: {e}")


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
        # *** 優化點：捕捉特定的 Google API 錯誤 ***
        except HttpError as e:
            error_details = e.content.decode('utf-8')
            current_app.logger.error(f"!!! [背景任務] Google API HTTP 錯誤: {e.resp.status} {e.resp.reason}, 詳細資訊: {error_details}")
        except Exception as e:
            current_app.logger.error(f"!!! [背景任務] 寫入每日摘要到 Google Sheet 時發生未預期的嚴重錯誤: {e}")
