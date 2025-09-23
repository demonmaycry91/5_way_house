# app/services/backup_service.py
import os
import io
import json
import threading
import time
from datetime import datetime
from flask import current_app
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials

from ..models import SystemSetting
from .google_service import get_services
from .. import create_app # 新增這行

def backup_instance_to_drive():
    """執行備份任務：將指定的 instance/ 檔案上傳到 Google Drive。"""
    print("--- 執行 instance/ 資料夾備份任務 ---")
    
    # 在背景任務中手動建立應用程式上下文
    app = create_app()
    with app.app_context():
        drive, _ = get_services(app) # 修改：傳入 app 物件
        if not drive:
            print("備份失敗：未找到有效的 Google Drive 憑證。")
            return
            
        backup_files_json = SystemSetting.get('instance_backup_files')
        backup_files = json.loads(backup_files_json) if backup_files_json else []
        
        if not backup_files:
            print("備份失敗：未選擇任何備份檔案。")
            return
            
        folder_name = SystemSetting.get('drive_folder_name', 'Cashier_System_Reports')
        
        response = drive.files().list(
            q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive',
            fields='files(id)'
        ).execute()
        
        folder_id = None
        if response.get('files'):
            folder_id = response['files'][0]['id']
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = drive.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
            
        for filename in backup_files:
            filepath = os.path.join(current_app.instance_path, filename)
            if not os.path.exists(filepath):
                print(f"警告：找不到檔案 '{filepath}'，跳過備份。")
                continue
                
            try:
                timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                backup_filename = f"{os.path.splitext(filename)[0]}_{timestamp}{os.path.splitext(filename)[1]}"
                
                file_metadata = {
                    'name': backup_filename,
                    'parents': [folder_id]
                }
                
                media = MediaIoBaseUpload(io.FileIO(filepath, 'rb'), mimetype='application/octet-stream')
                
                drive.files().create(body=file_metadata, media_body=media, fields='id').execute()
                print(f"成功備份 '{filename}' 至 Google Drive。")
                
            except Exception as e:
                print(f"備份 '{filename}' 時發生錯誤：{e}")

class BackupScheduler(threading.Thread):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.running = True

    def run(self):
        with self.app.app_context():
            while self.running:
                frequency = SystemSetting.get('instance_backup_frequency')
                if frequency == 'interval':
                    try:
                        interval = int(SystemSetting.get('instance_backup_interval_minutes', '1440') or 1440)
                    except (ValueError, TypeError):
                        interval = 1440
                    
                    print(f"下一次備份將在 {interval} 分鐘後執行...")
                    time.sleep(interval * 60)
                    
                    if SystemSetting.get('instance_backup_frequency') == 'interval':
                        backup_instance_to_drive()
                else:
                    time.sleep(60 * 5) # 每 5 分鐘檢查一次
                    
    def stop(self):
        self.running = False
        print("備份排程器已停止。")