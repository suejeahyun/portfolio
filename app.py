from flask import Flask, request, render_template, redirect, url_for, flash, session, send_file, jsonify, g
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
from sqlalchemy.orm import relationship
from fpdf import FPDF
from PIL import Image
import pandas as pd
import base64
import io
import easyocr
import os
import logging
import re

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Flask 앱 초기화
app = Flask(__name__)
app.secret_key = os.urandom(24)

# 데이터베이스 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:1234@localhost/cctv_db?charset=utf8mb4'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
migrate = Migrate(app, db)

# 로깅 설정
logging.basicConfig(
    filename="application.log",
    level=logging.DEBUG,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

# 원시 비밀번호
plain_password = "1234"

# 비밀번호 해시 생성
hashed_password = bcrypt.generate_password_hash(plain_password).decode('utf-8')
print(hashed_password)
# 전역 카메라 객체
camera = None

# 에러 핸들러
@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled Exception: {str(e)}")
    return render_template("error.html", error=str(e)), 500
# -------------------------------

# 관리자 세션 유효성 검증 함수
# -------------------------------
def admin_required(f):
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or session.get('role') != 'admin':
            flash("관리자 권한이 필요합니다.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function
# -------------------------------

# 데이터베이스 모델
# -------------------------------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(80), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    role = db.Column(db.String(20), default='pending', nullable=False)

    reports = relationship('Report', backref='user', lazy=True)

class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    entry_count = db.Column(db.Integer, default=0)
    exit_count = db.Column(db.Integer, default=0)
    current_parking_count = db.Column(db.Integer, default=0)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    total_fee = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=db.func.now())
    user_name = db.Column(db.String(80), db.ForeignKey('users.name'), nullable=False)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fee_per_10_minutes = db.Column(db.Integer, nullable=False, default=100)
    total_parking_slots = db.Column(db.Integer, nullable=False, default=50)
    total_floors = db.Column(db.Integer, nullable=False, default=5)

class Recognition(db.Model):
    __tablename__ = 'recognition'
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(20), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    recognition_time = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(255), nullable=True)
    entry_exit_input = db.Column(db.String(50), nullable=True, default='entry')
    vehicle_type = db.Column(db.String(50), nullable=True, default='normal')

    @property
    def category(self):
        if self.entry_exit_input == 'entry':
            return '입차'
        elif self.entry_exit_input == 'exit':
            return '출차'
        elif self.entry_exit_input is None:
            if self.vehicle_type == 'light':
                return '경차'
            elif self.vehicle_type == 'disabled':
                return '장애인 차량'
            elif self.vehicle_type == 'illegal':
                return '불법 주차'
            elif self.vehicle_type == 'normal':
                return '일반 차량'
            else:
                return '알 수 없음'
        else:
            return '알 수 없음'

class Inquiry(db.Model):
    __tablename__ = 'inquiry'
    id = db.Column(db.Integer, primary_key=True)  # 고유 ID
    user_name = db.Column(db.String(80), db.ForeignKey('users.name'), nullable=False)  # 사용자 이름 (외래키)
    message = db.Column(db.Text, nullable=False)  # 문의 내용
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # 작성 시간
    state = db.Column(db.String(20), nullable=False, default='receipt')  # 문의 상태

    user = db.relationship('User', backref='inquiries')  # User와 관계 설정

    @property
    def state_label(self):
        state_map = {
            'receipt': '접수',
            'progress': '진행중',
            'complete': '완료',
            'interruption': '중단',
            'custody': '보관'
        }
        return state_map.get(self.state, '알 수 없음')
    
# ORM모델 직접 사용
allowed_categories = {
    'entry': {'entry_exit_input': 'entry', 'vehicle_type': None},
    'exit': {'entry_exit_input': 'exit', 'vehicle_type': None},
    'light_vehicle': {'entry_exit_input': 'entry', 'vehicle_type': 'light'},
    'disabled_vehicle': {'entry_exit_input': 'entry', 'vehicle_type': 'disabled'},
    'illegal_parking': {'entry_exit_input': 'entry', 'vehicle_type': 'illegal'},
}

