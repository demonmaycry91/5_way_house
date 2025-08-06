from flask import render_template, request, flash, redirect, url_for, Blueprint
from flask_login import login_user, logout_user, login_required, current_user
from ..models import User, BusinessDay, Transaction # <-- 新增匯入 BusinessDay
from .. import db, login_manager
from datetime import date # <-- 新增匯入 date

# 1. 定義藍圖 (這是您原本就有的，保持不變)
bp = Blueprint('cashier', __name__, url_prefix='/cashier')


# 2. 定義 user_loader，它需要從 my_app/__init__.py 匯入 login_manager
@login_manager.user_loader
def load_user(user_id):
    """Flask-Login 需要這個函式來知道如何根據 user_id 找到使用者物件"""
    return User.query.get(int(user_id))



# 3. 定義路由，並使用 @login_required 保護需要登入的頁面
# @bp.route('/')
# @login_required
# def cashier_page():
#     return f"<h1>歡迎, {current_user.username}!</h1><a href='{url_for('cashier.logout')}'>點此登出</a>"

@bp.route('/dashboard')
@login_required
def dashboard():
    """每日營運儀表板"""
    today = date.today()

    # --- ↓↓↓ 修改點在這裡 ↓↓↓ ---
    # 更新據點列表，將特賣會改名並新增「其他」
    LOCATIONS = ['本舖', '瘋衣舍', '特賣會 1', '特賣會 2', '其他']
    # --- ↑↑↑ 修改完成 ↑↑↑ ---
    
    locations_status = {}

    for location_name in LOCATIONS:
        # 查詢今天、此據點的營業日紀錄
        business_day = BusinessDay.query.filter_by(date=today, location=location_name).first()
        
        status_info = {}
        if business_day is None:
            # 尚未開帳
            status_info = {
                'status': 'NOT_STARTED',
                'status_text': '尚未開帳',
                'message': '點擊以開始本日營業作業。',
                'badge_class': 'bg-secondary',
                'url': url_for('cashier.start_day', location=location_name)
            }
        elif business_day.status == 'OPEN':
            # 營業中
            status_info = {
                'status': 'OPEN',
                'status_text': '營業中',
                'message': f"本日銷售額: ${business_day.total_sales:,.0f}",
                'badge_class': 'bg-success',
                'url': url_for('cashier.pos', location=location_name)
            }
        elif business_day.status == 'CLOSED':
            # 已日結
            status_info = {
                'status': 'CLOSED',
                'status_text': '已日結',
                'message': '本日帳務已結算，僅供查閱。',
                'badge_class': 'bg-primary',
                'url': url_for('cashier.view_report', location=location_name)
            }
        
        locations_status[location_name] = status_info

    return render_template('cashier/dashboard.html', 
                           today_date=today.strftime('%Y-%m-%d'), 
                           locations_status=locations_status)

@bp.route('/start_day/<location>', methods=['GET', 'POST'])
@login_required
def start_day(location):
    """處理開店作業的表單顯示與提交"""
    today = date.today()

    # 檢查今天此據點是否已經開店，防止重複操作
    existing_day = BusinessDay.query.filter_by(date=today, location=location).first()
    if existing_day:
        flash(f'據點 "{location}" 今日已開帳或已日結，無法重複操作。', 'warning')
        return redirect(url_for('cashier.dashboard'))

    if request.method == 'POST':
        try:
            # 從表單獲取資料
            opening_cash = request.form.get('opening_cash', type=float)
            location_notes = request.form.get('location_notes')

            # 簡單的後端驗證
            if opening_cash is None or opening_cash < 0:
                flash('開店準備金格式不正確或小於 0，請重新輸入。', 'danger')
                return redirect(url_for('cashier.start_day', location=location))

            # 建立新的 BusinessDay 紀錄
            new_business_day = BusinessDay(
                date=today,
                location=location,
                location_notes=location_notes,
                status='OPEN', # 將狀態設定為「營業中」
                opening_cash=opening_cash,
                total_sales=0, # 初始銷售額為 0
                total_items=0, # 初始銷售件數為 0
                total_transactions=0 # 初始交易筆數為 0
            )

            # 將新紀錄加入資料庫並提交
            db.session.add(new_business_day)
            db.session.commit()

            flash(f'據點 "{location}" 開店成功！現在可以開始記錄交易。', 'success')
            # 成功後，導向該據點的 POS 系統頁面
            return redirect(url_for('cashier.pos', location=location))

        except Exception as e:
            db.session.rollback() # 如果發生錯誤，回滾資料庫操作
            flash(f'處理開店作業時發生錯誤：{e}', 'danger')
            return redirect(url_for('cashier.start_day', location=location))
    
    # 如果是 GET 請求，就顯示開店表單
    return render_template('cashier/start_day_form.html', 
                           location=location, 
                           today_date=today.strftime('%Y-%m-%d'))

@bp.route('/pos/<location>')
@login_required
def pos(location):
    """顯示 POS 系統主介面"""
    today = date.today()
    
    # 查詢今天此據點的營業日紀錄
    business_day = BusinessDay.query.filter_by(date=today, location=location, status='OPEN').first()

    # 如果找不到營業中紀錄 (例如使用者手動輸入網址)，則導回儀表板
    if not business_day:
        flash(f'據點 "{location}" 今日尚未開店營業。', 'warning')
        return redirect(url_for('cashier.dashboard'))

    # 將初始數據傳遞給範本
    return render_template('cashier/pos.html',
                           location=location,
                           today_date=today.strftime('%Y-%m-%d'),
                           initial_sales=business_day.total_sales,
                           initial_items=business_day.total_items,
                           initial_transactions=business_day.total_transactions)

@bp.route('/view_report/<location>')
@login_required
def view_report(location):
    return f"查看 {location} 的報表..."

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """處理登入邏輯"""
    if current_user.is_authenticated:
        return redirect(url_for('cashier.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # --- 修正點 ---
        # 我們將查詢結果統一儲存在名為 'user_from_db' 的變數中
        user_from_db = User.query.filter_by(username=username).first()

        # 檢查使用者是否存在，以及密碼是否正確
        if user_from_db is None or not user_from_db.check_password(password):
            flash('帳號或密碼錯誤，請重新輸入。', 'danger')
            return redirect(url_for('cashier.login'))
        
        # --- 修正點 ---
        # 將正確的變數 'user_from_db' 傳遞給 login_user 函式
        login_user(user_from_db)
        flash('登入成功！', 'success')

        next_page = request.args.get('next')
        return redirect(next_page or url_for('cashier.dashboard'))

    return render_template('cashier/login.html')

@bp.route('/logout')
@login_required
def logout():
    """處理登出邏輯"""
    logout_user()
    flash('您已成功登出。', 'info')
    return redirect(url_for('cashier.login'))