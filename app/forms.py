from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FloatField, TextAreaField, SelectMultipleField, widgets, SelectField, IntegerField
from wtforms.fields import ColorField
from wtforms.validators import DataRequired, Length, Regexp, EqualTo, ValidationError, Optional
from .models import User, Role, Category

class LoginForm(FlaskForm):
    username = StringField('帳號', validators=[DataRequired(message="請輸入帳號。")])
    password = PasswordField('密碼', validators=[DataRequired(message="請輸入密碼。")])
    submit = SubmitField('登入')

class LocationForm(FlaskForm):
    name = StringField('據點名稱', validators=[DataRequired(message="請輸入据點名稱。"), Length(max=50)])
    slug = StringField('URL Slug', validators=[
        DataRequired(message="請輸入 URL Slug。"), 
        Length(max=50),
        Regexp(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', message='Slug 只能包含小寫英文、數字和連字號 (-)，且不能以連字號開頭或結尾。')
    ])
    submit = SubmitField('儲存')

class CategoryForm(FlaskForm):
    """新增/編輯商品類別的表單"""
    name = StringField('類別名稱', validators=[DataRequired(), Length(1, 50)])
    color = ColorField('按鈕顏色', default='#cccccc', validators=[DataRequired()])
    
    # --- ↓↓↓ 新增/修改的欄位 ↓↓↓ ---
    category_type = SelectField(
        '類別類型',
        choices=[
            ('product', '一般商品 (加法)'),
            ('discount_fixed', '固定金額折扣 (減法)'),
            ('discount_percent', '百分比折扣 (乘法)'),
            ('buy_n_get_m', '買 N 送 M (固定)'),
            ('buy_x_get_x_minus_1', '買 X 送 X-1 (動態)'),
            ('buy_odd_even', '成雙優惠 (奇數件)')
        ],
        validators=[DataRequired()]
    )
    # --- 規則設定欄位 ---
    # `Optional()` 意思是這些欄位不是必填的，因為只有特定折扣類型才需要
    rule_target_category_id = SelectField('目標商品類別', coerce=int, validators=[Optional()])
    rule_buy_n = IntegerField('購買數量 (N)', validators=[Optional()])
    rule_get_m = IntegerField('免費/優惠數量 (M)', validators=[Optional()])
    # --- ↑↑↑ 新增/修改結束 ↑↑↑ ---

    submit = SubmitField('儲存')

    # 動態載入目標商品選項
    def __init__(self, location_id, *args, **kwargs):
        super(CategoryForm, self).__init__(*args, **kwargs)
        self.rule_target_category_id.choices = [
            (c.id, c.name) for c in Category.query.filter_by(
                location_id=location_id, category_type='product'
            ).order_by('name').all()
        ]

class StartDayForm(FlaskForm):
    opening_cash = FloatField('開店準備金 (元)', validators=[
        DataRequired(message="請輸入開店準備金。")
    ])
    location_notes = TextAreaField('備註 (選填)', validators=[Length(max=200)])
    submit = SubmitField('確認開始營業')

class CloseDayForm(FlaskForm):
    submit = SubmitField('送出盤點結果並預覽報表')

class ConfirmReportForm(FlaskForm):
    submit = SubmitField('確認存檔並結束本日營業')

class RoleForm(FlaskForm):
    """新增/編輯角色的表單"""
    name = StringField('角色名稱', validators=[DataRequired(), Length(1, 64)])
    permissions = SelectMultipleField(
        '權限', 
        coerce=str, 
        widget=widgets.ListWidget(prefix_label=False), 
        option_widget=widgets.CheckboxInput()
    )
    submit = SubmitField('儲存')

class UserForm(FlaskForm):
    """新增/編輯使用者的表單"""
    username = StringField('使用者名稱', validators=[DataRequired(), Length(1, 64), Regexp('^[A-Za-z][A-Za-z0-9_.]*$', 0, '使用者名稱只能包含字母、數字、點或底線')])
    password = PasswordField('密碼', validators=[
        EqualTo('password2', message='兩次輸入的密碼必須相符。')
    ])
    password2 = PasswordField('確認密碼')
    roles = SelectMultipleField(
        '角色', 
        coerce=int,
        widget=widgets.ListWidget(prefix_label=False), 
        option_widget=widgets.CheckboxInput()
    )
    submit = SubmitField('儲存')

    def __init__(self, user=None, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.original_user = user
        self.roles.choices = [(r.id, r.name) for r in Role.query.order_by('name').all()]

    def validate_username(self, field):
        if self.original_user is None or self.original_user.username != field.data:
            if User.query.filter_by(username=field.data).first():
                 raise ValidationError('此使用者名稱已被使用。')

class GoogleSettingsForm(FlaskForm):
    """用於管理 Google Drive 和 Sheets 設定的表單"""
    drive_folder_name = StringField(
        'Google Drive 資料夾名稱',
        validators=[DataRequired(message="請輸入資料夾名稱。")],
        description="所有報表將會備份到您 Google Drive 中以此名稱命名的資料夾。"
    )
    sheets_filename_format = StringField(
        'Google Sheets 檔名格式',
        validators=[DataRequired(message="請輸入檔名格式。")],
        description="支援的變數: {location_name}, {location_slug}, {year}, {month}。例如: {location_name}_{year}_業績"
    )
    submit = SubmitField('儲存設定')