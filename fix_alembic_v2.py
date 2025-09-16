import sqlite3

try:
    conn = sqlite3.connect('instance/app.db')
    cursor = conn.cursor()
    
    # 步驟 1: 清空 alembic_version 表格中的所有舊紀錄
    cursor.execute("DELETE FROM alembic_version")
    
    # 步驟 2: 插入正確的最新版本 ID
    # 確保這裡的 ID '22d1e8b77d0b' 與您 migrations/versions/ 資料夾中最新的檔案名稱相符
    cursor.execute("INSERT INTO alembic_version (version_num) VALUES ('22d1e8b77d0b')")
    
    conn.commit()
    print("資料庫遷移版本已成功更新為 22d1e8b77d0b")
except sqlite3.Error as e:
    print(f"錯誤：無法寫入資料庫，請確認檔案未被鎖定。錯誤訊息: {e}")
finally:
    if conn:
        conn.close()