from flask import Flask
from flask_sqlalchemy import SQLAlchemy  # <-- 新增
from flask_migrate import Migrate      # <-- 新增
import os  # <-- 新增

# 建立 SQLAlchemy 和 Migrate 的實例
db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # --- 資料庫設定 ---
    # 從 instance/config.py 載入設定，如果檔案不存在則忽略
    app.config.from_pyfile('config.py', silent=True)
    
    # 設定資料庫的路徑
    # app.instance_path 會指向專案根目錄下的 'instance' 資料夾
    # 我們的資料庫檔案 app.db 將會被建立在那裡
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # 確保 'instance' 資料夾存在
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass # 如果資料夾已存在，就略過

    # --- 初始化資料庫 ---
    db.init_app(app)
    migrate.init_app(app, db)

    # 註冊藍圖
    from .routes import main_routes, ocr_routes, cashier_routes
    app.register_blueprint(main_routes.bp)
    app.register_blueprint(ocr_routes.bp)
    app.register_blueprint(cashier_routes.bp)

    # 在此匯入模型，確保 Flask-Migrate 可以偵測到它們
    from . import models
    
    return app