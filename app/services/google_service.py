import os
from app import create_app
from flask import current_app
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from datetime import datetime
from googleapiclient.errors import HttpError
from sqlalchemy import func, extract
from collections import defaultdict
import requests

# (get_google_creds, get_services, find_or_create_folder 維持不變)
def get_google_creds(app): # 修改：新增 app 參數
    token_file = os.path.join(app.instance_path, "token.json") # 修改：使用 app
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets'])
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                app.logger.error(f"!!! 刷新 Google 憑證失敗: {e}") # 修改：使用 app
                return None
        else:
            app.logger.warning("!!! 找不到有效的 Google 憑證檔案。") # 修改：使用 app
            return None
    return creds

def get_services(app): # 修改：新增 app 參數
    creds = get_google_creds(app) # 修改：傳入 app
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

def find_or_create_spreadsheet(drive_service, sheets_service, folder_id, location_obj, overwrite=False):
    from app.models import SystemSetting
    now = datetime.now()
    filename_format = SystemSetting.get('sheets_filename_format', '{location_name}_{year}_業績')
    file_name = filename_format.format(
        location_name=location_obj.name,
        location_slug=location_obj.slug,
        year=now.year,
        month=f"{now.month:02d}"
    )
    response = (
        drive_service.files()
        .list(
            q=f"name='{file_name}' and '{folder_id}' in parents and trashed=false and mimeType='application/vnd.google-apps.spreadsheet'",
            # --- 修正點：移除 'sheets(properties)'，因為 Drive API 不認得這個欄位 ---
            fields="files(id)",
        )
        .execute()
    )
    files = response.get("files", [])
    
    if files:
        file_id = files[0].get("id")
        if overwrite:
            current_app.logger.warning(f"檔案 '{file_name}' 已存在，將執行覆蓋操作。正在刪除舊檔案...")
            try:
                drive_service.files().delete(fileId=file_id).execute()
                current_app.logger.info(f"成功刪除舊檔案 (ID: {file_id})。")
            except HttpError as e:
                current_app.logger.error(f"!!! 刪除舊檔案時發生錯誤: {e}")
        else:
            return file_id

    spreadsheet_metadata = {"properties": {"title": file_name}}
    spreadsheet = (
        sheets_service.spreadsheets()
        .create(body=spreadsheet_metadata, fields="spreadsheetId,sheets.properties")
        .execute()
    )
    spreadsheet_id = spreadsheet.get("spreadsheetId")
    current_app.logger.info(f"成功建立新的試算表: {file_name} (ID: {spreadsheet_id})")
    
    default_sheet = spreadsheet.get('sheets', [{}])[0]
    if default_sheet.get('properties', {}).get('title') == 'Sheet1':
        sheet_id_to_delete = default_sheet.get('properties', {}).get('sheetId')
        if sheet_id_to_delete is not None:
            try:
                delete_request = {'requests': [{'deleteSheet': {'sheetId': sheet_id_to_delete}}]}
                sheets_service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=delete_request).execute()
                current_app.logger.info("成功刪除預設的 'Sheet1' 工作表。")
            except HttpError as e:
                current_app.logger.warning(f"刪除預設工作表 'Sheet1' 時發生錯誤: {e}")

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

def ensure_sheet_with_header_exists(sheets_service, spreadsheet_id, sheet_name, header_row):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_exists = any(sheet["properties"]["title"] == sheet_name for sheet in spreadsheet.get("sheets", []))
    if not sheet_exists:
        requests = [{"addSheet": {"properties": {"title": sheet_name}}}]
        sheets_service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()
        header_body = {"values": [header_row]}
        sheets_service.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A1", valueInputOption="USER_ENTERED", body=header_body).execute()

def append_data(sheets_service, spreadsheet_id, sheet_name, data_row):
    body = {"values": [data_row]}
    sheets_service.spreadsheets().values().append(spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A1", valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS", body=body).execute()

def bulk_write_data(sheets_service, spreadsheet_id, sheet_name, data_rows):
    body = {'values': data_rows}
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A1",
        valueInputOption="USER_ENTERED", body=body
    ).execute()

