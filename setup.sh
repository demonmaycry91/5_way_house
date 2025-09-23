#!/bin/bash

# 這個腳本會自動化專案的啟動流程。
# 請注意，部分手動步驟仍需要您自行完成。

# 1. 建立並啟用 Python 虛擬環境
echo "--> 1. 建立並啟用 Python 虛擬環境..."
python3 -m venv .venv

# `source` 指令必須在當前 shell 中運行，才能使虛擬環境生效。
# 因此，您必須在運行腳本後手動執行這一步。
# source .venv/bin/activate
#
# 為了讓後續指令在腳本中運行，我們直接使用虛擬環境中的 python 和 flask 指令
VENV_PYTHON=.venv/bin/python
VENV_FLASK=.venv/bin/flask

# 檢查虛擬環境是否成功啟動
if [ ! -f "$VENV_PYTHON" ]; then
    echo "錯誤：虛擬環境建立失敗，請檢查 Python3 是否已安裝。終止腳本。"
    exit 1
fi
echo "成功建立虛擬環境。"


# 2. 安裝 pip-tools 並更新 pip
echo "--> 2. 安裝 pip-tools 並更新 pip..."
$VENV_PYTHON -m pip install pip-tools
$VENV_PYTHON -m pip install --upgrade pip

# 3. 編譯並安裝所有依賴套件
echo "--> 3. 編譯並安裝所有依賴套件..."
# 這裡使用 pip-compile 重新產生 requirements.txt
$VENV_PYTHON -m piptools compile requirements.in
# 安裝所有套件，然後同步環境，移除不需要的套件
$VENV_PYTHON -m pip install -r requirements.txt
# pip-sync 需要 pip-tools，所以我們確保它已安裝
$VENV_PYTHON -m piptools sync

# 4. 設定 FLASK_APP 環境變數
echo "--> 4. 設定 FLASK_APP 環境變數..."
# 將變數設定為當前會話專用，不會持久化
export FLASK_APP=run.py
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
echo "FLASK_APP 已設定為 run.py"

# 5. 執行資料庫遷移
echo "--> 5. 執行資料庫遷移..."
echo "警告：這將會刪除現有的資料庫檔案和遷移資料夾，請確認！"
# 請根據您的需求，選擇是否要保留舊資料。
rm -f instance/app.db
rm -rf migrations
$VENV_FLASK db init
$VENV_FLASK db migrate -m "Initial migration"
$VENV_FLASK db upgrade

# 6. 初始化後台角色
echo "--> 6. 初始化後台角色..."
$VENV_FLASK auth init-roles

# 7. 建立預設的管理員帳號
echo "--> 7. 建立預設的管理員帳號..."
$VENV_FLASK auth create-user root password --role Admin

echo "
=====================================================
專案初始化完成！
請手動完成以下步驟：
- 啟用虛擬環境：'source .venv/bin/activate'
- 啟動 Flask 伺服器：'flask run'
- 在另一個終端機中，啟動 RQ worker：'rq worker cashier-tasks' 或 'rq worker cashier-tasks --url redis://localhost:6379/0'
- 將 Google API 憑證 (client_secret.json 和 token.json) 放置到 instance/ 資料夾中。
=====================================================
"