def get_category_data(category, start_time=None, end_time=None):
    """
    주어진 카테고리와 시간 범위에 따라 Recognition 데이터를 필터링합니다.

    Args:
        category (str): 필터링할 카테고리 (예: 'entry', 'exit').
        start_time (datetime, optional): 필터링 시작 시간.
        end_time (datetime, optional): 필터링 종료 시간.

    Returns:
        list: 필터링된 Recognition 객체 리스트.
    """
    allowed_categories = {
        'entry': {'entry_exit_input': 'entry', 'vehicle_type': None},
        'exit': {'entry_exit_input': 'exit', 'vehicle_type': None},
        'light_vehicle': {'entry_exit_input': 'entry', 'vehicle_type': 'light'},
        'disabled_vehicle': {'entry_exit_input': 'entry', 'vehicle_type': 'disabled'},
        'illegal_parking': {'entry_exit_input': 'entry', 'vehicle_type': 'illegal'},
    }

    if category not in allowed_categories:
        raise ValueError("Invalid category")

    filters = allowed_categories[category]
    query = Recognition.query

    # 카테고리에 따른 기본 필터 적용
    if filters['entry_exit_input']:
        query = query.filter_by(entry_exit_input=filters['entry_exit_input'])
    if filters['vehicle_type']:
        query = query.filter_by(vehicle_type=filters['vehicle_type'])

    # 시간 범위 필터 추가
    if start_time:
        query = query.filter(Recognition.recognition_time >= start_time)
    if end_time:
        query = query.filter(Recognition.recognition_time <= end_time)

    return query.order_by(Recognition.recognition_time.desc()).all()



# -------------------------------

