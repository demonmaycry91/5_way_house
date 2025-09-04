from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, Response
from flask_login import login_required, current_user
from ..models import BusinessDay, Transaction, TransactionItem, Location, DailySettlement
from ..forms import ReportQueryForm, SettlementForm
from .. import db
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from datetime import date, timedelta, datetime
import json
from ..decorators import admin_required
from weasyprint import HTML

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

        query_base = db.session.query(BusinessDay).options(
            db.joinedload(BusinessDay.location)
        ).filter(
            BusinessDay.date.between(start_date, end_date)
        )

        if location_id != 'all':
            query_base = query_base.filter(BusinessDay.location_id == location_id)

        if report_type == 'daily_summary':
            results = query_base.order_by(BusinessDay.date.desc(), BusinessDay.location_id).all()

        elif report_type == 'transaction_log':
            business_day_ids = [b.id for b in query_base.all()]
            results = db.session.query(Transaction).join(BusinessDay).options(
                selectinload(Transaction.items).selectinload(TransactionItem.category),
                db.joinedload(Transaction.business_day).joinedload(BusinessDay.location)
            ).filter(
                Transaction.business_day_id.in_(business_day_ids)
            ).order_by(Transaction.timestamp).all()

        elif report_type == 'daily_cash_summary':
            results = query_base.order_by(BusinessDay.date, BusinessDay.location_id).all()

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
        
        # --- ↓↓↓ 在這裡修改合併報表總結的邏輯 ↓↓↓ ---
        elif report_type == 'combined_summary_final':
            
            check_results = []
            
            # 取得範圍內的所有結算與營業日資料
            all_settlements = DailySettlement.query.filter(
                DailySettlement.date.between(start_date - timedelta(days=1), end_date)
            ).all()
            all_business_days = BusinessDay.query.filter(
                BusinessDay.date.between(start_date, end_date)
            ).all()
            
            # 將資料轉換為字典以便快速查找
            settlements_by_date = {s.date: s for s in all_settlements}
            business_days_by_date = {}
            for bd in all_business_days:
                if bd.date not in business_days_by_date:
                    business_days_by_date[bd.date] = []
                business_days_by_date[bd.date].append(bd)

            # 遍歷日期範圍
            current_date = start_date
            while current_date <= end_date:
                previous_date = current_date - timedelta(days=1)
                
                yesterday_settlement = settlements_by_date.get(previous_date)
                today_reports = business_days_by_date.get(current_date, [])
                
                total_next_day_cash_from_yesterday = yesterday_settlement.total_next_day_opening_cash if yesterday_settlement else 0
                total_opening_cash_today = sum(r.opening_cash or 0 for r in today_reports)
                
                cash_check_diff = total_opening_cash_today - total_next_day_cash_from_yesterday

                # 只有當天或前一天有資料時，才加入結果列表
                if today_reports or yesterday_settlement:
                    check_results.append({
                        'date': current_date,
                        'cash_check_diff': cash_check_diff,
                        'yesterday_total': total_next_day_cash_from_yesterday,
                        'today_total': total_opening_cash_today
                    })
                
                current_date += timedelta(days=1)
            
            results = check_results
        # --- ↑↑↑ 修改結束 ↑↑↑ ---

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
    
    opened_locations = db.session.query(Location.name).join(BusinessDay).filter(BusinessDay.date == report_date).all()
    opened_location_names = {name for name, in opened_locations}

    closed_reports = db.session.query(BusinessDay).options(db.joinedload(BusinessDay.location)).filter(
        BusinessDay.date == report_date,
        BusinessDay.status == 'CLOSED'
    ).all()
    
    daily_settlement = DailySettlement.query.filter_by(date=report_date).first()
    is_settled = daily_settlement is not None

    unclosed_locations = opened_location_names - {r.location.name for r in closed_reports}
    all_closed = not unclosed_locations
    
    reports = {r.location.name: r for r in closed_reports}

    active_locations_ordered = [name for name in LOCATION_ORDER if name in reports]
    
    grand_total_dict = {
        'A': sum(r.expected_cash or 0 for r in closed_reports),
        'B': sum(r.total_sales or 0 for r in closed_reports),
        'C': sum(r.opening_cash or 0 for r in closed_reports),
        'D': sum(r.closing_cash or 0 for r in closed_reports),
        'J': sum(r.total_transactions or 0 for r in closed_reports),
        'K': sum(r.total_items or 0 for r in closed_reports),
    }
    grand_total_dict['E'] = grand_total_dict['D'] - grand_total_dict['A']
    grand_total_dict['F'] = sum((r.donation_total or 0) + (r.other_total or 0) for r in closed_reports)
    grand_total_dict['G'] = grand_total_dict['D'] + grand_total_dict['F']
    
    if is_settled:
        grand_total_dict['H'] = daily_settlement.total_deposit
        grand_total_dict['I'] = daily_settlement.total_next_day_opening_cash
    else:
        grand_total_dict['I'] = 0 
        grand_total_dict['H'] = grand_total_dict['G'] - grand_total_dict['I']

    class GrandTotal:
        def __init__(self, **entries):
            self.__dict__.update(entries)
    
    grand_total = GrandTotal(**grand_total_dict)
    
    form.date.data = report_date.isoformat()
    
    if is_settled:
        form.total_deposit.data = grand_total.H
        form.total_next_day_opening_cash.data = grand_total.I
        if daily_settlement.remarks:
            remarks_data = json.loads(daily_settlement.remarks)
            for remark_form in form.remarks:
                key = remark_form.key.data
                if key in remarks_data:
                    remark_form.value.data = remarks_data[key]
    else:
        form.total_next_day_opening_cash.data = grand_total.I
        form.total_deposit.data = grand_total.H

    finance_items = [
        ('A', '應有現金', 'A', 'expected_cash'),
        ('B', '手帳營收', 'B', 'total_sales'),
        ('C', '開店現金', 'C', 'opening_cash'),
        ('D', '實有現金', 'D', 'closing_cash'),
        ('E', '溢短收', 'E', 'cash_diff'),
        ('F', '其他現金', 'F', 'other_cash'),
        ('G', '當日總現金', 'G', 'total_cash'),
        ('H', '存款', 'H', 'deposit'),
        ('I', '明日開店現金', 'I', 'next_day_cash')
    ]
    sales_items = [
        ('J', '結單數', 'J', 'total_transactions'),
        ('K', '品項數', 'K', 'total_items')
    ]

    return render_template(
        'report/settlement.html',
        form=form,
        report_date=report_date,
        reports=reports,
        active_locations_ordered=active_locations_ordered,
        grand_total=grand_total,
        all_closed=all_closed,
        unclosed_locations=sorted(list(unclosed_locations)),
        is_settled=is_settled,
        finance_items=finance_items,
        sales_items=sales_items
    )

