from flask import Flask


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # 從 instance/config.py 載入設定，如果檔案不存在則忽略
    app.config.from_pyfile('config.py', silent=True)

    # 註冊藍圖
    from .routes import main_routes, ocr_routes, cashier_routes
    app.register_blueprint(main_routes.bp)
    app.register_blueprint(ocr_routes.bp)
    app.register_blueprint(cashier_routes.bp)

    return app