# 로그인 관련 함수
# -------------------------------
def login_required(f):
    def wrap(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            flash("로그인이 필요합니다.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

@app.route('/login', methods=['GET', 'POST'])
def login():
    app.logger.info("로그인 시도")
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            # 로그인 성공 시 세션 설정
            session['logged_in'] = True
            session['username'] = username
            session['role'] = user.role
            session['name'] = user.name  # name 추가
            flash("로그인 성공", "success")
            return redirect(url_for('home'))
        else:
            app.logger.warning(f"로그인 실패 - 사용자: {username}")
            flash("아이디나 비밀번호가 잘못되었습니다.", "danger")
    return render_template('login.html')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    flash("로그아웃되었습니다.", "info")
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        name = request.form['name']
        phone = request.form['phone']

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, password=hashed_password, email=email, name=name, phone=phone)

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('회원가입 성공!', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'오류 발생: {e}', 'danger')

    return render_template('signup.html')
# -------------------------------

# 데이터 필터링
# -------------------------------
@app.route('/recognition-data', methods=['GET'])
@login_required
def get_recognition_data():
    recognition_type = request.args.get('type')  # 'entry' 또는 'exit'
    vehicle_type = request.args.get('vehicle_type')  # 'light', 'disabled', 'illegal', 'normal'

    query = Recognition.query
    if recognition_type:
        query = query.filter_by(entry_exit_input=recognition_type)
    if vehicle_type:
        query = query.filter_by(vehicle_type=vehicle_type)

    data = query.order_by(Recognition.recognition_time.desc()).all()
    return render_template('recognition_list.html', data=data)
# -------------------------------

# 주요 라우트
# -------------------------------
@app.route('/')
def home():
    if 'logged_in' in session and session.get('role') in ['admin', 'user']:
        return render_template('home.html')
    return redirect(url_for('login'))


@app.route('/search')
@login_required
def search():
    data = {
        'entry': Recognition.query.filter_by(entry_exit_input='entry').order_by(Recognition.recognition_time.desc()).all(),
        'exit': Recognition.query.filter_by(entry_exit_input='exit').order_by(Recognition.recognition_time.desc()).all(),
        'light_vehicle': Recognition.query.filter_by(vehicle_type='light').order_by(Recognition.recognition_time.desc()).all(),
        'disabled_vehicle': Recognition.query.filter_by(vehicle_type='disabled').order_by(Recognition.recognition_time.desc()).all(),
        'illegal_parking': Recognition.query.filter_by(vehicle_type='illegal').order_by(Recognition.recognition_time.desc()).all(),
    }

    return render_template('search.html', data=data)

# 전역 OCR Reader 객체 생성
ocr_reader = easyocr.Reader(['en', 'ko'])

@app.route('/capture-image', methods=['POST'])
def capture_image():
    data = request.get_json()
    if not data or 'image_data' not in data or 'category' not in data:
        return jsonify({"status": "error", "error": "Invalid input data"}), 400

    # 카테고리 조건 설정
    category_models = {
        'entry': {'entry_exit_input': 'entry', 'vehicle_type': 'normal'},
        'exit': {'entry_exit_input': 'exit', 'vehicle_type': 'normal'},
        'light_vehicle': {'entry_exit_input': 'entry', 'vehicle_type': 'light'},
        'disabled_vehicle': {'entry_exit_input': 'entry', 'vehicle_type': 'disabled'},
        'illegal_parking': {'entry_exit_input': 'entry', 'vehicle_type': 'illegal'}
    }

    category = data.get('category', '').replace('-', '_')
    app.logger.info(f"Received category: {category}")

    if category not in category_models:
        app.logger.error(f"Invalid category received: {category}")
        return jsonify({"status": "error", "error": "Invalid category"}), 400

    model_conditions = category_models[category]

    image_data = data['image_data'].split(",")[1]
    decoded_image = base64.b64decode(image_data)
    image = Image.open(io.BytesIO(decoded_image))

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    save_image_folder = os.path.join("static", "captured_images", category)
    os.makedirs(save_image_folder, exist_ok=True)

    image_filename = f"{timestamp}.jpg"
    image_path = os.path.join(save_image_folder, image_filename)
    image.save(image_path)

    image_db_path = f"captured_images/{category}/{image_filename}"
    app.logger.info(f"저장된 이미지 경로: {image_path}")

    try:
        ocr_results = ocr_reader.readtext(image_path)
        detected_text = ocr_results[0][1] if ocr_results else "Unknown"
    except Exception as e:
        app.logger.error(f"OCR 처리 중 오류: {str(e)}")
        detected_text = "Unknown"

    # OCR 결과에서 숫자만 추출
    numeric_text = re.sub(r'\D', '', detected_text)  # 숫자가 아닌 문자는 제거

    phone_number = None
    vehicle_number = None

    # 전화번호와 차량 번호를 분리하여 저장
    if len(numeric_text) == 11:  # 숫자가 11자리이면 전화번호로 저장
        phone_number = numeric_text
    elif numeric_text:  # 숫자가 있으나 11자리가 아닌 경우 차량 번호로 저장
        vehicle_number = numeric_text
    else:  # 숫자가 없으면 전체 텍스트를 차량 번호로 저장
        vehicle_number = detected_text

    # 데이터베이스에 저장
    new_record = Recognition(
        vehicle_number=vehicle_number,
        phone_number=phone_number,
        recognition_time=datetime.now(),
        image_path=image_db_path,
        entry_exit_input=model_conditions.get('entry_exit_input', 'unknown'),
        vehicle_type=model_conditions.get('vehicle_type', 'normal')
    )

    db.session.add(new_record)
    try:
        db.session.commit()
        app.logger.info("데이터베이스에 이미지 경로 및 OCR 결과 저장 완료")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"데이터베이스 저장 중 오류: {str(e)}")
        return jsonify({"status": "error", "error": "Failed to save record to database"}), 500

    return jsonify({
        "status": "success",
        "ocr_text": detected_text,
        "phone_number": phone_number,
        "vehicle_number": vehicle_number,
        "image_path": image_db_path
    })


# -------------------------------

# 카테고리별 비디오 인식 라우트
# -------------------------------

