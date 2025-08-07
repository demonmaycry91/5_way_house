from flask import render_template, request, flash, redirect, url_for, Blueprint
from flask_login import login_user, logout_user, login_required, current_user
from ..models import User, BusinessDay, Transaction # <-- 新增匯入 BusinessDay
from .. import db, login_manager
from datetime import date # <-- 新增匯入 date
from flask import jsonify # <-- 請確保檔案頂部有匯入 jsonify
import json # <-- 新增匯入 json

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
    LOCATIONS = ['本舖', '瘋衣舍', '特賣會 1', '特賣會 2', '其他']
    
    locations_status = {}

    for location_name in LOCATIONS:
        # 查詢今天、此據點的營業日紀錄
        business_day = BusinessDay.query.filter_by(date=today, location=location_name).first()
        
        status_info = {}
        if business_day is None:
            # 狀態一：尚未開帳
            status_info = {
                'status_text': '尚未開帳',
                'message': '點擊以開始本日營業作業。',
                'badge_class': 'bg-secondary',
                'url': url_for('cashier.start_day', location=location_name)
            }
        elif business_day.status == 'OPEN':
            # 狀態二：營業中
            status_info = {
                'status_text': '營業中',
                'message': f"本日銷售額: ${business_day.total_sales:,.0f}",
                'badge_class': 'bg-success',
                'url': url_for('cashier.pos', location=location_name)
            }
        # --- ↓↓↓ 這就是我們新增的邏輯 ↓↓↓ ---
        elif business_day.status == 'PENDING_REPORT':
            # 狀態三：等待報表確認
            status_info = {
                'status_text': '待確認報表',
                'message': '點擊以檢視並確認本日報表。',
                'badge_class': 'bg-warning text-dark', # 使用黃色背景
                'url': url_for('cashier.daily_report', location=location_name)
            }
        # --- ↑↑↑ 新增結束 ↑↑↑ ---
        elif business_day.status == 'CLOSED':
            # 狀態四：已日結
            status_info = {
                'status_text': '已日結',
                'message': '本日帳務已結算，僅供查閱。',
                'badge_class': 'bg-primary',
                'url': url_for('cashier.daily_report', location=location_name) # 已日結也應該能查看報表
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

@bp.route('/record_transaction', methods=['POST'])
@login_required
def record_transaction():
    """接收前端 AJAX 請求，記錄一筆新交易"""
    # 獲取從前端傳來的 JSON 資料
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '沒有收到資料'}), 400

    location = data.get('location')
    total = data.get('total')
    item_count = data.get('items')
    today = date.today()

    # 簡單的後端驗證
    if not all([location, isinstance(total, (int, float)), isinstance(item_count, int)]):
        return jsonify({'success': False, 'error': '資料格式不正確'}), 400
        
    try:
        # 找到今天此據點的營業日紀錄
        business_day = BusinessDay.query.filter_by(date=today, location=location, status='OPEN').first()

        if not business_day:
            return jsonify({'success': False, 'error': '找不到對應的營業中紀錄'}), 404

        # --- 核心邏輯：更新資料庫 ---
        # 1. 建立新的交易流水紀錄
        new_transaction = Transaction(
            amount=total,
            item_count=item_count,
            business_day_id=business_day.id
        )
        db.session.add(new_transaction)

        # 2. 更新當日的總計數據
        business_day.total_sales += total
        business_day.total_items += item_count
        business_day.total_transactions += 1

        # 一次性提交所有變更
        db.session.commit()

        # 回傳成功的 JSON 響應，並附上最新的總計數據
        return jsonify({
            'success': True,
            'message': '交易紀錄成功',
            'total_sales': business_day.total_sales,
            'total_items': business_day.total_items,
            'total_transactions': business_day.total_transactions
        })

    except Exception as e:
        db.session.rollback() # 如果發生任何錯誤，回滾資料庫操作
        # 在伺服器後台印出詳細錯誤，方便除錯
        print(f"記錄交易時發生錯誤: {e}") 
        return jsonify({'success': False, 'error': '伺服器內部錯誤'}), 500

