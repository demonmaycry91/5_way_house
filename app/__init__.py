from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
import os
from dotenv import load_dotenv

# 載入 .env 檔案中的環境變數
load_dotenv()

# 建立 SQLAlchemy 和 Migrate 的實例
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'cashier.login'


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # --- [關鍵修正] ---
    # 我們不再依賴 .env 中的 DATABASE_URL，而是以程式碼來確保路徑永遠正確。

    # 1. 確保 'instance' 資料夾存在。
    #    app.instance_path 會自動找到專案根目錄旁的 instance 文件夾的絕對路徑。
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass # 如果資料夾已存在，就略過

    # 2. 根據 instance_path 動態建立資料庫檔案的絕對路徑
    db_path = os.path.join(app.instance_path, 'app.db')

    # 3. 使用這個絕對路徑來設定資料庫 URI
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    
    # 從 .env 讀取 SECRET_KEY
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-fallback-secret-key')
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


    # --- 初始化資料庫 ---
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # 註冊藍圖
    from .routes import main_routes, ocr_routes, cashier_routes, google_routes, admin_routes
    app.register_blueprint(main_routes.bp)
    app.register_blueprint(ocr_routes.bp)
    app.register_blueprint(cashier_routes.bp)
    app.register_blueprint(google_routes.bp)
    app.register_blueprint(admin_routes.bp)

    # 在此匯入模型，確保 Flask-Migrate 可以偵測到它們
    from . import models

    # 註冊指令
    from . import auth_commands
    auth_commands.init_app(app)

    return app