@app.route('/<category>-recognition', methods=['GET'])
@login_required
def video_recognition(category):
    # 카테고리별 정보 매핑
    categories = {
        'entry': {
            'title': '입차 인식',
            'video_feed': 'entry_video_feed',
            'list_page': 'entry_recognition_list',
            'button_text': '입차 리스트'
        },
        'exit': {
            'title': '출차 인식',
            'video_feed': 'exit_video_feed',
            'list_page': 'exit_recognition_list',
            'button_text': '출차 리스트'
        },
        'light-vehicle': {
            'title': '경차 인식',
            'video_feed': 'light_vehicle_video_feed',
            'list_page': 'light_vehicle_recognition_list',
            'button_text': '경차 리스트'
        },
        'disabled-vehicle': {
            'title': '장애인 차량 인식',
            'video_feed': 'disabled_vehicle_video_feed',
            'list_page': 'disabled_vehicle_recognition_list',
            'button_text': '장애인 차량 리스트'
        },
        'illegal-parking': {
            'title': '불법 주차 인식',
            'video_feed': 'illegal_parking_video_feed',
            'list_page': 'illegal_parking_recognition_list',
            'button_text': '불법 주차 리스트'
        },
    }

    # 유효한 카테고리 확인
    if category not in categories:
        flash("잘못된 카테고리 요청입니다.", "danger")
        return redirect(url_for('home'))

    # 카테고리 데이터 전달
    data = categories[category]
    return render_template(
        'video_recognition.html',
        title=data['title'],
        video_feed=data['video_feed'],
        list_page=data['list_page'],
        button_text=data['button_text'],
        category=category
    )
# -------------------------------

# 보안 관련 라우트 및 기능
# -------------------------------

@app.route('/security', methods=['GET', 'POST'])
@login_required
def security():
    # 관리자 권한 확인
    if session.get('role') != 'admin':
        flash("관리자만 접근할 수 있습니다.", "danger")
        return redirect(url_for('home'))

    # 모든 사용자 정보 가져오기
    users = User.query.all()
    return render_template('security.html', users=users)
# -------------------------------

# 유저 role 승인 및 삭제 라우트 및 기능
# -------------------------------

