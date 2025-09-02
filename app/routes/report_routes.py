from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from ..models import BusinessDay, Transaction, TransactionItem, Location, DailySettlement
from ..forms import ReportQueryForm, SettlementForm
from .. import db
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from datetime import date, timedelta, datetime
from ..decorators import admin_required
import json

bp = Blueprint('report', __name__, url_prefix='/report')

LOCATION_ORDER = ["本舖", "瘋衣舍", "特賣會 1", "特賣會 2", "其他"]

@bp.route('/query', methods=['GET', 'POST'])
@login_required
def query():
    form = ReportQueryForm()
    report_type = None
    results = None
    grand_total = None
    
    if form.validate_on_submit():
        report_type = form.report_type.data
        start_date = form.start_date.data
        end_date = form.end_date.data if form.end_date.data else start_date
        location_id = form.location_id.data

        if report_type == 'daily_summary':
            query = db.session.query(BusinessDay).options(
                db.joinedload(BusinessDay.location)
            ).filter(
                BusinessDay.date.between(start_date, end_date),
                BusinessDay.status == 'CLOSED'
            )
            if location_id != 'all':
                query = query.filter(BusinessDay.location_id == location_id)
            results = query.order_by(BusinessDay.date.desc(), BusinessDay.location_id).all()

        elif report_type == 'transaction_log':
            query = db.session.query(Transaction).join(BusinessDay).options(
                selectinload(Transaction.items).selectinload(TransactionItem.category),
                db.joinedload(Transaction.business_day).joinedload(BusinessDay.location)
            ).filter(
                BusinessDay.date == start_date
            )
            if location_id != 'all':
                query = query.filter(BusinessDay.location_id == location_id)
            results = query.order_by(Transaction.timestamp).all()

        elif report_type == 'daily_cash_summary':
            query = db.session.query(BusinessDay).options(
                db.joinedload(BusinessDay.location)
            ).filter(
                BusinessDay.date == start_date
            )
            if location_id != 'all':
                query = query.filter(BusinessDay.location_id == location_id)
            results = query.order_by(BusinessDay.location_id).all()

            if results:
                grand_total_dict = {
                    'opening_cash': sum(r.opening_cash or 0 for r in results),
                    'total_sales': sum(r.total_sales or 0 for r in results),
                    'expected_cash': sum(r.expected_cash or 0 for r in results),
                    'closing_cash': sum(r.closing_cash or 0 for r in results),
                    'cash_diff': sum(r.cash_diff or 0 for r in results),
                    'donation_total': sum(r.donation_total or 0 for r in results),
                    'other_total': sum(r.other_total or 0 for r in results),
                }
                grand_total_dict['other_cash'] = grand_total_dict['donation_total'] + grand_total_dict['other_total']
                
                class GrandTotal:
                    def __init__(self, **entries):
                        self.__dict__.update(entries)
                grand_total = GrandTotal(**grand_total_dict)
        
        elif report_type == 'combined_summary_final':
            previous_date = start_date - timedelta(days=1)
            
            yesterday_settlement = DailySettlement.query.filter_by(date=previous_date).first()
            today_opening_cash_total = db.session.query(func.sum(BusinessDay.opening_cash)).filter(
                BusinessDay.date == start_date
            ).scalar() or 0

            cash_check_diff = today_opening_cash_total - (yesterday_settlement.total_next_day_opening_cash if yesterday_settlement else 0)
            
            results = {
                'cash_check_diff': cash_check_diff,
                'yesterday_total': yesterday_settlement.total_next_day_opening_cash if yesterday_settlement else 0,
                'today_total': today_opening_cash_total,
                'date': start_date
            }


    return render_template('report/query.html', 
                           form=form, 
                           results=results, 
                           report_type=report_type,
                           grand_total=grand_total)

