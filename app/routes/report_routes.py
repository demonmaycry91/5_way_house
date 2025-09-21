# app/routes/report_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, Response
from flask_login import login_required
from ..models import BusinessDay, Transaction, TransactionItem, Location, DailySettlement, Category
from ..forms import ReportQueryForm, SettlementForm
from .. import db, csrf
from sqlalchemy.orm import selectinload
from sqlalchemy import func, case, extract
from datetime import date, timedelta
import json
from ..decorators import admin_required
from weasyprint import HTML
import csv
from io import StringIO
from calendar import monthrange
from collections import defaultdict

bp = Blueprint('report', __name__, url_prefix='/report')

LOCATION_ORDER = ["本舖", "瘋衣舍", "特賣會 1", "特賣會 2", "其他"]
DENOMINATIONS = [1000, 500, 200, 100, 50, 10, 5, 1]

@bp.before_request
@login_required
@admin_required
def before_request():
    pass

def get_date_range_from_period(time_unit, year=None, month=None, quarter=None, period_str=None):
    """根據時間單位和參數，計算開始與結束日期"""
    try:
        if time_unit == 'month':
            year, month = map(int, period_str.split('-'))
            start_date = date(year, month, 1)
            end_date = date(year, month, monthrange(year, month)[1])
        elif time_unit == 'quarter':
            year, quarter = int(year), int(quarter)
            start_month = (quarter - 1) * 3 + 1
            end_month = start_month + 2
            start_date = date(year, start_month, 1)
            end_date = date(year, end_month, monthrange(year, end_month)[1])
        elif time_unit == 'year':
            year = int(year)
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
        return start_date, end_date
    except (ValueError, TypeError):
        return None, None

