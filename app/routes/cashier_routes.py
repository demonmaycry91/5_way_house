import os
import json
from flask import (
    render_template,
    request,
    flash,
    redirect,
    url_for,
    Blueprint,
    jsonify,
    current_app,
)
from flask_login import login_user, logout_user, login_required, current_user
from ..models import User, BusinessDay, Transaction, Location
from .. import db, login_manager, csrf
from ..forms import LoginForm, StartDayForm, CloseDayForm, ConfirmReportForm
from datetime import date, datetime
from ..services import google_service
from sqlalchemy.orm import contains_eager
from sqlalchemy import and_
# --- 匯入我們建立的裝飾器 ---
from ..decorators import admin_required

# 建立名為 'cashier' 的藍圖
bp = Blueprint("cashier", __name__, url_prefix="/cashier")


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login 需要這個函式來根據 session 中的 user_id 重新載入使用者物件。"""
    return User.query.get(int(user_id))

# --- 統一入口 ---
@bp.route('/')
@login_required
def index():
    """Cashier 功能區的根目錄，自動重新導向到儀表板。"""
    return redirect(url_for('cashier.dashboard'))


# --- Dashboard ---
@bp.route("/dashboard")
@login_required
def dashboard():
    """每日營運儀表板。"""
    today = date.today()
    
    locations = (
        db.session.query(Location)
        .outerjoin(
            BusinessDay,
            and_(
                Location.id == BusinessDay.location_id,
                BusinessDay.date == today
            )
        )
        .options(contains_eager(Location.business_days))
        .order_by(Location.id)
        .all()
    )
    
    locations_status = {}
    
    for location in locations:
        business_day = next(iter(location.business_days), None)
        
        status_info = {}
        if business_day is None:
            status_info = {
                "status_text": "尚未開帳",
                "message": "點擊以開始本日營業作業。",
                "badge_class": "bg-secondary",
                "url": url_for("cashier.start_day", location_slug=location.slug),
            }
        elif business_day.status == "OPEN":
            status_info = {
                "status_text": "營業中",
                "message": f"本日銷售額: ${business_day.total_sales or 0:,.0f}",
                "badge_class": "bg-success",
                "url": url_for("cashier.pos", location_slug=location.slug),
            }
        elif business_day.status == "PENDING_REPORT":
            status_info = {
                "status_text": "待確認報表",
                "message": "點擊以檢視並確認本日報表。",
                "badge_class": "bg-warning text-dark",
                "url": url_for("cashier.daily_report", location_slug=location.slug),
            }
        elif business_day.status == "CLOSED":
            status_info = {
                "status_text": "已日結",
                "message": "本日帳務已結算，僅供查閱。",
                "badge_class": "bg-primary",
                "url": url_for("cashier.daily_report", location_slug=location.slug),
            }
        
        locations_status[location] = status_info
        
    return render_template(
        "cashier/dashboard.html",
        today_date=today.strftime("%Y-%m-%d"),
        locations_status=locations_status,
    )


# --- Login / Logout ---
@bp.route("/login", methods=["GET", "POST"])
def login():
    """處理使用者登入。"""
    if current_user.is_authenticated:
        return redirect(url_for("cashier.dashboard"))
    
    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash("帳號或密碼錯誤，請重新輸入。", "danger")
            return redirect(url_for("cashier.login"))
        login_user(user)
        flash("登入成功！", "success")
        next_page = request.args.get("next")
        return redirect(next_page or url_for("cashier.dashboard"))
    
    return render_template("cashier/login.html", form=form)

@bp.route("/logout")
@login_required
def logout():
    """處理使用者登出。"""
    logout_user()
    flash("您已成功登出。", "info")
    return redirect(url_for("cashier.login"))


# --- Settings ---
@bp.route("/settings")
@login_required
@admin_required  # --- 修正點：加入權限保護 ---
def settings():
    """系統設定頁面，主要用於管理 Google 帳號的連結狀態。"""
    token_path = os.path.join(current_app.instance_path, "token.json")
    is_connected = os.path.exists(token_path)
    return render_template("cashier/settings.html", is_connected=is_connected)


# --- Start Day ---
@bp.route("/start_day/<location_slug>", methods=["GET", "POST"])
@login_required
def start_day(location_slug):
    """開店作業頁面。"""
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    today = date.today()
    
    if BusinessDay.query.filter_by(date=today, location_id=location.id).first():
        flash(f'據點 "{location.name}" 今日已開帳或已日結，無法重複操作。', "warning")
        return redirect(url_for("cashier.dashboard"))

    form = StartDayForm()
    if form.validate_on_submit():
        new_business_day = BusinessDay(
            date=today,
            location=location,
            location_notes=form.location_notes.data,
            status="OPEN",
            opening_cash=form.opening_cash.data,
        )
        db.session.add(new_business_day)
        db.session.commit()
        flash(f'據點 "{location.name}" 開店成功！現在可以開始記錄交易。', "success")
        return redirect(url_for("cashier.pos", location_slug=location.slug))
            
    return render_template(
        "cashier/start_day_form.html",
        location=location,
        today_date=today.strftime("%Y-%m-%d"),
        form=form
    )


# --- POS ---
@bp.route("/pos/<location_slug>")
@login_required
def pos(location_slug):
    """銷售點終端 (POS) 頁面。"""
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    today = date.today()
    business_day = BusinessDay.query.filter_by(
        date=today, location_id=location.id, status="OPEN"
    ).first()
    if not business_day:
        flash(f'據點 "{location.name}" 今日尚未開店營業。', "warning")
        return redirect(url_for("cashier.dashboard"))
        
    return render_template(
        "cashier/pos.html",
        location=location,
        today_date=today.strftime("%Y-%m-%d"),
        initial_sales=business_day.total_sales or 0,
        initial_items=business_day.total_items or 0,
        initial_transactions=business_day.total_transactions or 0,
    )


# --- Record Transaction API ---
@bp.route("/record_transaction", methods=["POST"])
@csrf.exempt
@login_required
def record_transaction():
    """接收前端 AJAX 請求，記錄一筆新交易。"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "沒有收到資料"}), 400

    location_slug = data.get("location_slug")
    total = data.get("total")
    item_count = data.get("items")
    today = date.today()

    if not all([location_slug, isinstance(total, (int, float)), isinstance(item_count, int)]):
        return jsonify({"success": False, "error": "資料格式不正確"}), 400

    try:
        location = Location.query.filter_by(slug=location_slug).first()
        if not location:
            return jsonify({"success": False, "error": "無效的據點識別碼"}), 404

        business_day = BusinessDay.query.filter_by(
            date=today, location_id=location.id, status="OPEN"
        ).first()
        if not business_day:
            return jsonify({"success": False, "error": "找不到對應的營業中紀錄"}), 404

        new_transaction = Transaction(
            amount=total, item_count=item_count, business_day_id=business_day.id
        )
        db.session.add(new_transaction)
        
        business_day.total_sales = (business_day.total_sales or 0) + total
        business_day.total_items = (business_day.total_items or 0) + item_count
        business_day.total_transactions = (business_day.total_transactions or 0) + 1
        
        db.session.commit()

        header = ["時間戳", "金額", "品項數"]
        transaction_data = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total, item_count]
        current_app.task_queue.enqueue(
            'app.services.google_service.write_transaction_to_sheet_task',
            args=(location.name, transaction_data, header),
            job_timeout='10m'
        )

        return jsonify({
            "success": True,
            "message": "交易紀錄成功",
            "total_sales": business_day.total_sales,
            "total_items": business_day.total_items,
            "total_transactions": business_day.total_transactions,
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"記錄交易時發生錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500


# --- Close Day ---
@bp.route("/close_day/<location_slug>", methods=["GET", "POST"])
@login_required
def close_day(location_slug):
    """日結作業 - 現金盤點頁面。"""
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    today = date.today()
    business_day = BusinessDay.query.filter_by(
        date=today, location_id=location.id, status="OPEN"
    ).first()
    if not business_day:
        flash(f'據點 "{location.name}" 今日並非營業中狀態，無法進行日結。', "warning")
        return redirect(url_for("cashier.dashboard"))

    form = CloseDayForm()    
    denominations = [1000, 500, 200, 100, 50, 10, 5, 1]

    if form.validate_on_submit():
        try:
            total_cash_counted = 0
            cash_breakdown = {}
            for denom in denominations:
                count = request.form.get(f"count_{denom}", 0, type=int)
                total_cash_counted += count * denom
                cash_breakdown[denom] = count
            business_day.closing_cash = total_cash_counted
            business_day.cash_breakdown = json.dumps(cash_breakdown)
            business_day.status = "PENDING_REPORT"
            db.session.commit()
            flash("現金盤點完成！請核對最後的每日報表。", "success")
            return redirect(url_for("cashier.daily_report", location_slug=location.slug))
        except Exception as e:
            db.session.rollback()
            flash(f"處理日結時發生錯誤：{e}", "danger")
            return redirect(url_for("cashier.close_day", location_slug=location.slug))
            
    return render_template(
        "cashier/close_day_form.html",
        location=location,
        today_date=today.strftime("%Y-%m-%d"),
        denominations=denominations,
        form=form
    )


# --- Daily Report ---
@bp.route("/report/<location_slug>")
@login_required
def daily_report(location_slug):
    """每日報表檢視頁面。"""
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    today = date.today()
    business_day = BusinessDay.query.filter(
        BusinessDay.date == today,
        BusinessDay.location_id == location.id,
        BusinessDay.status.in_(["PENDING_REPORT", "CLOSED"]),
    ).first()

    if not business_day:
        flash(f'找不到據點 "{location.name}" 今日的日結報表資料。', "warning")
        return redirect(url_for("cashier.dashboard"))
        
    closing_cash = business_day.closing_cash or 0
    opening_cash = business_day.opening_cash or 0
    total_sales = business_day.total_sales or 0
    expected_total = opening_cash + total_sales
    difference = closing_cash - expected_total
    
    form = ConfirmReportForm()
    
    return render_template(
        "cashier/daily_report.html",
        day=business_day,
        帳面總額=expected_total,
        帳差=difference,
        form=form
    )


# --- Confirm Report ---
@bp.route("/confirm_report/<location_slug>", methods=["POST"])
@login_required
def confirm_report(location_slug):
    """最終確認報表，將本日營業正式歸檔。"""
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    today = date.today()
    business_day = BusinessDay.query.filter_by(
        date=today, location_id=location.id, status="PENDING_REPORT"
    ).first()

    if not business_day:
        flash("找不到待確認的報表，或該報表已被確認。", "warning")
        return redirect(url_for("cashier.dashboard"))

    form = ConfirmReportForm()
    if form.validate_on_submit():
        try:
            business_day.signature_operator = request.form.get('sig_operator')
            business_day.signature_reviewer = request.form.get('sig_reviewer')
            business_day.signature_cashier = request.form.get('sig_cashier')
            
            business_day.status = "CLOSED"
            business_day.expected_cash = (business_day.opening_cash or 0) + (business_day.total_sales or 0)
            business_day.cash_diff = (business_day.closing_cash or 0) - business_day.expected_cash
            db.session.commit()

            header = ["日期", "據點", "開店準備金", "本日銷售總額", "帳面總額", "盤點現金合計", "帳差", "交易筆數", "銷售件數"]
            report_data = [
                business_day.date.strftime("%Y-%m-%d"),
                business_day.location.name,
                business_day.opening_cash,
                business_day.total_sales,
                business_day.expected_cash,
                business_day.closing_cash,
                business_day.cash_diff,
                business_day.total_transactions,
                business_day.total_items,
            ]
            current_app.task_queue.enqueue(
                'app.services.google_service.write_report_to_sheet_task',
                args=(location.name, report_data, header),
                job_timeout='10m'
            )

            flash(f'據點 "{location.name}" 本日營業已成功歸檔！正在背景同步至雲端...', "success")
            return redirect(url_for("cashier.daily_report", location_slug=location.slug))
        except Exception as e:
            db.session.rollback()
            flash(f"歸檔時發生錯誤：{e}", "danger")
            return redirect(url_for("cashier.daily_report", location_slug=location.slug))
    
    flash('無效的操作請求，請重試。', 'danger')
    return redirect(url_for('cashier.daily_report', location_slug=location.slug))


# --- PDF Report Generation ---
@bp.route("/report/<location_slug>/print", methods=['POST'])
@login_required
def print_report(location_slug):
    """產生並回傳每日報表的 PDF 檔案。"""
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    today = date.today()
    business_day = BusinessDay.query.filter(
        BusinessDay.date == today,
        BusinessDay.location_id == location.id,
    ).first_or_404()

    closing_cash = business_day.closing_cash or 0
    opening_cash = business_day.opening_cash or 0
    total_sales = business_day.total_sales or 0
    expected_total = opening_cash + total_sales
    difference = closing_cash - expected_total

    signatures = {
        'operator': request.form.get('sig_operator'),
        'reviewer': request.form.get('sig_reviewer'),
        'cashier': request.form.get('sig_cashier'),
    }

    html_to_render = render_template(
        "cashier/report_print.html",
        day=business_day,
        帳面總額=expected_total,
        帳差=difference,
        signatures=signatures
    )

    pdf = HTML(string=html_to_render).write_pdf()

    return Response(
        pdf,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment;filename=daily_report_{location.slug}_{today.strftime('%Y%m%d')}.pdf"
        }
    )