@bp.route('/settlement', methods=['GET'])
@login_required
@admin_required
def settlement():
    date_str = request.args.get('date', date.today().isoformat())
    try:
        report_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        report_date = date.today()

    form = SettlementForm()
    
    # 檢查是否所有據點都已結帳
    all_locations = Location.query.all()
    
    business_days_today = BusinessDay.query.filter_by(date=report_date).all()
    opened_locations_today = {b.location_id for b in business_days_today}
    
    unclosed_locations = [b.location.name for b in business_days_today if b.status == 'OPEN']
    all_closed = not unclosed_locations if opened_locations_today else True

    reports_today_list = [b for b in business_days_today if b.status == 'CLOSED']
    reports = {r.location.name: r for r in reports_today_list}
    
    # 按照固定順序準備資料
    active_locations_ordered = [name for name in LOCATION_ORDER if name in reports]
    
    grand_total = {
        'A': sum(r.expected_cash or 0 for r in reports.values()),
        'B': sum(r.total_sales or 0 for r in reports.values()),
        'C': sum(r.opening_cash or 0 for r in reports.values()),
        'D': sum(r.closing_cash or 0 for r in reports.values()),
        'E': sum(r.cash_diff or 0 for r in reports.values()),
    }
    grand_total['F'] = sum((r.donation_total or 0) + (r.other_total or 0) for r in reports.values())
    grand_total['G'] = grand_total['D'] + grand_total['F']

    # 讀取已儲存的結算資料
    daily_settlement = DailySettlement.query.filter_by(date=report_date).first()
    is_settled = daily_settlement is not None

    if is_settled:
        form.total_deposit.data = daily_settlement.total_deposit
        form.total_next_day_opening_cash.data = daily_settlement.total_next_day_opening_cash
        try:
            remarks_data = json.loads(daily_settlement.remarks or '{}')
        except json.JSONDecodeError:
            remarks_data = {}
        
        for i, item_key in enumerate(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']):
            form.remarks[i].value.data = remarks_data.get(item_key, '')
            form.remarks[i].key.data = item_key
    else:
        form.total_next_day_opening_cash.data = 0
        for i, item_key in enumerate(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']):
            form.remarks[i].key.data = item_key

    grand_total['H'] = form.total_deposit.data if is_settled else (grand_total['G'] - (form.total_next_day_opening_cash.data or 0))
    grand_total['I'] = form.total_next_day_opening_cash.data

    class GrandTotal:
        def __init__(self, **entries):
            self.__dict__.update(entries)
    grand_total_obj = GrandTotal(**grand_total)

    return render_template(
        'report/settlement.html',
        form=form,
        report_date=report_date,
        reports=reports,
        grand_total=grand_total_obj,
        all_closed=all_closed,
        unclosed_locations=unclosed_locations,
        active_locations_ordered=active_locations_ordered,
        is_settled=is_settled
    )

@bp.route('/save_settlement', methods=['POST'])
@login_required
@admin_required
def save_settlement():
    form = SettlementForm()
    report_date = date.fromisoformat(form.report_date.data)

    if form.validate_on_submit():
        daily_settlement = DailySettlement.query.filter_by(date=report_date).first()
        if not daily_settlement:
            daily_settlement = DailySettlement(date=report_date)
            db.session.add(daily_settlement)
        
        daily_settlement.total_deposit = form.total_deposit.data
        daily_settlement.total_next_day_opening_cash = form.total_next_day_opening_cash.data
        
        remarks_data = {item.key.data: item.value.data for item in form.remarks}
        daily_settlement.remarks = json.dumps(remarks_data)

        try:
            db.session.commit()
            flash(f"已成功儲存 {report_date.strftime('%Y-%m-%d')} 的總結算資料。", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"儲存時發生錯誤: {e}", "danger")

        return redirect(url_for('report.settlement', date=report_date.isoformat()))
    else:
        flash("提交的資料有誤，請修正後再試一次。", "danger")
        all_locations = Location.query.all()
        closed_locations_today = {b.location_id for b in BusinessDay.query.filter_by(date=report_date, status='CLOSED')}
        opened_locations_today = {b.location_id for b in BusinessDay.query.filter_by(date=report_date)}
        unclosed_locations = [loc.name for loc in all_locations if loc.id in opened_locations_today and loc.id not in closed_locations_today]
        all_closed = not unclosed_locations
        reports_today_list = BusinessDay.query.filter(BusinessDay.date == report_date, BusinessDay.status == 'CLOSED').all()
        reports = {r.location.name: r for r in reports_today_list}
        active_locations_ordered = [name for name in LOCATION_ORDER if name in reports]
        grand_total = {
            'A': sum(r.expected_cash or 0 for r in reports.values()),
            'B': sum(r.total_sales or 0 for r in reports.values()),
            'C': sum(r.opening_cash or 0 for r in reports.values()),
            'D': sum(r.closing_cash or 0 for r in reports.values()),
            'E': sum(r.cash_diff or 0 for r in reports.values()),
        }
        grand_total['F'] = sum((r.donation_total or 0) + (r.other_total or 0) for r in reports.values())
        grand_total['G'] = grand_total['D'] + grand_total['F']
        grand_total['H'] = form.total_deposit.data
        grand_total['I'] = form.total_next_day_opening_cash.data
        class GrandTotal:
            def __init__(self, **entries):
                self.__dict__.update(entries)
        grand_total_obj = GrandTotal(**grand_total)

        return render_template(
            'report/settlement.html',
            form=form,
            report_date=report_date,
            reports=reports,
            grand_total=grand_total_obj,
            all_closed=all_closed,
            unclosed_locations=unclosed_locations,
            active_locations_ordered=active_locations_ordered,
            is_settled=False
        )

# --- ↓↓↓ 在這裡更新 API 邏輯 ↓↓↓ ---
@bp.route('/api/settlement_status')
@login_required
@admin_required
def settlement_status_api():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if not year or not month:
        today = date.today()
        year, month = today.year, today.month

    start_date = date(year, month, 1)
    end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    # 一次性查詢所需的所有資料
    settled_dates = {s.date for s in DailySettlement.query.filter(DailySettlement.date.between(start_date, end_date))}
    business_days = BusinessDay.query.filter(BusinessDay.date.between(start_date, end_date)).all()
    
    # 將營業日資料按日期分組
    days_data = {}
    for bd in business_days:
        if bd.date not in days_data:
            days_data[bd.date] = []
        days_data[bd.date].append(bd.status)

    status_map = {}
    current_day = start_date
    while current_day <= end_date:
        iso_date = current_day.isoformat()
        
        if current_day in settled_dates:
            status_map[iso_date] = 'settled'  # 紅色：已結算
        elif current_day in days_data:
            statuses = days_data[current_day]
            if 'OPEN' in statuses:
                status_map[iso_date] = 'in_progress' # 黃色：營業中
            else: # 如果沒有 OPEN，代表所有都是 CLOSED
                status_map[iso_date] = 'pending' # 綠色：待結算
        else:
            status_map[iso_date] = 'no_data' # 灰色：無資料

        current_day += timedelta(days=1)
            
    return jsonify(status_map)
# --- ↑↑↑ 修改結束 ↑↑↑ ---

