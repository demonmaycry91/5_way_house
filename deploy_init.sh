#!/bin/bash

# 確保腳本在任何指令失敗時都會終止
set -e

echo "--> 安裝所有相依套件"
pip install -r requirements.txt

echo "--> 執行資料庫遷移"
# 如果 migrations 資料夾不存在，則執行 flask db init
# 雖然這個資料夾在 Git 中，但為了保險起見，這段程式碼可以確保它在所有環境中都存在。
if [ ! -d "migrations" ]; then
    echo "migrations 資料夾不存在，執行 flask db init..."
    flask db init
fi

# 執行資料庫升級
flask db upgrade

echo "--> 初始化後台角色與管理員帳號"
flask auth init-roles
flask auth create-user root password --role Admin

echo "部署建置與初始化設定完成。"