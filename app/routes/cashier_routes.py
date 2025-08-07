# my_app/routes/cashier_routes.py (最終完整版)

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
from ..models import User, BusinessDay, Transaction
from .. import db, login_manager
from datetime import date, datetime  # <--- [修正點] 已確保 datetime 被正確匯入
from ..services import google_service
import threading  # <--- [修正點] 已確保 threading 被正確匯入

bp = Blueprint("cashier", __name__, url_prefix="/cashier")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- Dashboard ---


@bp.route("/dashboard")
@login_required
def dashboard():
    today = date.today()
    LOCATIONS = ["本舖", "瘋衣舍", "特賣會1", "特賣會2", "其他"]
    locations_status = {}
    for location_name in LOCATIONS:
        business_day = BusinessDay.query.filter_by(
            date=today, location=location_name
        ).first()
        status_info = {}
        if business_day is None:
            status_info = {
                "status_text": "尚未開帳",
                "message": "點擊以開始本日營業作業。",
                "badge_class": "bg-secondary",
                "url": url_for("cashier.start_day", location=location_name),
            }
        elif business_day.status == "OPEN":
            status_info = {
                "status_text": "營業中",
                "message": f"本日銷售額: ${business_day.total_sales:,.0f}",
                "badge_class": "bg-success",
                "url": url_for("cashier.pos", location=location_name),
            }
        elif business_day.status == "PENDING_REPORT":
            status_info = {
                "status_text": "待確認報表",
                "message": "點擊以檢視並確認本日報表。",
                "badge_class": "bg-warning text-dark",
                "url": url_for("cashier.daily_report", location=location_name),
            }
        elif business_day.status == "CLOSED":
            status_info = {
                "status_text": "已日結",
                "message": "本日帳務已結算，僅供查閱。",
                "badge_class": "bg-primary",
                "url": url_for("cashier.daily_report", location=location_name),
            }
        locations_status[location_name] = status_info
    return render_template(
        "cashier/dashboard.html",
        today_date=today.strftime("%Y-%m-%d"),
        locations_status=locations_status,
    )