@bp.route('/save_settlement', methods=['POST'])
@login_required
@admin_required
def save_settlement():
    form = SettlementForm()
    if form.validate_on_submit():
        report_date = date.fromisoformat(form.date.data)
        
        existing_settlement = DailySettlement.query.filter_by(date=report_date).first()
        if existing_settlement:
            flash(f"{report_date.strftime('%Y-%m-%d')} 的總結算已歸檔，無法重複儲存。", "warning")
            return redirect(url_for('report.settlement', date=report_date.isoformat()))

        try:
            remarks_dict = {item.key.data: item.value.data for item in form.remarks if item.value.data}
            
            new_settlement = DailySettlement(
                date=report_date,
                total_deposit=form.total_deposit.data,
                total_next_day_opening_cash=form.total_next_day_opening_cash.data,
                remarks=json.dumps(remarks_dict)
            )
            db.session.add(new_settlement)
            db.session.commit()
            flash(f"已成功儲存 {report_date.strftime('%Y-%m-%d')} 的總結算資料。", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"儲存時發生錯誤：{e}", "danger")
    else:
        error_messages = []
        for field, errors in form.errors.items():
            for error in errors:
                error_messages.append(f"欄位 '{getattr(form, field).label.text}' 發生錯誤: {error}")
        flash("提交的資料有誤，請重試。 " + " ".join(error_messages), "warning")
        
        report_date_str = form.date.data or date.today().isoformat()
        return redirect(url_for('report.settlement', date=report_date_str))
        
    return redirect(url_for('report.settlement', date=form.date.data))

