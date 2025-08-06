from . import db  # 從 my_app 的 __init__.py 中匯入 db 實例
from datetime import datetime

# 為了避免與 Flask-Login 的 UserMixin 衝突，我們可以將我們的 User 模型改名
# 或者在這裡先這樣定義，之後再整合 Flask-Login
class User(db.Model):
    """使用者模型：用於登入驗證"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False) # 密碼將會被加密儲存

    def __repr__(self):
        return f'<User {self.username}>'

class BusinessDay(db.Model):
    """營業日模型：記錄每一天的完整營運資訊"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(100), nullable=False) # 營業據點名稱
    location_notes = db.Column(db.String(200), nullable=True) # 據點備註
    
    # 狀態：NOT_STARTED (尚未開帳), OPEN (營業中), CLOSED (已日結)
    status = db.Column(db.String(20), nullable=False, default='NOT_STARTED')
    
    # 財務數據
    opening_cash = db.Column(db.Float, nullable=False) # 開店準備金
    total_sales = db.Column(db.Float, default=0.0) # 本日銷售總額
    closing_cash = db.Column(db.Float, nullable=True) # 盤點現金合計 (日結時填寫)
    expected_cash = db.Column(db.Float, nullable=True) # 帳面總額 (開店+銷售)
    cash_diff = db.Column(db.Float, nullable=True) # 帳差
    
    # 業績統計
    total_items = db.Column(db.Integer, default=0) # 銷售件數
    total_transactions = db.Column(db.Integer, default=0) # 交易筆數
    
    # 現金盤點明細 (以 JSON 格式的字串儲存)
    cash_breakdown = db.Column(db.Text, nullable=True)
    
    # 建立與交易紀錄的一對多關聯
    transactions = db.relationship('Transaction', backref='business_day', lazy=True)

    def __repr__(self):
        return f'<BusinessDay {self.date} - {self.location}>'

class Transaction(db.Model):
    """交易紀錄模型：記錄每一筆顧客交易"""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False) # 單筆成交金額
    item_count = db.Column(db.Integer, nullable=False) # 單筆銷售件數
    
    # 建立與營業日的多對一外鍵關聯
    business_day_id = db.Column(db.Integer, db.ForeignKey('business_day.id'), nullable=False)

    def __repr__(self):
        return f'<Transaction {self.id} - Amount: {self.amount}>'