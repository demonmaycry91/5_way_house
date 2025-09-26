#!/bin/bash

# 確保腳本在任何指令失敗時都會終止
set -e

echo "--> 安裝所有相依套件"
pip install -r requirements.txt

echo "--> 執行資料庫遷移"
# 如果 migrations 資料夾不存在，則先初始化
if [ ! -d "migrations" ]; then
    echo "migrations 資料夾不存在，執行 flask db init..."
    flask db init
fi

# 自動產生初始遷移腳本
echo "產生初始遷移腳本..."
# 這裡使用 --autogenerate 來自動產生腳本，並指定訊息
flask db migrate -m "Initial migration"

# 執行資料庫升級
echo "套用資料庫遷移..."
flask db upgrade

echo "--> 初始化後台角色與管理員帳號"
flask auth init-roles
flask auth create-user root password --role Admin

echo "部署建置與初始化設定完成。"