@bp.route('/query', methods=['GET'])
def query():
    form = ReportQueryForm()
    
    all_categories = Category.query.all()
    form.location_id.choices = [('all', '所有據點')] + [(str(l.id), l.name) for l in Location.query.order_by(Location.id).all()]

    results = None
    grand_total = None
    chart_data = None
    total_revenue = 0
    report_type = request.args.get('report_type', 'daily_summary')
    form.report_type.data = report_type

    if report_type:
        form.process(request.args)
        location_id = request.args.get('location_id', 'all')

        if report_type != 'periodic_performance':
            start_date_str = request.args.get('start_date')
            end_date_str = request.args.get('end_date')
            if not start_date_str:
                start_date = date.today()
                end_date = date.today()
                flash('查詢日期為必填欄位，已自動選取今日。', 'info')
                form.start_date.data = start_date
                form.end_date.data = end_date
            else:
                try:
                    start_date = date.fromisoformat(start_date_str)
                    end_date = date.fromisoformat(end_date_str) if end_date_str else start_date
                except ValueError:
                    start_date = date.today()
                    end_date = date.today()
                    flash('無效的日期格式，已自動選取今日。', 'warning')
                    form.start_date.data = start_date
                    form.end_date.data = end_date
        else:
            time_unit = request.args.get('time_unit')
            start_date_a, end_date_a = get_date_range_from_period(time_unit, year=request.args.get('year_a'), quarter=request.args.get('quarter_a'), period_str=request.args.get('period_a'))
            start_date_b, end_date_b = get_date_range_from_period(time_unit, year=request.args.get('year_b'), quarter=request.args.get('quarter_b'), period_str=request.args.get('period_b'))
            if not all([start_date_a, end_date_a, start_date_b, end_date_b]):
                 flash('週期性報表的時間參數不完整或格式錯誤，請重新選擇。', 'warning')
                 return render_template('report/query.html', form=form, all_categories=all_categories)

        if report_type != 'periodic_performance':
            query_base = db.session.query(BusinessDay).options(db.joinedload(BusinessDay.location)).filter(BusinessDay.date.between(start_date, end_date))
            if location_id != 'all':
                query_base = query_base.filter(BusinessDay.location_id == location_id)

        if report_type == 'daily_summary':
            results = query_base.order_by(BusinessDay.date.desc(), BusinessDay.location_id).all()
            if results:
                chart_labels = sorted(list(set(r.date.strftime('%Y-%m-%d') for r in results)))
                locations = sorted(list(set(r.location.name for r in results)))
                datasets = []
                for loc_name in locations:
                    data = [sum(r.total_sales or 0 for r in results if r.date.strftime('%Y-%m-%d') == label_date and r.location.name == loc_name) for label_date in chart_labels]
                    datasets.append({'label': loc_name, 'data': data})
                chart_data = {'labels': chart_labels, 'datasets': datasets}

        elif report_type == 'transaction_log':
            business_day_ids = [b.id for b in query_base.all()]
            results = db.session.query(Transaction).join(BusinessDay).options(
                selectinload(Transaction.items).selectinload(TransactionItem.category),
                db.joinedload(Transaction.business_day).joinedload(BusinessDay.location)
            ).filter(Transaction.business_day_id.in_(business_day_ids)).order_by(Transaction.timestamp).all()

        elif report_type in ['daily_cash_summary', 'daily_cash_check']:
            results = query_base.order_by(BusinessDay.date.desc(), BusinessDay.location_id).all()
            if results:
                # 重新動態計算 donation_total 和 other_total，以避免 AttributeError
                for r in results:
                    other_income_totals = db.session.query(
                        Category.name,
                        func.sum(TransactionItem.price)
                    ).join(TransactionItem.transaction).join(Transaction.business_day).join(TransactionItem.category).filter(
                        BusinessDay.id == r.id,
                        Category.category_type == 'other_income'
                    ).group_by(Category.name).all()
                    
                    r.donation_total = 0
                    r.other_total = 0
                    for name, total in other_income_totals:
                        if name == '捐款':
                            r.donation_total = total
                        else:
                            r.other_total += total
                
                grand_total_dict = {
                    'opening_cash': sum(r.opening_cash or 0 for r in results),
                    'total_sales': sum(r.total_sales or 0 for r in results),
                    'expected_cash': sum(r.expected_cash or 0 for r in results),
                    'closing_cash': sum(r.closing_cash or 0 for r in results),
                    'cash_diff': sum(r.cash_diff or 0 for r in results),
                    'donation_total': sum(r.donation_total or 0 for r in results),
                    'other_total': sum(r.other_total or 0 for r in results),
                    'location_notes': ""
                }
                grand_total_dict['other_cash'] = grand_total_dict['donation_total'] + grand_total_dict['other_total']
                class GrandTotal:
                    def __init__(self, **entries): self.__dict__.update(entries)
                grand_total = GrandTotal(**grand_total_dict)
                sales_by_location = defaultdict(float)
                for r in results:
                    sales_by_location[r.location.name] += r.total_sales or 0
                chart_data = {
                    'labels': list(sales_by_location.keys()),
                    'datasets': [{'label': '手帳營收', 'data': list(sales_by_location.values())}]
                }
        
        elif report_type == 'combined_summary_final':
            check_results = []
            all_settlements = DailySettlement.query.filter(DailySettlement.date.between(start_date - timedelta(days=1), end_date)).all()
            all_business_days = BusinessDay.query.filter(BusinessDay.date.between(start_date, end_date)).all()
            settlements_by_date = {s.date: s for s in all_settlements}
            business_days_by_date = defaultdict(list)
            for bd in all_business_days: business_days_by_date[bd.date].append(bd)
            current_date = start_date
            while current_date <= end_date:
                previous_date = current_date - timedelta(days=1)
                yesterday_settlement = settlements_by_date.get(previous_date)
                today_reports = business_days_by_date.get(current_date, [])
                total_next_day_cash_from_yesterday = yesterday_settlement.total_next_day_opening_cash if yesterday_settlement else 0
                total_opening_cash_today = sum(r.opening_cash or 0 for r in today_reports)
                cash_check_diff = total_opening_cash_today - total_next_day_cash_from_yesterday
                if today_reports or yesterday_settlement:
                    check_results.append({
                        'date': current_date, 'cash_check_diff': cash_check_diff,
                        'yesterday_total': total_next_day_cash_from_yesterday, 'today_total': total_opening_cash_today
                    })
                current_date += timedelta(days=1)
            results = check_results

        elif report_type == 'product_mix':
            query = db.session.query(
                Category.name.label('category_name'),
                func.sum(case((TransactionItem.price > 0, TransactionItem.price), else_=0)).label('total_sales'),
                func.count(case((TransactionItem.price > 0, TransactionItem.id), else_=None)).label('items_sold')
            ).join(TransactionItem.transaction).join(Transaction.business_day).join(TransactionItem.category).filter(
                BusinessDay.date.between(start_date, end_date), Category.category_type == 'product'
            )
            if location_id != 'all': query = query.filter(BusinessDay.location_id == location_id)
            results = query.group_by(Category.name).order_by(func.sum(TransactionItem.price).desc()).all()
            total_revenue = sum(r.total_sales for r in results) if results else 0
            chart_data = {
                'labels': [r.category_name for r in results],
                'datasets': [{'label': '銷售總額', 'data': [r.total_sales for r in results]}]
            }

        elif report_type == 'sales_trend':
            query = db.session.query(BusinessDay.date, func.sum(BusinessDay.total_sales).label('total_sales'), func.sum(BusinessDay.total_transactions).label('total_transactions')).filter(BusinessDay.date.between(start_date, end_date))
            if location_id != 'all': query = query.filter(BusinessDay.location_id == location_id)
            results = query.group_by(BusinessDay.date).order_by(BusinessDay.date).all()
            chart_data = {
                'labels': [r.date.strftime('%Y-%m-%d') for r in results],
                'datasets': [{'label': '總銷售額', 'data': [r.total_sales for r in results], 'borderColor': 'rgb(75, 192, 192)', 'tension': 0.1, 'yAxisID': 'y'}, {'label': '總交易筆數', 'data': [r.total_transactions for r in results], 'borderColor': 'rgb(255, 99, 132)', 'tension': 0.1, 'yAxisID': 'y1'}]
            }

        elif report_type == 'peak_hours':
            query = db.session.query(
                func.strftime('%H', Transaction.timestamp).label('hour'),
                func.count(Transaction.id).label('transactions'),
                func.sum(Transaction.amount).label('total_sales')
            ).join(BusinessDay).filter(BusinessDay.date.between(start_date, end_date))
            if location_id != 'all': query = query.filter(BusinessDay.location_id == location_id)
            results = query.group_by('hour').order_by('hour').all()
            chart_data = {
                'labels': [f"{r.hour}:00 - {int(r.hour)+1}:00" for r in results],
                'datasets': [{'label': '交易筆數', 'data': [r.transactions for r in results]}, {'label': '銷售總額', 'data': [r.total_sales for r in results]}]
            }

        elif report_type == 'periodic_performance':
            def get_period_data(start, end, unit):
                time_unit_expressions = {
                    'year': [extract('year', BusinessDay.date)], 'quarter': [extract('year', BusinessDay.date), case((extract('month', BusinessDay.date) <= 3, 1), (extract('month', BusinessDay.date) <= 6, 2), (extract('month', BusinessDay.date) <= 9, 3), else_=4)], 'month': [extract('year', BusinessDay.date), extract('month', BusinessDay.date)]
                }
                query = db.session.query(*time_unit_expressions[unit], func.sum(BusinessDay.total_sales).label('total_sales'), func.sum(BusinessDay.total_transactions).label('total_transactions')).filter(BusinessDay.date.between(start, end))
                if location_id != 'all': query = query.filter(BusinessDay.location_id == location_id)
                return query.group_by(*time_unit_expressions[unit]).order_by(*time_unit_expressions[unit]).all()

            data_a = get_period_data(start_date_a, end_date_a, time_unit)
            data_b = get_period_data(start_date_b, end_date_b, time_unit)
            dict_a = {tuple(row[:-2]): row[-2:] for row in data_a}
            dict_b = {tuple(row[:-2]): row[-2:] for row in data_b}
            all_keys = sorted(list(set(dict_a.keys()) | set(dict_b.keys())))
            results = []
            for key in all_keys:
                sales_a, trans_a = dict_a.get(key, (0, 0))
                sales_b, trans_b = dict_b.get(key, (0, 0))
                sales_diff = (sales_b or 0) - (sales_a or 0)
                sales_perc = (sales_diff / sales_a * 100) if sales_a else float('inf')
                label = ""
                if time_unit == 'year': label = str(key[0])
                elif time_unit == 'quarter': label = f"{key[0]}-Q{key[1]}"
                elif time_unit == 'month': label = f"{key[0]}-{key[1]:02d}"
                results.append({
                    'label': label, 'sales_a': sales_a or 0, 'trans_a': trans_a or 0, 'sales_b': sales_b or 0, 'trans_b': trans_b or 0, 'sales_diff': sales_diff, 'sales_perc': sales_perc
                })
            chart_data = {
                'labels': [r['label'] for r in results],
                'datasets': [{'label': f'期間 A', 'data': [r['sales_a'] for r in results]}, {'label': f'期間 B', 'data': [r['sales_b'] for r in results]}]
            }
            
    return render_template('report/query.html', 
                           form=form, 
                           results=results, 
                           report_type=report_type,
                           grand_total=grand_total,
                           chart_data=json.dumps(chart_data) if chart_data else None,
                           total_revenue=total_revenue,
                           denominations=DENOMINATIONS,
                           all_categories=[{'id': c.id, 'name': c.name, 'category_type': c.category_type} for c in all_categories])