def write_transaction_to_sheet_task(location_id, transaction_data, header_row):
    app = create_app()
    with app.app_context():
        from app.models import SystemSetting, Location
        from app import db
        try:
            location = db.session.get(Location, location_id)
            if not location:
                current_app.logger.error(f"!!! [背景任務] 找不到 ID 為 {location_id} 的據點。")
                return
            drive_service, sheets_service = get_services(app)
            if not drive_service: return
            folder_name = SystemSetting.get('drive_folder_name', 'Cashier_System_Reports')
            folder_id = find_or_create_folder(drive_service, folder_name)
            if not folder_id: return
            spreadsheet_id = find_or_create_spreadsheet(drive_service, sheets_service, folder_id, location)
            if not spreadsheet_id: return
            month_sheet_name = datetime.now().strftime("%Y年%m月")
            ensure_sheet_with_header_exists(sheets_service, spreadsheet_id, month_sheet_name, header_row)
            append_data(sheets_service, spreadsheet_id, month_sheet_name, transaction_data)
        except HttpError as e:
            error_details = e.content.decode('utf-8')
            current_app.logger.error(f"!!! [背景任務] Google API HTTP 錯誤: {e.resp.status} {e.resp.reason}, 詳細資訊: {error_details}")
        except Exception as e:
            current_app.logger.error(f"!!! [背景任務] 寫入交易紀錄時發生未預期的嚴重錯誤: {e}", exc_info=True)

def write_report_to_sheet_task(location_id, report_data, header_row):
    app = create_app()
    with app.app_context():
        from app.models import SystemSetting, Location
        from app import db
        try:
            location = db.session.get(Location, location_id)
            if not location:
                current_app.logger.error(f"!!! [背景任務] 找不到 ID 為 {location_id} 的據點。")
                return
            drive_service, sheets_service = get_services(app)
            if not drive_service: return
            folder_name = SystemSetting.get('drive_folder_name', 'Cashier_System_Reports')
            folder_id = find_or_create_folder(drive_service, folder_name)
            if not folder_id: return
            spreadsheet_id = find_or_create_spreadsheet(drive_service, sheets_service, folder_id, location)
            if not spreadsheet_id: return
            summary_sheet_name = "每日摘要"
            ensure_sheet_with_header_exists(sheets_service, spreadsheet_id, summary_sheet_name, header_row)
            append_data(sheets_service, spreadsheet_id, summary_sheet_name, report_data)
            update_monthly_summary(sheets_service, spreadsheet_id, location_id)
        except HttpError as e:
            error_details = e.content.decode('utf-8')
            current_app.logger.error(f"!!! [背景任務] Google API HTTP 錯誤: {e.resp.status} {e.resp.reason}, 詳細資訊: {error_details}")
        except Exception as e:
            current_app.logger.error(f"!!! [背景任務] 寫入每日摘要時發生未預期的嚴重錯誤: {e}", exc_info=True)

def update_monthly_summary(sheets_service, spreadsheet_id, location_id):
    from app.models import BusinessDay
    from app import db
    now = datetime.now()
    year, month = now.year, now.month
    monthly_stats = db.session.query(
        func.sum(BusinessDay.total_sales).label('total_sales'),
        func.sum(BusinessDay.cash_diff).label('cash_diff'),
        func.sum(BusinessDay.total_transactions).label('total_transactions'),
        func.sum(BusinessDay.total_items).label('total_items')
    ).filter(
        BusinessDay.location_id == location_id,
        extract('year', BusinessDay.date) == year,
        extract('month', BusinessDay.date) == month,
        BusinessDay.status == 'CLOSED'
    ).first()
    if not monthly_stats.total_sales:
        return
    sheet_name = "每月數據"
    header = ["月份", "總銷售額", "總帳差", "總交易筆數", "總銷售件數"]
    ensure_sheet_with_header_exists(sheets_service, spreadsheet_id, sheet_name, header)
    result = sheets_service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=sheet_name).execute()
    values = result.get('values', [])
    month_str = f"{year}-{month:02d}"
    update_row_index = -1
    for i, row in enumerate(values):
        if row and row[0] == month_str:
            update_row_index = i + 1
            break
    row_data = [
        month_str,
        monthly_stats.total_sales or 0,
        monthly_stats.cash_diff or 0,
        monthly_stats.total_transactions or 0,
        monthly_stats.total_items or 0
    ]
    if update_row_index != -1:
        range_to_update = f"'{sheet_name}'!A{update_row_index}"
        body = {'values': [row_data]}
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=range_to_update,
            valueInputOption="USER_ENTERED", body=body
        ).execute()
        current_app.logger.info(f"成功更新 '{sheet_name}' 工作表中 '{month_str}' 的數據。")
    else:
        append_data(sheets_service, spreadsheet_id, sheet_name, row_data)
        current_app.logger.info(f"成功在 '{sheet_name}' 工作表中新增 '{month_str}' 的數據。")