@app.route('/update-role', methods=['POST'])
@login_required
def update_role():
    if session.get('role') != 'admin':
        flash("관리자만 접근할 수 있습니다.", "danger")
        return redirect(url_for('security'))

    user_id = request.form.get('user_id')
    new_role = request.form.get('new_role')

    user = User.query.get(user_id)
    if not user:
        flash("사용자를 찾을 수 없습니다.", "danger")
        return redirect(url_for('security'))

    try:
        user.role = new_role
        db.session.commit()
        flash(f"사용자 '{user.username}'의 역할이 '{new_role}'로 변경되었습니다.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"역할 업데이트 중 오류 발생: {str(e)}", "danger")

    return redirect(url_for('security'))

@app.route('/delete-user', methods=['POST'])
@login_required
def delete_user():
    if session.get('role') != 'admin':
        flash("관리자만 접근할 수 있습니다.", "danger")
        return redirect(url_for('security'))

    user_id = request.form.get('user_id_to_delete')
    user = User.query.get(user_id)

    if not user:
        flash("사용자를 찾을 수 없습니다.", "danger")
        return redirect(url_for('security'))

    try:
        db.session.delete(user)
        db.session.commit()
        flash(f"사용자 '{user.username}'가 삭제되었습니다.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"사용자 삭제 중 오류 발생: {str(e)}", "danger")

    return redirect(url_for('security'))

# -------------------------------

# 문의 사항 관련 라우트 및 기능
# -------------------------------
@app.route('/inquiry_write', methods=['GET', 'POST'])
@login_required
def inquiry_write():
    # 사용자 역할 확인
    user_role = session.get('role')
    if user_role != 'user':  # 'user' 역할만 접근 가능
        app.logger.warning("접근 권한 없음: 사용자 역할이 'user'가 아님")
        flash("일반 사용자만 이 기능을 사용할 수 있습니다.", "danger")
        return redirect(url_for('home'))

    # GET 요청: 문의 작성 페이지 렌더링
    if request.method == 'GET':
        app.logger.info("문의 작성 페이지 접근")
        return render_template('inquiry_write.html')

    # POST 요청: 문의 제출
    username = session.get('username')
    if not username:
        app.logger.error("세션에 username이 없음")
        flash("로그인이 필요합니다.", "danger")
        return redirect(url_for('login'))
    
    user = User.query.filter_by(username=username).first()
    if not user:
        app.logger.error(f"유효하지 않은 사용자: {username}")
        flash("잘못된 사용자입니다. 다시 로그인하세요.", "danger")
        return redirect(url_for('login'))

    # 메시지 가져오기 및 검증
    message = request.form.get('message', '').strip()
    if not message:
        app.logger.warning("빈 메시지 제출")
        flash("문의 내용을 입력하세요.", "warning")
        return render_template('inquiry_write.html')

    # 문의 저장
    new_inquiry = Inquiry(user_name=user.name, message=message, state='receipt')  # user_name을 사용
    try:
        db.session.add(new_inquiry)
        db.session.commit()
        app.logger.info(f"문의 사항 저장 완료: {new_inquiry.id}")
        flash("문의 사항이 성공적으로 제출되었습니다!", "success")
        return redirect(url_for('inquiry'))
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"문의 사항 저장 중 오류: {e}")
        flash("문의 사항 제출 중 오류가 발생했습니다. 다시 시도해주세요.", "danger")
        return render_template('inquiry_write.html')  # 에러가 발생했을 때도 폼을 다시 렌더링
    
@app.route('/inquiry', methods=['GET'])
@login_required
def inquiry():
    username = session.get('username')
    if not username:
        app.logger.error("세션에 username이 없음")
        flash("로그인이 필요합니다.", "danger")
        return redirect(url_for('login'))

    # 페이지네이션을 위한 페이지 번호 파라미터
    page = request.args.get('page', 1, type=int)  # 기본값은 1
    per_page = 10  # 한 페이지에 표시할 문의 사항 수

    # 'user_name'을 기준으로 Inquiry 데이터를 불러오고, User 관계를 서브쿼리로 로드
    inquiries = Inquiry.query.order_by(Inquiry.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # 총 페이지 수와 현재 페이지를 템플릿에 전달
    total_pages = inquiries.pages
    inquiries_list = inquiries.items  # 현재 페이지의 문의 사항 목록

    # 문의사항이 없을 경우 메시지 표시
    if not inquiries_list:
        flash("최근 문의사항이 없습니다.", "info")

    app.logger.info(f"{len(inquiries_list)}개의 문의사항을 불러왔습니다.")
    return render_template('inquiry.html', 
                           inquiries=inquiries_list, 
                           total_pages=total_pages, 
                           current_page=page)

@app.route('/inquiry/update/<int:inquiry_id>', methods=['POST'])
@login_required
def update_inquiry_state(inquiry_id):
    user_role = session.get('role')
    if user_role != 'admin':
        flash('권한이 없습니다.', 'danger')
        return redirect(url_for('inquiry'))

    inquiry = Inquiry.query.get_or_404(inquiry_id)
    new_state = request.form.get('state')

    valid_states = ['receipt', 'progress', 'complete', 'interruption', 'custody']
    if new_state in valid_states:
        inquiry.state = new_state
        db.session.commit()
        flash('문의 상태가 업데이트되었습니다.', 'success')
    else:
        flash('잘못된 상태 값입니다.', 'danger')

    return redirect(url_for('inquiry'))
# -------------------------------

# 각 카테고리 별 검색 라우트 및 기능
# -------------------------------
@app.route('/search-results', methods=['GET', 'POST'])
@login_required
def search_results():
    query = None
    results = {}

    if request.method == 'POST':
        query = request.form.get('query', '').strip()

        if query and len(query) == 4 and query.isdigit():
            results = {
                '입차 인식': Recognition.query.filter(
                    Recognition.entry_exit_input == 'entry',
                    Recognition.vehicle_number.like(f'%{query}%')
                ).order_by(Recognition.recognition_time.desc()).all(),

                '출차 인식': Recognition.query.filter(
                    Recognition.entry_exit_input == 'exit',
                    Recognition.vehicle_number.like(f'%{query}%')
                ).order_by(Recognition.recognition_time.desc()).all(),

                '경차 인식': Recognition.query.filter(
                    Recognition.vehicle_type == 'light',
                    Recognition.vehicle_number.like(f'%{query}%')
                ).order_by(Recognition.recognition_time.desc()).all(),

                '장애인 차량 인식': Recognition.query.filter(
                    Recognition.vehicle_type == 'disabled',
                    Recognition.vehicle_number.like(f'%{query}%')
                ).order_by(Recognition.recognition_time.desc()).all(),

                '불법 주차 차량 인식': Recognition.query.filter(
                    Recognition.vehicle_type == 'illegal',
                    Recognition.vehicle_number.like(f'%{query}%')
                ).order_by(Recognition.recognition_time.desc()).all(),
            }

    return render_template('search_results.html', query=query, results=results)

# -------------------------------

# 기타 사항 / 카테고리 리스트 및 검색 결과 라우트
# -------------------------------
@app.route('/recognition-list/<string:category>', methods=['GET'])
@login_required
def recognition_list(category):
    # get_category_data 함수 사용
    try:
        data = get_category_data(category)
    except ValueError:
        flash("Invalid category!", "danger")
        return redirect(url_for('search'))

    # 페이지네이션 추가
    page = request.args.get('page', 1, type=int)
    per_page = 10
    total_pages = (len(data) + per_page - 1) // per_page
    paginated_data = data[(page - 1) * per_page: page * per_page]

    return render_template(
        'recognition_list.html',
        data=paginated_data,
        page=page,
        total_pages=total_pages,
        category=category
    )

# -------------------------------

# 기타 사항 / 출퇴근 목록 페이지
# -------------------------------
@app.route('/work', methods=['GET'])
@login_required
def work():
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # 세션에서 role 확인
    if session['role'] == 'admin':
        # 관리자는 모든 기록 조회 가능
        reports = Report.query.order_by(Report.start_time.desc()).paginate(page=page, per_page=per_page)
    else:
        # 일반 사용자는 자신의 기록만 조회
        reports = Report.query.filter_by(user_name=session['name']).order_by(Report.start_time.desc()).paginate(page=page, per_page=per_page)

    return render_template('work.html', reports=reports)
# -------------------------------

# 보고서 페이지 및 데이터 입력, 표시
# -------------------------------
@app.route('/report', methods=['GET', 'POST'])
@login_required
def report():
    user_name = session['name']
    setting = Setting.query.first()
    fee_per_10_minutes = setting.fee_per_10_minutes if setting else 100

    if request.method == 'POST':
        if 'start_time_button' in request.form:
            existing_report = Report.query.filter_by(user_name=user_name, end_time=None).first()
            if existing_report:
                flash("이미 출근 상태입니다. 퇴근 후 다시 출근하세요.", "danger")
            else:
                start_time = datetime.now()
                new_report = Report(
                    entry_count=0,
                    exit_count=0,
                    current_parking_count=0,
                    start_time=start_time,
                    end_time=None,
                    total_fee=0,
                    user_name=user_name
                )
                db.session.add(new_report)
                db.session.commit()
                flash("출근 시간이 기록되었습니다!", "success")

        elif 'end_time_button' in request.form:
            end_time = datetime.now()
            report = Report.query.filter_by(user_name=user_name, end_time=None).first()
            if report:
                report.end_time = end_time

                # 입차 및 출차 기록을 시간 범위로 필터링
                entry_records = get_category_data('entry', start_time=report.start_time, end_time=end_time)
                exit_records = get_category_data('exit', start_time=report.start_time, end_time=end_time)

                # 입차 수와 출차 수 계산
                report.entry_count = len(entry_records)
                report.exit_count = len(exit_records)

                # 입차 차량 번호와 출차 차량 번호 집합 생성
                entry_vehicle_numbers = {record.vehicle_number for record in entry_records}
                exit_vehicle_numbers = {record.vehicle_number for record in exit_records}

                # 현재 주차 수 계산: 입차한 차량 중 아직 출차하지 않은 차량 카운트
                # entry 차량 번호 중 exit 차량 번호에 포함되지 않은 차량 번호가 현재 주차된 차량입니다.
                current_parking_vehicles = entry_vehicle_numbers - exit_vehicle_numbers
                report.current_parking_count = len(current_parking_vehicles)

                # 총 주차 시간 계산 (분 단위)
                total_parking_minutes = sum(
                    (end_time - record.recognition_time).total_seconds() // 60 for record in entry_records
                )
                # 총 요금 계산
                report.total_fee = (total_parking_minutes // 10) * fee_per_10_minutes

                db.session.commit()
                flash("퇴근 시간이 기록되었습니다!", "success")
            else:
                flash("출근 기록이 없습니다. 출근 버튼을 눌러주세요.", "danger")

    # 페이지네이션
    page = request.args.get('page', 1, type=int)
    reports = Report.query.filter_by(user_name=user_name).order_by(Report.start_time.desc()).paginate(page=page, per_page=10, error_out=False)

    return render_template('report.html', reports=reports)
# -------------------------------

# 기타 사항 / 알람 페이지
# -------------------------------
@app.route('/alerts', methods=['GET'])
@login_required
def alerts():
    now = datetime.utcnow()
    three_hours_ago = now - timedelta(hours=3)

    query = Recognition.query.filter(
        Recognition.recognition_time >= three_hours_ago
    ).order_by(Recognition.recognition_time.desc())

    page = request.args.get('page', 1, type=int)
    paginated_data = query.paginate(page=page, per_page=10, error_out=False)

    return render_template(
        'alerts.html',
        all_data=paginated_data.items,
        page=paginated_data.page,
        total_pages=paginated_data.pages
    )
# -------------------------------

# 기타 사항 / 환경 설정
# -------------------------------
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    setting = Setting.query.first()
    if request.method == 'POST':
        fee = request.form.get('fee_per_10_minutes', type=int)
        total_slots = request.form.get('total_parking_slots', type=int)
        total_floors = request.form.get('total_floors', type=int)

        if fee <= 0 or total_slots <= 0 or total_floors <= 0:
            flash("설정 값은 0보다 커야 합니다.", "danger")
            return redirect(url_for('settings'))

        if setting:
            setting.fee_per_10_minutes = fee
            setting.total_parking_slots = total_slots
            setting.total_floors = total_floors
        else:
            setting = Setting(fee_per_10_minutes=fee, total_parking_slots=total_slots, total_floors=total_floors)
            db.session.add(setting)
        db.session.commit()
        flash("환경 설정이 성공적으로 업데이트되었습니다!", "success")
    return render_template('settings.html', setting=setting)
# -------------------------------

# 기타 사항 / PDF, EXCEL
# -------------------------------
@app.route('/export/<string:category>/<string:file_format>', methods=['GET'])
@login_required
def export_category_data(category, file_format):
    data = get_category_data(category)
    df = pd.DataFrame([{
        '차량 번호': record.vehicle_number,
        '핸드폰 번호': record.phone_number,
        '인식 시간': record.recognition_time.strftime('%Y-%m-%d %H:%M:%S') if record.recognition_time else None,
        '이미지 경로': record.image_path
    } for record in data])

    folder_path = os.path.join('static', category)
    os.makedirs(folder_path, exist_ok=True)

    if file_format == 'pdf':
        file_path = os.path.join(folder_path, f'{category}_data.pdf')
        pdf = FPDF()
        pdf.add_page()

        # NanumGothic 폰트 추가
        pdf.add_font('NanumGothic', '', 'static/fonts/NanumGothic.ttf', uni=True)
        pdf.set_font('NanumGothic', size=12)

        pdf.cell(200, 10, txt=f"{category.capitalize()} Data", ln=True, align='C')
        for _, row in df.iterrows():
            row_text = ", ".join([f"{key}: {value}" for key, value in row.to_dict().items()])
            pdf.cell(200, 10, txt=row_text, ln=True)

        pdf.output(file_path)
        return send_file(file_path, as_attachment=True)

    elif file_format == 'excel':
        file_path = os.path.join(folder_path, f'{category}_data.xlsx')
        df.to_excel(file_path, index=False)
        return send_file(file_path, as_attachment=True)

    flash("유효하지 않은 파일 형식입니다.", "danger")
    return redirect(url_for('search'))

# -------------------------------

# 관리자 이메일 가져오는 라우트
# -------------------------------
@app.before_request
def inject_admin_email():
    # 관리자 계정을 검색
    admin_user = User.query.filter_by(role='admin').first()
    
    # 관리자 이메일을 g 객체에 저장
    g.admin_email = admin_user.email if admin_user else "관리자 이메일 없음"
# -------------------------------

# 서버 실행
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
