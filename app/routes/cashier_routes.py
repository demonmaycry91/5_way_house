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
    Response
)
from flask_login import login_user, logout_user, login_required, current_user
from ..models import User, BusinessDay, Transaction, Location, SystemSetting, Category, TransactionItem
from .. import db, login_manager, csrf
from ..forms import LoginForm, StartDayForm, CloseDayForm, ConfirmReportForm, GoogleSettingsForm
from datetime import date, datetime
from ..services import google_service
from sqlalchemy.orm import contains_eager
from sqlalchemy import and_
from ..decorators import admin_required
from weasyprint import HTML
from sqlalchemy.sql import func
from sqlalchemy import case

bp = Blueprint("cashier", __name__, url_prefix="/cashier")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@bp.route('/')
@login_required
def index():
    return redirect(url_for('cashier.dashboard'))


@bp.route("/dashboard")
@login_required
def dashboard():
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
        # 修正點：動態計算捐款與其他收入總額
        donation_total = 0
        other_total = 0
        total_sales_with_income = business_day.total_sales if business_day else 0
        if business_day:
            other_income_totals = db.session.query(
                Category.name,
                func.sum(TransactionItem.price)
            ).join(TransactionItem.transaction).join(Transaction.business_day).join(TransactionItem.category).filter(
                BusinessDay.id == business_day.id,
                Category.category_type == 'other_income'
            ).group_by(Category.name).all()
            for name, total in other_income_totals:
                total_sales_with_income += total
                if name == '捐款':
                    donation_total = total
                else:
                    other_total += total

        if business_day is None:
            status_info = {"business_day_id": None, "status_text": "尚未開帳", "message": "點擊以開始本日營業作業。",
                        "badge_class": "bg-secondary", "url": url_for("cashier.start_day", location_slug=location.slug)}
        elif business_day.status == "OPEN":
            status_info = {"business_day_id": business_day.id, "status_text": "營業中", "message": f"本日銷售額: ${total_sales_with_income:,.0f}",
                        "badge_class": "bg-success", "url": url_for("cashier.pos", location_slug=location.slug)}
        elif business_day.status == "PENDING_REPORT":
            status_info = {"business_day_id": business_day.id, "status_text": "待確認報表", "message": "點擊以檢視並確認本日報表。",
                        "badge_class": "bg-warning text-dark", "url": url_for("cashier.daily_report", location_slug=location.slug)}
        elif business_day.status == "CLOSED":
            status_info = {"business_day_id": business_day.id, "status_text": "已日結", "message": "本日帳務已結算，僅供查閱。",
                        "badge_class": "bg-primary", "url": url_for("cashier.daily_report", location_slug=location.slug)}
        locations_status[location] = status_info
    return render_template("cashier/dashboard.html", today_date=today.strftime("%Y-%m-%d"), locations_status=locations_status)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("cashier.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash("帳號或密碼錯誤，請重新輸入。", "danger")
            return redirect(url_for("cashier.login"))
        login_user(user)
        next_page = request.args.get("next")
        return redirect(next_page or url_for("cashier.dashboard"))
    return render_template("cashier/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("您已成功登出。", "info")
    return redirect(url_for("cashier.login"))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
@admin_required
def settings():
    form = GoogleSettingsForm()
    if form.validate_on_submit():
        SystemSetting.set('drive_folder_name', form.drive_folder_name.data)
        SystemSetting.set('sheets_filename_format',
                          form.sheets_filename_format.data)
        flash('雲端備份設定已成功儲存！', 'success')
        return redirect(url_for('cashier.settings'))

    form.drive_folder_name.data = SystemSetting.get(
        'drive_folder_name', 'Cashier_System_Reports')
    form.sheets_filename_format.data = SystemSetting.get(
        'sheets_filename_format', '{location_name}_{year}_業績')

    token_path = os.path.join(current_app.instance_path, "token.json")
    is_connected = os.path.exists(token_path)

    drive_account_email = None
    if is_connected:
        user_info = google_service.get_drive_user_info()
        if user_info and 'email' in user_info:
            drive_account_email = user_info['email']

    return render_template(
        "cashier/settings.html",
        is_connected=is_connected,
        form=form,
        drive_account_email=drive_account_email
    )


@bp.route('/rebuild_backup', methods=['POST'])
@login_required
@admin_required
def rebuild_backup():
    unclosed_locations = BusinessDay.query.filter(
        BusinessDay.status.in_(['OPEN', 'PENDING_REPORT'])).all()
    if unclosed_locations:
        reasons = [
            f"{loc.location.name} ({'正在營業中' if loc.status == 'OPEN' else '報表待確認'})" for loc in unclosed_locations]
        flash(f"備份失敗：因為以下據點尚未完成日結: {', '.join(reasons)}", "danger")
        return redirect(url_for('cashier.settings'))

    overwrite = request.form.get('overwrite') == 'on'

    current_app.task_queue.enqueue(
        'app.services.google_service.rebuild_backup_task',
        args=(overwrite,),
        job_timeout='30m'
    )

    flash('已成功提交完整備份請求！備份將在背景執行，請稍後至 Google Drive 查閱結果。', 'info')
    return redirect(url_for('cashier.settings'))


@bp.route("/start_day/<location_slug>", methods=["GET", "POST"])
@login_required
def start_day(location_slug):
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    today = date.today()
    if BusinessDay.query.filter_by(date=today, location_id=location.id).first():
        flash(f'據點 "{location.name}" 今日已開帳或已日結，無法重複操作。', "warning")
        return redirect(url_for("cashier.dashboard"))
    form = StartDayForm()
    if form.validate_on_submit():
        new_business_day = BusinessDay(
            date=today, location=location, location_notes=form.location_notes.data, status="OPEN", opening_cash=form.opening_cash.data)
        db.session.add(new_business_day)
        db.session.commit()
        flash(f'據點 "{location.name}" 開店成功！現在可以開始記錄交易。', "success")
        return redirect(url_for("cashier.pos", location_slug=location.slug))
    return render_template("cashier/start_day_form.html", location=location, today_date=today.strftime("%Y-%m-%d"), form=form)


@bp.route("/pos/<location_slug>")
@login_required
def pos(location_slug):
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    today = date.today()
    business_day = BusinessDay.query.filter_by(
        date=today, location_id=location.id, status="OPEN").first()
    if not business_day:
        flash(f'據點 "{location.name}" 今日尚未開店營業。', "warning")
        return redirect(url_for("cashier.dashboard"))

    categories = Category.query.filter_by(
        location_id=location.id).order_by(Category.id).all()

    # 修正點：從交易紀錄中動態計算其他收入總額
    from sqlalchemy.sql import func
    from sqlalchemy import case

    other_income_totals = db.session.query(
        Category.name,
        func.sum(TransactionItem.price)
    ).join(TransactionItem.transaction).join(Transaction.business_day).join(TransactionItem.category).filter(
        BusinessDay.id == business_day.id,
        Category.category_type == 'other_income'
    ).group_by(Category.name).all()

    donation_total = 0
    other_total = 0
    for name, total in other_income_totals:
        if name == '捐款':
            donation_total = total
        else:
            other_total += total

    return render_template("cashier/pos.html",
                           location=location,
                           today_date=today.strftime("%Y-%m-%d"),
                           business_day=business_day,
                           categories=categories,
                           donation_total=donation_total,
                           other_total=other_total)


@bp.route("/record_transaction", methods=["POST"])
@csrf.exempt
@login_required
def record_transaction():
    data = request.get_json()
    location_slug = data.get("location_slug")
    items = data.get("items", [])
    today = date.today()

    cash_received = data.get("cash_received")
    change_given = data.get("change_given")

    if not items:
        return jsonify({"success": False, "error": "交易內容不可為空"}), 400

    try:
        location = Location.query.filter_by(slug=location_slug).first()
        business_day = BusinessDay.query.filter_by(date=today, location_id=location.id, status="OPEN").first()
        if not business_day:
            return jsonify({"success": False, "error": "找不到對應的營業中紀錄"}), 404

        total_amount = sum(item['price'] for item in items)
        
        # 修正點：分開計算銷售額和項目總數。
        # total_sales 是指所有 product 的金額總和，discounts 是指所有 discount 的金額總和。
        # 應為 (總銷售額) = (所有商品金額) - (所有折扣金額)
        total_sales_amount = 0
        total_items_count = 0
        for item in items:
            category = Category.query.get(item['category_id'])
            if category and category.category_type in ['product', 'discount_fixed', 'discount_percent', 'buy_n_get_m', 'buy_x_get_x_minus_1', 'buy_odd_even']:
                total_sales_amount += item['price']
            if category and category.category_type == 'product':
                total_items_count += 1
        
        # 修正點：交易總額直接使用 total_amount，而不是重新計算
        new_transaction = Transaction(
            amount=total_amount, 
            item_count=len(items),
            business_day_id=business_day.id,
            cash_received=cash_received,
            change_given=change_given
        )
        db.session.add(new_transaction)
        
        for item in items:
            transaction_item = TransactionItem(
                price=item['price'],
                category_id=item['category_id'],
                transaction=new_transaction
            )
            db.session.add(transaction_item)

        # 修正點：使用新的 total_sales_amount 更新 business_day
        business_day.total_sales = (business_day.total_sales or 0) + total_sales_amount
        business_day.total_items = (business_day.total_items or 0) + total_items_count
        business_day.total_transactions = (business_day.total_transactions or 0) + 1
        
        db.session.commit()
        
        # 重新查詢當日其他收入總額，以傳回給前端
        from sqlalchemy.sql import func
        from sqlalchemy import case
        other_income_totals = db.session.query(
            Category.name,
            func.sum(TransactionItem.price)
        ).join(TransactionItem.transaction).join(Transaction.business_day).join(TransactionItem.category).filter(
            BusinessDay.id == business_day.id,
            Category.category_type == 'other_income'
        ).group_by(Category.name).all()
        
        donation_total = 0
        other_total = 0
        for name, total in other_income_totals:
            if name == '捐款':
                donation_total = total
            else:
                other_total += total

        return jsonify({
            "success": True,
            "total_sales": business_day.total_sales,
            "total_items": business_day.total_items,
            "total_transactions": business_day.total_transactions,
            "donation_total": donation_total,
            "other_total": other_total,
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"記錄交易時發生錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500


@bp.route("/close_day/<location_slug>", methods=["GET", "POST"])
@login_required
def close_day(location_slug):
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    today = date.today()
    business_day = BusinessDay.query.filter_by(
        date=today, location_id=location.id, status="OPEN").first()
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
    return render_template("cashier/close_day_form.html", location=location, today_date=today.strftime("%Y-%m-%d"), denominations=denominations, form=form)


@bp.route("/report/<location_slug>", methods=['GET'])
@login_required
def daily_report(location_slug):
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    date_str = request.args.get('date', date.today().isoformat())
    try:
        report_date = date.fromisoformat(date_str)
    except ValueError:
        flash("日期格式無效。", "danger")
        return redirect(url_for("cashier.dashboard"))

    business_day = BusinessDay.query.filter(BusinessDay.date == report_date, BusinessDay.location_id == location.id, BusinessDay.status.in_(["PENDING_REPORT", "CLOSED"])).first()
    if not business_day:
        flash(f'找不到據點 "{location.name}" {report_date.strftime("%Y-%m-%d")} 的日結報表資料。', "warning")
        return redirect(url_for("cashier.dashboard"))

    closing_cash = business_day.closing_cash or 0
    opening_cash = business_day.opening_cash or 0
    
    # 修正點：動態重新計算 total_sales，確保顯示正確的折扣後總額
    recalculated_total_sales = db.session.query(func.sum(Transaction.amount)).filter(Transaction.business_day_id == business_day.id).scalar() or 0
    
    other_income_total = db.session.query(
        func.sum(TransactionItem.price)
    ).join(TransactionItem.transaction).join(Transaction.business_day).join(TransactionItem.category).filter(
        BusinessDay.id == business_day.id,
        Category.category_type == 'other_income'
    ).scalar() or 0
    
    expected_total = opening_cash + recalculated_total_sales + other_income_total
    difference = closing_cash - expected_total
    form = ConfirmReportForm()
    
    # 修正點：將動態計算的 total_sales 傳給模板
    business_day.total_sales = recalculated_total_sales
    business_day.expected_cash = expected_total
    business_day.cash_diff = difference

    return render_template("cashier/daily_report.html", day=business_day, 帳面總額=expected_total, 帳差=difference, form=form, report_date=report_date)


@bp.route("/confirm_report/<location_slug>", methods=["POST"])
@login_required
def confirm_report(location_slug):
    report_date_str = request.form.get('report_date')
    if not report_date_str:
        flash("請求缺少日期參數。", "danger")
        return redirect(url_for("cashier.dashboard"))
        
    try:
        report_date = date.fromisoformat(report_date_str)
    except ValueError:
        flash("日期格式無效。", "danger")
        return redirect(url_for("cashier.dashboard"))
    
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    business_day = BusinessDay.query.filter_by(date=report_date, location_id=location.id, status="PENDING_REPORT").first()
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
            
            # 修正點：動態重新計算 total_sales 和 other_income_total，並存回資料庫
            recalculated_total_sales = db.session.query(func.sum(Transaction.amount)).filter(Transaction.business_day_id == business_day.id).scalar() or 0
            
            other_income_total = db.session.query(
                func.sum(TransactionItem.price)
            ).join(TransactionItem.transaction).join(Transaction.business_day).join(TransactionItem.category).filter(
                BusinessDay.id == business_day.id,
                Category.category_type == 'other_income'
            ).scalar() or 0
            
            business_day.total_sales = recalculated_total_sales
            business_day.expected_cash = (business_day.opening_cash or 0) + (business_day.total_sales or 0) + other_income_total
            business_day.cash_diff = (business_day.closing_cash or 0) - business_day.expected_cash
            
            db.session.commit()
            header = ["日期", "據點", "開店準備金", "本日銷售總額", "帳面總額", "盤點現金合計", "帳差", "交易筆數", "銷售件數"]
            report_data = [business_day.date.strftime("%Y-%m-%d"), business_day.location.name, business_day.opening_cash, business_day.total_sales, business_day.expected_cash, business_day.closing_cash, business_day.cash_diff, business_day.total_transactions, business_day.total_items]
            current_app.task_queue.enqueue('app.services.google_service.write_report_to_sheet_task', args=(location.id, report_data, header), job_timeout='10m')
            flash(f'據點 "{location.name}" 本日營業已成功歸檔！正在背景同步至雲端...', "success")
            return redirect(url_for("cashier.daily_report", location_slug=location.slug, date=report_date.isoformat()))
        except Exception as e:
            db.session.rollback()
            flash(f"歸檔時發生錯誤：{e}", "danger")
            return redirect(url_for('cashier.daily_report', location_slug=location.slug, date=report_date.isoformat()))
    flash('無效的操作請求，請重試。', 'danger')
    return redirect(url_for('cashier.daily_report', location_slug=location.slug, date=report_date.isoformat()))


@bp.route("/report/<location_slug>/print", methods=['POST'])
@login_required
def print_report(location_slug):
    location = Location.query.filter_by(slug=location_slug).first_or_404()
    today = date.today()
    business_day = BusinessDay.query.filter(
        BusinessDay.date == today, BusinessDay.location_id == location.id).first_or_404()
    closing_cash = business_day.closing_cash or 0
    opening_cash = business_day.opening_cash or 0
    total_sales = business_day.total_sales or 0

    # 修正點：從交易紀錄中計算其他收入並計入 expected_total
    from sqlalchemy.sql import func
    other_income_total = db.session.query(
        func.sum(TransactionItem.price)
    ).join(TransactionItem.transaction).join(Transaction.business_day).join(TransactionItem.category).filter(
        BusinessDay.id == business_day.id,
        Category.category_type == 'other_income'
    ).scalar() or 0

    expected_total = opening_cash + total_sales + other_income_total
    difference = closing_cash - expected_total
    signatures = {'operator': request.form.get('sig_operator'), 'reviewer': request.form.get(
        'sig_reviewer'), 'cashier': request.form.get('sig_cashier')}
    html_to_render = render_template(
        "cashier/report_print.html", day=business_day, 帳面總額=expected_total, 帳差=difference, signatures=signatures)
    pdf = HTML(string=html_to_render).write_pdf()
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f"attachment;filename=daily_report_{location.slug}_{today.strftime('%Y%m%d')}.pdf"})