@bp.route('/settlement/print/<date_str>')
@login_required
@admin_required
def print_settlement(date_str):
    try:
        report_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        flash("無效的日期格式。", "danger")
        return redirect(url_for('report.settlement'))

    closed_reports = db.session.query(BusinessDay).options(db.joinedload(BusinessDay.location)).filter(
        BusinessDay.date == report_date,
        BusinessDay.status == 'CLOSED'
    ).all()
    daily_settlement = DailySettlement.query.filter_by(date=report_date).first()

    if not daily_settlement:
        flash("該日期的合併報表尚未結算，無法列印。", "warning")
        return redirect(url_for('report.settlement', date=report_date.isoformat()))

    reports = {r.location.name: r for r in closed_reports}
    active_locations_ordered = [name for name in LOCATION_ORDER if name in reports]
    
    grand_total_dict = {
        'A': sum(r.expected_cash or 0 for r in closed_reports),
        'B': sum(r.total_sales or 0 for r in closed_reports),
        'C': sum(r.opening_cash or 0 for r in closed_reports),
        'D': sum(r.closing_cash or 0 for r in closed_reports),
        'J': sum(r.total_transactions or 0 for r in closed_reports),
        'K': sum(r.total_items or 0 for r in closed_reports),
    }
    grand_total_dict['E'] = grand_total_dict['D'] - grand_total_dict['A']
    grand_total_dict['F'] = sum((r.donation_total or 0) + (r.other_total or 0) for r in closed_reports)
    grand_total_dict['G'] = grand_total_dict['D'] + grand_total_dict['F']
    grand_total_dict['H'] = daily_settlement.total_deposit
    grand_total_dict['I'] = daily_settlement.total_next_day_opening_cash

    class GrandTotal:
        def __init__(self, **entries):
            self.__dict__.update(entries)
    
    grand_total = GrandTotal(**grand_total_dict)
    
    remarks_data = json.loads(daily_settlement.remarks) if daily_settlement and daily_settlement.remarks else {}

    finance_items = [
        ('A', '應有現金', 'A', 'expected_cash'),
        ('B', '手帳營收', 'B', 'total_sales'),
        ('C', '開店現金', 'C', 'opening_cash'),
        ('D', '實有現金', 'D', 'closing_cash'),
        ('E', '溢短收', 'E', 'cash_diff'),
        ('F', '其他現金', 'F', 'other_cash'),
        ('G', '當日總現金', 'G', 'total_cash'),
        ('H', '存款', 'H', 'deposit'),
        ('I', '明日開店現金', 'I', 'next_day_cash')
    ]
    sales_items = [
        ('J', '結單數', 'J', 'total_transactions'),
        ('K', '品項數', 'K', 'total_items')
    ]

    html_to_render = render_template(
        'report/settlement_print.html',
        report_date=report_date,
        reports=reports,
        active_locations_ordered=active_locations_ordered,
        grand_total=grand_total,
        remarks_data=remarks_data,
        finance_items=finance_items,
        sales_items=sales_items
    )
    
    pdf = HTML(string=html_to_render).write_pdf()
    
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment;filename=settlement_report_{report_date.isoformat()}.pdf"}
    )

@bp.route('/api/settlement_status')
@login_required
@admin_required
def settlement_status_api():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    
    if not year or not month:
        return jsonify({"error": "Year and month are required"}), 400

    start_date = date(year, month, 1)
    end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    business_days = db.session.query(BusinessDay.date, BusinessDay.status, Location.name).join(Location).filter(BusinessDay.date.between(start_date, end_date)).all()
    settlements = db.session.query(DailySettlement.date).filter(DailySettlement.date.between(start_date, end_date)).all()
    
    settled_dates = {s.date for s in settlements}
    
    day_statuses = {}
    for d, status, loc_name in business_days:
        if d not in day_statuses:
            day_statuses[d] = {'opened': set(), 'closed': set()}
        day_statuses[d]['opened'].add(loc_name)
        if status == 'CLOSED':
            day_statuses[d]['closed'].add(loc_name)
            
    response_data = {}
    current_date = start_date
    while current_date <= end_date:
        iso_date = current_date.isoformat()
        if current_date in settled_dates:
            response_data[iso_date] = 'settled'
        elif current_date in day_statuses:
            stats = day_statuses[current_date]
            if len(stats['opened']) > 0 and stats['opened'] == stats['closed']:
                response_data[iso_date] = 'pending'
            else:
                response_data[iso_date] = 'in_progress'
        else:
            response_data[iso_date] = 'no_data'
        
        current_date += timedelta(days=1)
        
    return jsonify(response_data)

@bp.route('/api/query_status')
@login_required
def query_status_api():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    
    if not year or not month:
        return jsonify({"error": "Year and month are required"}), 400

    start_date = date(year, month, 1)
    end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    business_days = db.session.query(BusinessDay.date, BusinessDay.status).filter(
        BusinessDay.date.between(start_date, end_date)
    ).all()
    
    day_statuses = {}
    for d, status in business_days:
        if d not in day_statuses:
            day_statuses[d] = []
        day_statuses[d].append(status)
            
    response_data = {}
    current_date = start_date
    while current_date <= end_date:
        iso_date = current_date.isoformat()
        if current_date in day_statuses:
            statuses = set(day_statuses[current_date])
            if 'OPEN' in statuses or 'PENDING_REPORT' in statuses:
                response_data[iso_date] = 'in_progress'
            else:
                response_data[iso_date] = 'ready'
        else:
            response_data[iso_date] = 'no_data'
        
        current_date += timedelta(days=1)
        
    return jsonify(response_data)