def rebuild_backup_task(overwrite=False):
    app = create_app()
    with app.app_context():
        from app.models import Location, BusinessDay, Transaction, SystemSetting
        from app import db
        current_app.logger.info(f"--- 開始執行完整備份任務 (Overwrite={overwrite}) ---")
        try:
            drive_service, sheets_service = get_services(app)
            if not drive_service or not sheets_service:
                current_app.logger.error("!!! 無法獲取 Google 服務，備份任務中止。")
                return
            folder_name = SystemSetting.get('drive_folder_name', 'Cashier_System_Reports')
            folder_id = find_or_create_folder(drive_service, folder_name)
            locations = Location.query.all()
            for location in locations:
                current_app.logger.info(f"正在處理據點: {location.name}")
                spreadsheet_id = find_or_create_spreadsheet(drive_service, sheets_service, folder_id, location, overwrite=overwrite)
                if not spreadsheet_id:
                    current_app.logger.warning(f"無法為據點 {location.name} 建立或找到試算表，跳過此據點。")
                    continue
                
                daily_reports = BusinessDay.query.filter_by(location_id=location.id, status='CLOSED').order_by(BusinessDay.date).all()
                if daily_reports:
                    header = ["日期", "據點", "開店準備金", "本日銷售總額", "帳面總額", "盤點現金合計", "帳差", "交易筆數", "銷售件數"]
                    ensure_sheet_with_header_exists(sheets_service, spreadsheet_id, "每日摘要", header)
                    data_rows = [header] + [[day.date.strftime("%Y-%m-%d"), location.name, day.opening_cash, day.total_sales, day.expected_cash, day.closing_cash, day.cash_diff, day.total_transactions, day.total_items] for day in daily_reports]
                    bulk_write_data(sheets_service, spreadsheet_id, "每日摘要", data_rows)
                    current_app.logger.info(f"已為 {location.name} 寫入 {len(data_rows) - 1} 筆每日摘要。")

                monthly_stats = db.session.query(
                    extract('year', BusinessDay.date).label('year'),
                    extract('month', BusinessDay.date).label('month'),
                    func.sum(BusinessDay.total_sales).label('total_sales'),
                    func.sum(BusinessDay.cash_diff).label('cash_diff'),
                    func.sum(BusinessDay.total_transactions).label('total_transactions'),
                    func.sum(BusinessDay.total_items).label('total_items')
                ).filter_by(location_id=location.id, status='CLOSED').group_by('year', 'month').order_by('year', 'month').all()
                if monthly_stats:
                    header = ["月份", "總銷售額", "總帳差", "總交易筆數", "總銷售件數"]
                    ensure_sheet_with_header_exists(sheets_service, spreadsheet_id, "每月數據", header)
                    data_rows = [header] + [[f"{stats.year}-{stats.month:02d}", stats.total_sales or 0, stats.cash_diff or 0, stats.total_transactions or 0, stats.total_items or 0] for stats in monthly_stats]
                    bulk_write_data(sheets_service, spreadsheet_id, "每月數據", data_rows)
                    current_app.logger.info(f"已為 {location.name} 寫入 {len(data_rows) - 1} 筆每月數據。")

                all_transactions = Transaction.query.join(BusinessDay).filter(BusinessDay.location_id == location.id).order_by(Transaction.timestamp).all()
                transactions_by_month = defaultdict(list)
                for trans in all_transactions:
                    month_key = trans.timestamp.strftime("%Y年%m月")
                    transactions_by_month[month_key].append(trans)
                for month_key, transactions in transactions_by_month.items():
                    header = ["時間戳", "金額", "品項數"]
                    ensure_sheet_with_header_exists(sheets_service, spreadsheet_id, month_key, header)
                    data_rows = [header] + [[trans.timestamp.strftime("%Y-%m-%d %H:%M:%S"), trans.amount, trans.item_count] for trans in transactions]
                    bulk_write_data(sheets_service, spreadsheet_id, month_key, data_rows)
                    current_app.logger.info(f"已為 {location.name} 的 {month_key} 寫入 {len(data_rows) - 1} 筆交易紀錄。")
            current_app.logger.info("--- 完整備份任務執行完畢 ---")
        except HttpError as e:
            error_details = e.content.decode('utf-8')
            current_app.logger.error(f"!!! [完整備份任務] Google API HTTP 錯誤: {e.resp.status} {e.resp.reason}, 詳細資訊: {error_details}")
        except Exception as e:
            current_app.logger.error(f"!!! [完整備份任務] 發生未預期的嚴重錯誤: {e}", exc_info=True)

def get_drive_user_info(app):
    with app.app_context():
        creds = get_google_creds(app)
        if not creds:
            return None
        try:
            userinfo_response = requests.get(
                'https://www.googleapis.com/oauth2/v1/userinfo',
                headers={'Authorization': f'Bearer {creds.token}'}
            )
            if userinfo_response.ok:
                return userinfo_response.json()
        except Exception as e:
            current_app.logger.error(f"獲取 Drive 使用者資訊時發生錯誤: {e}")
        return None