@bp.route('/close_day/<location>', methods=['GET', 'POST'])
@login_required
def close_day(location):
    """處理日結作業的現金盤點"""
    today = date.today()
    
    # 找到今天此據點的營業日紀錄
    business_day = BusinessDay.query.filter_by(date=today, location=location, status='OPEN').first()

    if not business_day:
        flash(f'據點 "{location}" 今日並非營業中狀態，無法進行日結。', 'warning')
        return redirect(url_for('cashier.dashboard'))

    # 定義台幣面額
    denominations = [1000, 500, 200, 100, 50, 10, 5, 1]

    if request.method == 'POST':
        try:
            total_cash_counted = 0
            cash_breakdown = {} # 用來儲存每種面額的數量
            
            for denom in denominations:
                count = request.form.get(f'count_{denom}', 0, type=int)
                total_cash_counted += count * denom
                cash_breakdown[denom] = count

            # --- 更新資料庫 ---
            business_day.closing_cash = total_cash_counted
            # 將各面額數量的字典轉換為 JSON 字串儲存
            business_day.cash_breakdown = json.dumps(cash_breakdown)
            
            # 將狀態從 OPEN 改為 PENDING_REPORT (等待報表確認)
            # 這樣可以防止使用者再回到 POS 頁面新增交易
            business_day.status = 'PENDING_REPORT'
            
            db.session.commit()

            flash('現金盤點完成！請核對最後的每日報表。', 'success')
            # 成功後，導向最終的報表頁面
            return redirect(url_for('cashier.daily_report', location=location))

        except Exception as e:
            db.session.rollback()
            flash(f'處理日結時發生錯誤：{e}', 'danger')
            return redirect(url_for('cashier.close_day', location=location))

    # 如果是 GET 請求，顯示盤點表單
    return render_template('cashier/close_day_form.html',
                           location=location,
                           today_date=today.strftime('%Y-%m-%d'),
                           denominations=denominations)

@bp.route('/report/<location>')
@login_required
def daily_report(location):
    """顯示最終的每日報表"""
    today = date.today()
    
    business_day = BusinessDay.query.filter(
        BusinessDay.date == today,
        BusinessDay.location == location,
        BusinessDay.status.in_(['PENDING_REPORT', 'CLOSED'])
    ).first()

    if not business_day:
        flash(f'找不到據點 "{location}" 今日的日結報表資料。', 'warning')
        return redirect(url_for('cashier.dashboard'))

    closing_cash = business_day.closing_cash or 0
    opening_cash = business_day.opening_cash or 0
    total_sales = business_day.total_sales or 0
    
    expected_total = opening_cash + total_sales
    difference = closing_cash - expected_total

    # --- ↓↓↓ THE FIX IS ON THIS LINE ↓↓↓ ---
    return render_template('cashier/daily_report.html',
                           day=business_day,
                           帳面總額=expected_total,
                           帳差=difference)

@bp.route('/confirm_report/<location>', methods=['POST'])
@login_required
def confirm_report(location):
    """處理最終確認，將本日營業正式結束"""
    today = date.today()
    
    business_day = BusinessDay.query.filter_by(
        date=today, 
        location=location, 
        status='PENDING_REPORT'
    ).first()

    if not business_day:
        flash('找不到待確認的報表，或該報表已被確認。', 'warning')
        return redirect(url_for('cashier.dashboard'))
        
    try:
        # --- 更新資料庫，正式封存 ---
        business_day.status = 'CLOSED'
        # 同時將計算出的帳面總額與帳差存入資料庫
        business_day.expected_cash = (business_day.opening_cash or 0) + (business_day.total_sales or 0)
        business_day.cash_diff = (business_day.closing_cash or 0) - business_day.expected_cash
        
        db.session.commit()
        
        flash(f'據點 "{location}" 本日營業已成功歸檔！', 'success')
        return redirect(url_for('cashier.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'歸檔時發生錯誤：{e}', 'danger')
        return redirect(url_for('cashier.daily_report', location=location))

    
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