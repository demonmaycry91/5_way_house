import sqlite3

try:
    conn = sqlite3.connect('instance/app.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE alembic_version SET version_num = '22d1e8b77d0b'")
    conn.commit()
    print("資料庫遷移版本已成功更新為 22d1e8b77d0b")
except sqlite3.OperationalError as e:
    print(f"錯誤：無法寫入資料庫，請確認檔案未被鎖定，錯誤訊息: {e}")
finally:
    if conn:
        conn.close()