# --- Login / Logout ---


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("cashier.dashboard"))
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user_from_db = User.query.filter_by(username=username).first()
        if user_from_db is None or not user_from_db.check_password(password):
            flash("帳號或密碼錯誤，請重新輸入。", "danger")
            return redirect(url_for("cashier.login"))
        login_user(user_from_db)
        flash("登入成功！", "success")
        next_page = request.args.get("next")
        return redirect(next_page or url_for("cashier.dashboard"))
    return render_template("cashier/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("您已成功登出。", "info")
    return redirect(url_for("cashier.login"))


# --- Settings ---


@bp.route("/settings")
@login_required
def settings():
    token_path = os.path.join(current_app.instance_path, "token.json")
    is_connected = os.path.exists(token_path)
    return render_template("cashier/settings.html", is_connected=is_connected)


# --- Start Day ---


@bp.route("/start_day/<location>", methods=["GET", "POST"])
@login_required
def start_day(location):
    today = date.today()
    existing_day = BusinessDay.query.filter_by(
        date=today, location=location).first()
    if existing_day:
        flash(f'據點 "{location}" 今日已開帳或已日結，無法重複操作。', "warning")
        return redirect(url_for("cashier.dashboard"))
    if request.method == "POST":
        try:
            opening_cash = request.form.get("opening_cash", type=float)
            location_notes = request.form.get("location_notes")
            if opening_cash is None or opening_cash < 0:
                flash("開店準備金格式不正確或小於 0，請重新輸入。", "danger")
                return redirect(url_for("cashier.start_day", location=location))
            new_business_day = BusinessDay(
                date=today,
                location=location,
                location_notes=location_notes,
                status="OPEN",
                opening_cash=opening_cash,
            )
            db.session.add(new_business_day)
            db.session.commit()
            flash(f'據點 "{location}" 開店成功！現在可以開始記錄交易。', "success")
            return redirect(url_for("cashier.pos", location=location))
        except Exception as e:
            db.session.rollback()
            flash(f"處理開店作業時發生錯誤：{e}", "danger")
            return redirect(url_for("cashier.start_day", location=location))
    return render_template(
        "cashier/start_day_form.html",
        location=location,
        today_date=today.strftime("%Y-%m-%d"),
    )


# --- POS ---


@bp.route("/pos/<location>")
@login_required
def pos(location):
    today = date.today()
    business_day = BusinessDay.query.filter_by(
        date=today, location=location, status="OPEN"
    ).first()
    if not business_day:
        flash(f'據點 "{location}" 今日尚未開店營業。', "warning")
        return redirect(url_for("cashier.dashboard"))
    return render_template(
        "cashier/pos.html",
        location=location,
        today_date=today.strftime("%Y-%m-%d"),
        initial_sales=business_day.total_sales,
        initial_items=business_day.total_items,
        initial_transactions=business_day.total_transactions,
    )


# --- Record Transaction API ---


@bp.route("/record_transaction", methods=["POST"])
@login_required
def record_transaction():
    """接收前端 AJAX 請求，記錄一筆新交易，並在背景同步到 Google Sheets"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "沒有收到資料"}), 400

    location = data.get("location")
    total = data.get("total")
    item_count = data.get("items")
    today = date.today()

    if not all(
        [location, isinstance(total, (int, float)),
         isinstance(item_count, int)]
    ):
        return jsonify({"success": False, "error": "資料格式不正確"}), 400

    try:
        # 1. 更新本地資料庫 (這一步很快)
        business_day = BusinessDay.query.filter_by(
            date=today, location=location, status="OPEN"
        ).first()
        if not business_day:
            return jsonify({"success": False, "error": "找不到對應的營業中紀錄"}), 404

        new_transaction = Transaction(
            amount=total, item_count=item_count, business_day_id=business_day.id
        )
        db.session.add(new_transaction)
        business_day.total_sales += total
        business_day.total_items += item_count
        business_day.total_transactions += 1
        db.session.commit()

        # 2. 準備好要傳給背景任務的資料
        header = ["時間戳", "金額", "品項數"]
        transaction_data = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total,
            item_count,
        ]
        app_context = current_app.app_context()

        # 3. 建立並啟動背景執行緒去處理 Google Sheets 的慢速任務
        thread = threading.Thread(
            target=google_service.write_transaction_to_sheet,
            args=(app_context, location, transaction_data, header),
        )
        thread.start()

        # 4. 立刻回傳成功響應給前端，讓網頁立即更新！
        return jsonify(
            {
                "success": True,
                "message": "交易紀錄成功",
                "total_sales": business_day.total_sales,
                "total_items": business_day.total_items,
                "total_transactions": business_day.total_transactions,
            }
        )

    except Exception as e:
        db.session.rollback()
        print(f"記錄交易時發生錯誤: {e}")
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500


# --- Close Day ---


@bp.route("/close_day/<location>", methods=["GET", "POST"])
@login_required
def close_day(location):
    today = date.today()
    business_day = BusinessDay.query.filter_by(
        date=today, location=location, status="OPEN"
    ).first()
    if not business_day:
        flash(f'據點 "{location}" 今日並非營業中狀態，無法進行日結。', "warning")
        return redirect(url_for("cashier.dashboard"))
    denominations = [1000, 500, 200, 100, 50, 10, 5, 1]
    if request.method == "POST":
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
            return redirect(url_for("cashier.daily_report", location=location))
        except Exception as e:
            db.session.rollback()
            flash(f"處理日結時發生錯誤：{e}", "danger")
            return redirect(url_for("cashier.close_day", location=location))
    return render_template(
        "cashier/close_day_form.html",
        location=location,
        today_date=today.strftime("%Y-%m-%d"),
        denominations=denominations,
    )


# --- Daily Report ---


@bp.route("/report/<location>")
@login_required
def daily_report(location):
    today = date.today()
    business_day = BusinessDay.query.filter(
        BusinessDay.date == today,
        BusinessDay.location == location,
        BusinessDay.status.in_(["PENDING_REPORT", "CLOSED"]),
    ).first()
    if not business_day:
        flash(f'找不到據點 "{location}" 今日的日結報表資料。', "warning")
        return redirect(url_for("cashier.dashboard"))
    closing_cash = business_day.closing_cash or 0
    opening_cash = business_day.opening_cash or 0
    total_sales = business_day.total_sales or 0
    expected_total = opening_cash + total_sales
    difference = closing_cash - expected_total
    return render_template(
        "cashier/daily_report.html",
        day=business_day,
        帳面總額=expected_total,
        帳差=difference,
    )


# --- Confirm Report ---


@bp.route("/confirm_report/<location>", methods=["POST"])
@login_required
def confirm_report(location):
    """處理最終確認，將本日營業正式結束，並在背景將摘要同步到 Google Sheets"""
    today = date.today()
    business_day = BusinessDay.query.filter_by(
        date=today, location=location, status="PENDING_REPORT"
    ).first()

    if not business_day:
        flash("找不到待確認的報表，或該報表已被確認。", "warning")
        return redirect(url_for("cashier.dashboard"))

    try:
        # 1. 更新本地資料庫
        business_day.status = "CLOSED"
        business_day.expected_cash = (business_day.opening_cash or 0) + (
            business_day.total_sales or 0
        )
        business_day.cash_diff = (
            business_day.closing_cash or 0
        ) - business_day.expected_cash
        db.session.commit()

        # 2. 準備好要傳給背景任務的資料
        header = [
            "日期",
            "據點",
            "開店準備金",
            "本日銷售總額",
            "帳面總額",
            "盤點現金合計",
            "帳差",
            "交易筆數",
            "銷售件數",
        ]
        report_data = [
            business_day.date.strftime("%Y-%m-%d"),
            business_day.location,
            business_day.opening_cash,
            business_day.total_sales,
            business_day.expected_cash,
            business_day.closing_cash,
            business_day.cash_diff,
            business_day.total_transactions,
            business_day.total_items,
        ]
        app_context = current_app.app_context()

        # 3. 建立並啟動背景執行緒
        thread = threading.Thread(
            target=google_service.write_report_to_sheet,
            args=(app_context, location, report_data, header),
        )
        thread.start()

        # 4. 立刻回傳成功響應給前端
        flash(f'據點 "{location}" 本日營業已成功歸檔！正在背景同步至雲端...', "success")
        return redirect(url_for("cashier.dashboard"))

    except Exception as e:
        db.session.rollback()
        flash(f"歸檔時發生錯誤：{e}", "danger")
        return redirect(url_for("cashier.daily_report", location=location))
