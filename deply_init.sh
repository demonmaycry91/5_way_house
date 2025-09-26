#!/bin/bash

# 安裝所有相依套件
pip install -r requirements.txt

# 執行資料庫遷移
flask db upgrade

# 初始化後台角色 (只需要執行一次)
flask auth init-roles

# 建立預設管理員帳號 (只需要執行一次)
flask auth create-user root password --role Admin

echo "初始化設定完成。"