@bp.route('/save_daily_summary_data', methods=['POST'])
@csrf.exempt
def save_daily_summary_data():
    try:
        data = request.get_json()
        for row_data in data:
            business_day = BusinessDay.query.get(row_data.get('id'))
            if not business_day:
                continue
            business_day.opening_cash = float(row_data.get('opening_cash', business_day.opening_cash))
            business_day.expected_cash = (business_day.opening_cash or 0) + (business_day.total_sales or 0)
            business_day.cash_diff = (business_day.closing_cash or 0) - (business_day.expected_cash or 0)
        db.session.commit()
        return jsonify({'success': True, 'message': '每日摘要數據已成功更新。'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/save_cash_check_data', methods=['POST'])
@csrf.exempt
def save_cash_check_data():
    try:
        data = request.get_json()
        
        for row_data in data:
            business_day_id = row_data.get('id')
            business_day = BusinessDay.query.get(business_day_id)
            if not business_day:
                continue
            cash_breakdown_raw = row_data.get('cash_breakdown')
            if isinstance(cash_breakdown_raw, dict):
                cash_breakdown_dict = {key: int(value) for key, value in cash_breakdown_raw.items()}
                business_day.cash_breakdown = json.dumps(cash_breakdown_dict)
                closing_cash = sum(int(denom) * count for denom, count in cash_breakdown_dict.items())
                business_day.closing_cash = float(closing_cash)
            business_day.expected_cash = (business_day.opening_cash or 0) + (business_day.total_sales or 0)
            business_day.cash_diff = (business_day.closing_cash or 0) - (business_day.expected_cash or 0)
        db.session.commit()
        return jsonify({'success': True, 'message': '報表數據已成功儲存！'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失敗: {str(e)}'}), 500

@bp.route('/save_transaction_log_data', methods=['POST'])
@csrf.exempt
def save_transaction_log_data():
    try:
        data = request.get_json()
        for transaction_data in data:
            transaction = Transaction.query.get(transaction_data.get('id'))
            if not transaction:
                continue
            transaction.cash_received = float(transaction_data.get('cash_received', transaction.cash_received))
            for item_data in transaction_data.get('items', []):
                item = TransactionItem.query.get(item_data.get('id'))
                if item:
                    item.price = float(item_data.get('price', item.price))
                    item.category_id = item_data.get('category_id', item.category_id)
            new_transaction_amount = sum(item.price for item in transaction.items)
            transaction.amount = new_transaction_amount
            transaction.change_given = (transaction.cash_received or 0) - (transaction.amount or 0)
            business_day = transaction.business_day
            if business_day:
                all_transactions_for_day = BusinessDay.query.get(business_day.id).transactions
                business_day.total_sales = sum(t.amount or 0 for t in all_transactions_for_day)
                business_day.expected_cash = (business_day.opening_cash or 0) + (business_day.total_sales or 0)
                business_day.cash_diff = (business_day.closing_cash or 0) - (business_day.expected_cash or 0)
        db.session.commit()
        return jsonify({'success': True, 'message': '交易細節數據已成功更新。'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/save_daily_cash_summary_data', methods=['POST'])
@csrf.exempt
def save_daily_cash_summary_data():
    flash('錯誤：捐款與其他收入為累計欄位，無法手動修改。', 'danger')
    return jsonify({'success': False, 'message': '捐款與其他收入為累計欄位，無法手動修改。'}), 400

@bp.route('/export_csv')
def export_csv():
    report_type = request.args.get('report_type')
    location_id = request.args.get('location_id')
    
    si = StringIO()
    cw = csv.writer(si)
    header = []
    results_to_write = []

    if report_type != 'periodic_performance':
        start_date = date.fromisoformat(request.args.get('start_date'))
        end_date = date.fromisoformat(request.args.get('end_date')) if request.args.get('end_date') else start_date
    else:
        time_unit = request.args.get('time_unit')
        start_date_a, end_date_a = get_date_range_from_period(time_unit, year=request.args.get('year_a'), quarter=request.args.get('quarter_a'), period_str=request.args.get('period_a'))
        start_date_b, end_date_b = get_date_range_from_period(time_unit, year=request.args.get('year_b'), quarter=request.args.get('quarter_b'), period_str=request.args.get('period_b'))
        if not all([start_date_a, end_date_a, start_date_b, end_date_b]):
            flash('無法匯出：週期性報表的時間參數不完整。', 'warning')
            return redirect(url_for('report.query'))

    if report_type == 'daily_summary':
        header = ['日期', '據點', '開店金', '銷售總額', '帳面總額', '盤點現金', '帳差', '交易筆數', '銷售件數']
        query = db.session.query(BusinessDay).filter(BusinessDay.date.between(start_date, end_date))
        if location_id != 'all': query = query.filter(BusinessDay.location_id == location_id)
        results = query.order_by(BusinessDay.date.desc(), BusinessDay.location_id).all()
        for day in results:
            results_to_write.append([day.date.strftime('%Y-%m-%d'), day.location.name, day.opening_cash, day.total_sales, day.expected_cash, day.closing_cash, day.cash_diff, day.total_transactions, day.total_items])
    
    elif report_type in ['daily_cash_summary', 'daily_cash_check']:
        header = ['日期', '據點', '開店現金', '手帳營收', '應有現金', '實有現金', '溢短收', '捐款', '其他收入', '其他現金(總)', '備註']
        query = db.session.query(BusinessDay).filter(BusinessDay.date.between(start_date, end_date))
        if location_id != 'all': query = query.filter(BusinessDay.location_id == location_id)
        results = query.order_by(BusinessDay.date, BusinessDay.location_id).all()
        for day in results:
            results_to_write.append([
                day.date.strftime('%Y-%m-%d'), day.location.name, day.opening_cash, day.total_sales, day.expected_cash,
                day.closing_cash, day.cash_diff, day.donation_total, day.other_total, (day.donation_total or 0) + (day.other_total or 0), day.location_notes
            ])

    elif report_type == 'transaction_log':
        header = ['時間', '據點', '項目/折扣', '類型', '單價/折扣額', '收到現金', '交易總額', '找零']
        query_base = db.session.query(BusinessDay).filter(BusinessDay.date.between(start_date, end_date))
        if location_id != 'all': query_base = query_base.filter(BusinessDay.location_id == location_id)
        business_day_ids = [b.id for b in query_base.all()]
        results = db.session.query(Transaction).filter(Transaction.business_day_id.in_(business_day_ids)).order_by(Transaction.timestamp).all()
        for trans in results:
            for item in trans.items:
                results_to_write.append([
                    trans.timestamp.strftime('%Y-%m-%d %H:%M:%S'), trans.business_day.location.name,
                    item.category.name if item.category else '手動輸入', '商品' if item.price > 0 else '折扣',
                    item.price, trans.cash_received, trans.amount, trans.change_given
                ])

    elif report_type == 'product_mix':
        header = ['類別名稱', '銷售數量', '銷售總額']
        query = db.session.query(Category.name, func.count(case((TransactionItem.price > 0, TransactionItem.id), else_=None)), func.sum(case((TransactionItem.price > 0, TransactionItem.price), else_=0))).join(TransactionItem.transaction).join(Transaction.business_day).join(TransactionItem.category).filter(BusinessDay.date.between(start_date, end_date), Category.category_type == 'product')
        if location_id != 'all': query = query.filter(BusinessDay.location_id == location_id)
        results = query.group_by(Category.name).order_by(func.sum(TransactionItem.price).desc()).all()
        total_revenue = sum(r.total_sales for r in results) if results else 0
        chart_data = {
            'labels': [r.category_name for r in results],
            'datasets': [{'label': '銷售總額', 'data': [r.total_sales for r in results]}]
        }

    elif report_type == 'sales_trend':
        header = ['日期', '總銷售額', '總交易筆數']
        query = db.session.query(BusinessDay.date, func.sum(BusinessDay.total_sales).label('total_sales'), func.sum(BusinessDay.total_transactions).label('total_transactions')).filter(BusinessDay.date.between(start_date, end_date))
        if location_id != 'all': query = query.filter(BusinessDay.location_id == location_id)
        results = query.group_by(BusinessDay.date).order_by(BusinessDay.date).all()
        results_to_write = [[r.date.strftime('%Y-%m-%d'), r.total_sales, r.total_transactions] for r in results]

    elif report_type == 'peak_hours':
        header = ['時段', '交易筆數', '銷售總額']
        query = db.session.query(func.strftime('%H', Transaction.timestamp), func.count(Transaction.id), func.sum(Transaction.amount)).join(BusinessDay).filter(BusinessDay.date.between(start_date, end_date))
        if location_id != 'all': query = query.filter(BusinessDay.location_id == location_id)
        query_results = query.group_by(func.strftime('%H', Transaction.timestamp)).order_by(func.strftime('%H', Transaction.timestamp)).all()
        results_to_write = [(f"{r[0]}:00 - {int(r[0])+1}:00", r[1], r[2]) for r in query_results]

    elif report_type == 'periodic_performance':
        header = ['時間單位', '期間 A 銷售額', '期間 A 交易數', '期間 B 銷售額', '期間 B 交易數', '銷售額差異', '增長率']
        def get_period_data_csv(start, end, unit):
            time_unit_expressions = {'year': [extract('year', BusinessDay.date)], 'quarter': [extract('year', BusinessDay.date), case((extract('month', BusinessDay.date) <= 3, 1), (extract('month', BusinessDay.date) <= 6, 2), (extract('month', BusinessDay.date) <= 9, 3), else_=4)], 'month': [extract('year', BusinessDay.date), extract('month', BusinessDay.date)]}
            query = db.session.query(*time_unit_expressions[unit], func.sum(BusinessDay.total_sales).label('total_sales'), func.sum(BusinessDay.total_transactions).label('total_transactions')).filter(BusinessDay.date.between(start, end))
            if location_id != 'all': query = query.filter(BusinessDay.location_id == location_id)
            return query.group_by(*time_unit_expressions[unit]).order_by(*time_unit_expressions[unit]).all()
        data_a = get_period_data_csv(start_date_a, end_date_a, time_unit)
        data_b = get_period_data_csv(start_date_b, end_date_b, time_unit)
        dict_a = {tuple(row[:-2]): row[-2:] for row in data_a}
        dict_b = {tuple(row[:-2]): row[-2:] for row in data_b}
        all_keys = sorted(list(set(dict_a.keys()) | set(dict_b.keys())))
        for key in all_keys:
            sales_a, trans_a = dict_a.get(key, (0, 0))
            sales_b, trans_b = dict_b.get(key, (0, 0))
            sales_diff = (sales_b or 0) - (sales_a or 0)
            sales_perc = (sales_diff / sales_a * 100) if sales_a else float('inf')
            label = ""
            if time_unit == 'year': label = str(key[0])
            elif time_unit == 'quarter': label = f"{key[0]}-Q{key[1]}"
            elif time_unit == 'month': label = f"{key[0]}-{key[1]:02d}"
            results_to_write.append((label, sales_a or 0, trans_a or 0, sales_b or 0, trans_b or 0, sales_diff, f"{sales_perc:.2f}%" if sales_a else "N/A"))
            
    else:
        flash('此報表類型不支援匯出功能。', 'warning')
        return redirect(url_for('report.query'))

    cw.writerow(header)
    cw.writerows(results_to_write)
    output = si.getvalue().encode('utf-8-sig')
    
    filename = f"{report_type}_{date.today().strftime('%Y%m%d')}.csv"
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )
    
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
    
    # --- 修正點：動態計算 donation_total 和 other_total ---
    for r in closed_reports:
        r.donation_total = 0
        r.other_total = 0
        other_income_totals = db.session.query(
            Category.name,
            func.sum(TransactionItem.price)
        ).join(TransactionItem.transaction).join(Transaction.business_day).join(TransactionItem.category).filter(
            BusinessDay.id == r.id,
            Category.category_type == 'other_income'
        ).group_by(Category.name).all()
        for name, total in other_income_totals:
            if name == '捐款':
                r.donation_total = total
            else:
                r.other_total += total
    
    grand_total_dict = {
        'A': sum(r.expected_cash or 0 for r in closed_reports), 'B': sum(r.total_sales or 0 for r in closed_reports), 'C': sum(r.opening_cash or 0 for r in closed_reports),
        'D': sum(r.closing_cash or 0 for r in closed_reports), 'J': sum(r.total_transactions or 0 for r in closed_reports), 'K': sum(r.total_items or 0 for r in closed_reports),
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
        def __init__(self, **entries): self.__dict__.update(entries)
    grand_total = GrandTotal(**grand_total_dict)
    
    form.date.data = report_date.isoformat()
    
    if is_settled:
        form.total_deposit.data = grand_total.H
        form.total_next_day_opening_cash.data = grand_total.I
        if daily_settlement.remarks:
            remarks_data = json.loads(daily_settlement.remarks)
            for remark_form in form.remarks:
                if remark_form.key.data in remarks_data:
                    remark_form.value.data = remarks_data[remark_form.key.data]
    else:
        form.total_next_day_opening_cash.data = grand_total.I
        form.total_deposit.data = grand_total.H

    finance_items = [
        ('A', '應有現金', 'A', 'expected_cash'), ('B', '手帳營收', 'B', 'total_sales'), ('C', '開店現金', 'C', 'opening_cash'),
        ('D', '實有現金', 'D', 'closing_cash'), ('E', '溢短收', 'E', 'cash_diff'), ('F', '其他現金', 'F', 'other_cash'),
        ('G', '當日總現金', 'G', 'total_cash'), ('H', '存款', 'H', 'deposit'), ('I', '明日開店現金', 'I', 'next_day_cash')
    ]
    sales_items = [('J', '結單數', 'J', 'total_transactions'), ('K', '品項數', 'K', 'total_items')]

    return render_template(
        'report/settlement.html', form=form, report_date=report_date, reports=reports, active_locations_ordered=active_locations_ordered,
        grand_total=grand_total, all_closed=all_closed, unclosed_locations=sorted(list(unclosed_locations)),
        is_settled=is_settled, finance_items=finance_items, sales_items=sales_items
    )

@bp.route('/save_settlement', methods=['POST'])
@login_required
@admin_required
def save_settlement():
    form = SettlementForm()
    if form.validate_on_submit():
        report_date = date.fromisoformat(form.date.data)
        if DailySettlement.query.filter_by(date=report_date).first():
            flash(f"{report_date.strftime('%Y-%m-%d')} 的總結算已歸檔，無法重複儲存。", "warning")
            return redirect(url_for('report.settlement', date=report_date.isoformat()))
        try:
            remarks_dict = {item.key.data: item.value.data for item in form.remarks if item.value.data}
            new_settlement = DailySettlement(date=report_date, total_deposit=form.total_deposit.data, total_next_day_opening_cash=form.total_next_day_opening_cash.data, remarks=json.dumps(remarks_dict))
            db.session.add(new_settlement)
            db.session.commit()
            flash(f"已成功儲存 {report_date.strftime('%Y-%m-%d')} 的總結算資料。", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"儲存時發生錯誤：{e}", "danger")
    else:
        error_messages = [f"欄位 '{getattr(form, field).label.text}' 發生錯誤: {error}" for field, errors in form.errors.items() for error in errors]
        flash("提交的資料有誤，請重試。 " + " ".join(error_messages), "warning")
        return redirect(url_for('report.settlement', date=form.date.data or date.today().isoformat()))
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
    closed_reports = db.session.query(BusinessDay).options(db.joinedload(BusinessDay.location)).filter(BusinessDay.date == report_date, BusinessDay.status == 'CLOSED').all()
    daily_settlement = DailySettlement.query.filter_by(date=report_date).first()
    if not daily_settlement:
        flash("該日期的合併報表尚未結算，無法列印。", "warning")
        return redirect(url_for('report.settlement', date=report_date.isoformat()))
    reports = {r.location.name: r for r in closed_reports}
    active_locations_ordered = [name for name in LOCATION_ORDER if name in reports]
    grand_total_dict = {
        'A': sum(r.expected_cash or 0 for r in closed_reports), 'B': sum(r.total_sales or 0 for r in closed_reports), 'C': sum(r.opening_cash or 0 for r in closed_reports),
        'D': sum(r.closing_cash or 0 for r in closed_reports), 'J': sum(r.total_transactions or 0 for r in closed_reports), 'K': sum(r.total_items or 0 for r in closed_reports),
    }
    grand_total_dict['E'] = grand_total_dict['D'] - grand_total_dict['A']
    grand_total_dict['F'] = sum((r.donation_total or 0) + (r.other_total or 0) for r in closed_reports)
    grand_total_dict['G'] = grand_total_dict['D'] + grand_total_dict['F']
    grand_total_dict['H'] = daily_settlement.total_deposit
    grand_total_dict['I'] = daily_settlement.total_next_day_opening_cash
    class GrandTotal:
        def __init__(self, **entries): self.__dict__.update(entries)
    grand_total = GrandTotal(**grand_total_dict)
    remarks_data = json.loads(daily_settlement.remarks) if daily_settlement and daily_settlement.remarks else {}
    finance_items = [
        ('A', '應有現金', 'A', 'expected_cash'), ('B', '手帳營收', 'B', 'total_sales'), ('C', '開店現金', 'C', 'opening_cash'),
        ('D', '實有現金', 'D', 'closing_cash'), ('E', '溢短收', 'E', 'cash_diff'), ('F', '其他現金', 'F', 'other_cash'),
        ('G', '當日總現金', 'G', 'total_cash'), ('H', '存款', 'H', 'deposit'), ('I', '明日開店現金', 'I', 'next_day_cash')
    ]
    sales_items = [('J', '結單數', 'J', 'total_transactions'), ('K', '品項數', 'K', 'total_items')]
    html_to_render = render_template(
        'report/settlement_print.html', report_date=report_date, reports=reports, active_locations_ordered=active_locations_ordered,
        grand_total=grand_total, remarks_data=remarks_data, finance_items=finance_items, sales_items=sales_items
    )
    pdf = HTML(string=html_to_render).write_pdf()
    return Response(pdf, mimetype="application/pdf", headers={"Content-disposition": f"attachment;filename=settlement_report_{report_date.isoformat()}.pdf"})

@bp.route('/api/settlement_status')
@login_required
@admin_required
def settlement_status_api():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if not year or not month: return jsonify({"error": "Year and month are required"}), 400
    start_date = date(year, month, 1)
    end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    business_days = db.session.query(BusinessDay.date, BusinessDay.status, Location.name).join(Location).filter(BusinessDay.date.between(start_date, end_date)).all()
    settlements = db.session.query(DailySettlement.date).filter(DailySettlement.date.between(start_date, end_date)).all()
    settled_dates = {s.date for s in settlements}
    day_statuses = defaultdict(lambda: {'opened': set(), 'closed': set()})
    for d, status, loc_name in business_days:
        day_statuses[d]['opened'].add(loc_name)
        if status == 'CLOSED': day_statuses[d]['closed'].add(loc_name)
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
    if not year or not month: return jsonify({"error": "Year and month are required"}), 400
    start_date = date(year, month, 1)
    end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    business_days = db.session.query(BusinessDay.date, BusinessDay.status).filter(BusinessDay.date.between(start_date, end_date)).all()
    day_statuses = defaultdict(list)
    for d, status in business_days: day_statuses[d].append(status)
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