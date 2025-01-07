from flask import Flask, request, render_template, redirect, url_for, flash, session, send_file, Response, jsonify, g
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
from sqlalchemy.orm import relationship
from fpdf import FPDF
from PIL import Image
import base64
import io
import cv2
import easyocr
import pandas as pd
import os
import logging

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

# 로그를 파일로 저장합니다. 추가적으로 날짜와 시간, 로그 레벨도 포함하도록 합니다
logging.basicConfig(filename="application.log", level=logging.DEBUG, format='%(asctime)s:%(levelname)s:%(message)s' )

# Secret key for session management
app.secret_key = os.urandom(24)

# MySQL 연결 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:1234@localhost/cctv_db'  # 실제 MySQL 계정 및 데이터베이스명으로 수정
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SQLAlchemy 및 Bcrypt 초기화
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
migrate = Migrate(app, db)  # 마이그레이션 객체 초기화
bcrypt = Bcrypt(app)

# 로그인 확인을 위한 데코레이터
def login_required(f):
    def wrap(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap
            
# 사용자 모델 생성
class User(db.Model):
    __tablename__ = 'users'  # 테이블 이름 명시
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(80), unique=True, nullable=False)  # name에 UNIQUE 제약조건 추가
    phone = db.Column(db.String(20), nullable=False)
    role = db.Column(db.String(20), default='user', nullable=False)  # 역할 필드 추가 (기본값: 'user')

    # User와 Report 간의 관계 설정 (user_name을 name으로 연결)
    reports = relationship('Report', backref='user', primaryjoin="foreign(Report.user_name) == User.name", lazy=True)

    # 역할을 확인하는 메서드 추가
    def is_admin(self):
        return self.role == 'admin'

    def is_user(self):
        return self.role == 'user'

    def is_pending(self):
        return self.role == 'pending'

@app.before_request
def inject_admin_email():
    # id가 'admin'인 사용자 검색
    admin_user = User.query.filter_by(username='admin').first()
    admin_email = admin_user.email if admin_user else "이메일 없음"
    # g 객체에 추가 (템플릿에서 사용 가능)
    g.admin_email = admin_email

# 보고서 모델 생성
class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    entry_count = db.Column(db.Integer, default=0)
    exit_count = db.Column(db.Integer, default=0)
    current_parking_count = db.Column(db.Integer, default=0)
    start_time = db.Column(db.DateTime, nullable=True)  # DATETIME 형식
    end_time = db.Column(db.DateTime, nullable=True)  # DATETIME 형식
    total_fee = db.Column(db.Integer, default=0)  # 정수형으로 변경
    created_at = db.Column(db.DateTime, default=db.func.now())
    
    # 사용자 이름 (외래 키 없이 직접 참조)
    user_name = db.Column(db.String(80), nullable=False)  # 사용자 이름을 저장

# 입차 인식 모델 생성
class EntryRecognition(db.Model):
    __tablename__ = 'entry_recognition'
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(20), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    recognition_time = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(255), nullable=True)

# 출차 인식 모델 생성
class ExitRecognition(db.Model):
    __tablename__ = 'exit_recognition'
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(20), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    recognition_time = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(255), nullable=True)

# 경차 인식 모델 생성
class LightVehicleRecognition(db.Model):
    __tablename__ = 'light_vehicle_recognition'
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(20), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    recognition_time = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(255), nullable=True)

# 장애인 차량 인식 모델 생성
class DisabledVehicleRecognition(db.Model):
    __tablename__ = 'disabled_vehicle_recognition'
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(20), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    recognition_time = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(255), nullable=True)

# 불법 주차 차량 인식 모델 생성
class IllegalParkingVehicleRecognition(db.Model):
    __tablename__ = 'illegal_parking_vehicle_recognition'
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(20), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    recognition_time = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(255), nullable=True)

# 설정 모델 생성
class Setting(db.Model):
    __tablename__ = 'setting'
    id = db.Column(db.Integer, primary_key=True)
    fee_per_10_minutes = db.Column(db.Integer, nullable=False, default=1000)  # 10분당 요금
    total_parking_slots = db.Column(db.Integer, nullable=False, default=50)  # 총 주차 가능 수
    total_floors = db.Column(db.Integer, nullable=False, default=5)          # 층 수

# 홈 페이지
@app.route('/')
def home():
    app.logger.debug('Debug level log') #디버그 메시지
    app.logger.info('Info level log') # 정보 메시지
    app.logger.warning('Warning level log') #경고 메시지
    app.logger.error('Error level log') # 오류 메시지
    app.logger.critical('Critical level log') #크리티컬 메시지
    if 'logged_in' in session:
        return render_template('home.html')  # 로그인된 상태일 때 홈 화면을 렌더링
    return redirect(url_for('login'))  # 로그인되지 않으면 로그인 페이지로 리디렉션


# 로그인 페이지
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            session['logged_in'] = True
            session['username'] = username
            session['role'] = user.role  # 사용자 역할 저장
            flash('로그인 성공!', 'success')
            return redirect(url_for('home'))
        else:
            flash('아이디나 비밀번호가 잘못되었습니다.', 'danger')

    return render_template('login.html')

# 로그아웃 처리
@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    flash("로그아웃되었습니다.", "info")
    return redirect(url_for('login'))


# 회원가입 처리
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        name = request.form['name']
        phone = request.form['phone']

        # 비밀번호 해싱
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # 사용자 객체 생성
        new_user = User(username=username, password=hashed_password, email=email, name=name, phone=phone)

        # DB에 사용자 추가
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('회원가입 성공!', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'오류 발생: {e}', 'danger')

    return render_template('signup.html')

# 모델 맵핑 (모델 이름과 템플릿 이름 연결)
MODEL_TEMPLATE_MAP = {
    'entry-recognition': {
        'model': EntryRecognition,
        'template': 'entry_recognition_list.html',
    },
    'exit-recognition': {
        'model': ExitRecognition,
        'template': 'exit_recognition_list.html',
    },
    'light-vehicle-recognition': {
        'model': LightVehicleRecognition,
        'template': 'light_vehicle_recognition_list.html',
    },
    'disabled-vehicle-recognition': {
        'model': DisabledVehicleRecognition,
        'template': 'disabled_vehicle_recognition_list.html',
    },
    'illegal-parking-vehicle-recognition': {
        'model': IllegalParkingVehicleRecognition,
        'template': 'illegal_parking_vehicle_recognition_list.html',
    },
}

@app.route('/<recognition_type>-data')
@login_required
def recognition_data(recognition_type):
    # 모델과 템플릿을 동적으로 가져오기
    mapping = MODEL_TEMPLATE_MAP.get(recognition_type)
    if not mapping:
        return "Invalid recognition type", 404

    model = mapping['model']
    template = mapping['template']

    # 페이지 번호 가져오기 (기본값: 1)
    page = request.args.get('page', default=1, type=int)
    per_page = 10  # 한 페이지당 표시할 데이터 수

    # 데이터 가져오기 및 페이지네이션 적용
    paginated_data = model.query.order_by(model.recognition_time.desc()) \
                                .paginate(page=page, per_page=per_page, error_out=False)

    # 템플릿으로 데이터 전달
    return render_template(
        template,
        data=paginated_data.items,
        page=paginated_data.page,
        total_pages=paginated_data.pages
    )

# 시간 포맷팅
def formatted_start_time(self):
    if self.start_time:
        return self.start_time.strftime('%Y-%m-%d %H:%M')  # 시작 시간 포맷
    return '공백'

def formatted_end_time(self):
    if self.end_time:
        return self.end_time.strftime('%Y-%m-%d %H:%M')  # 끝 시간 포맷
    return '공백'

@app.route('/<category>_recognition_list')
@login_required
def recognition_list(category):
    # 카테고리 매핑
    allowed_categories = {
        'entry': ('입차 인식', EntryRecognition),
        'exit': ('출차 인식', ExitRecognition),
        'light_vehicle': ('경차 인식', LightVehicleRecognition),
        'disabled_vehicle': ('장애인 차량 인식', DisabledVehicleRecognition),
        'illegal_parking': ('불법 주차 차량 인식', IllegalParkingVehicleRecognition)
    }

    # 카테고리 유효성 검사
    if category not in allowed_categories:
        flash("Invalid category!", "danger")
        return redirect(url_for('search'))

    # 카테고리 이름과 모델 분리
    category_name, model = allowed_categories[category]

    # 페이지 번호 가져오기 (기본값: 1)
    page = request.args.get('page', default=1, type=int)
    per_page = 10

    # 데이터 조회 및 페이지네이션
    paginated_data = model.query.order_by(model.recognition_time.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # 이미지 경로 포함
    data_with_image = [
        {
            'vehicle_number': record.vehicle_number,
            'phone_number': record.phone_number,
            'recognition_time': record.recognition_time.strftime('%Y-%m-%d %H:%M:%S') if record.recognition_time else None,
            'image_path': record.image_path
        } for record in paginated_data.items
    ]
    
    # 공통 템플릿 렌더링
    return render_template(
        'recognition_list.html',
        data=data_with_image,
        page=paginated_data.page,
        total_pages=paginated_data.pages,
        category=category,
        category_name=category_name
    )
# 검색 리스트 페이지
@app.route('/search')
@login_required
def search():
    data = {
        'entry': EntryRecognition.query.order_by(EntryRecognition.recognition_time.desc()).all(),
        'exit': ExitRecognition.query.order_by(ExitRecognition.recognition_time.desc()).all(),
        'light_vehicle': LightVehicleRecognition.query.order_by(LightVehicleRecognition.recognition_time.desc()).all(),
        'disabled_vehicle': DisabledVehicleRecognition.query.order_by(DisabledVehicleRecognition.recognition_time.desc()).all(),
        'illegal_parking': IllegalParkingVehicleRecognition.query.order_by(IllegalParkingVehicleRecognition.recognition_time.desc()).all()
    }
    return render_template('search.html', data=data)

# 검색 결과 페이지
@app.route('/search-results', methods=['GET', 'POST'])
@login_required
def search_results():
    query = None
    results = []

    if request.method == 'POST':
        # 폼에서 입력된 차량 번호 4자리 검색 쿼리를 가져옴
        query = request.form.get('query', '').strip()

        if query and len(query) == 4 and query.isdigit():
            # 모든 테이블에서 해당 번호가 포함된 차량 데이터를 검색 후 정렬
            results = {
                '입차 인식': EntryRecognition.query.filter(
                    EntryRecognition.vehicle_number.like(f'%{query}%')
                ).order_by(EntryRecognition.recognition_time.desc()).all(),
                
                '출차 인식': ExitRecognition.query.filter(
                    ExitRecognition.vehicle_number.like(f'%{query}%')
                ).order_by(ExitRecognition.recognition_time.desc()).all(),
                
                '경차 인식': LightVehicleRecognition.query.filter(
                    LightVehicleRecognition.vehicle_number.like(f'%{query}%')
                ).order_by(LightVehicleRecognition.recognition_time.desc()).all(),
                
                '장애인 차량 인식': DisabledVehicleRecognition.query.filter(
                    DisabledVehicleRecognition.vehicle_number.like(f'%{query}%')
                ).order_by(DisabledVehicleRecognition.recognition_time.desc()).all(),
                
                '불법 주차 차량 인식': IllegalParkingVehicleRecognition.query.filter(
                    IllegalParkingVehicleRecognition.vehicle_number.like(f'%{query}%')
                ).order_by(IllegalParkingVehicleRecognition.recognition_time.desc()).all()
            }

    return render_template('search_results.html', query=query, results=results)

# 알람 현황 페이지
@app.route('/alerts')
@login_required
def alerts():
    # 현재 시간
    now = datetime.utcnow()

    # 3시간 전 시간 계산
    three_hours_ago = now - timedelta(hours=3)

    # 각 카테고리에서 최근 3시간 이내의 데이터를 시간순으로 정렬하여 가져옴
    entry_data = EntryRecognition.query.filter(EntryRecognition.recognition_time >= three_hours_ago).order_by(EntryRecognition.recognition_time.desc()).all()
    exit_data = ExitRecognition.query.filter(ExitRecognition.recognition_time >= three_hours_ago).order_by(ExitRecognition.recognition_time.desc()).all()
    light_vehicle_data = LightVehicleRecognition.query.filter(LightVehicleRecognition.recognition_time >= three_hours_ago).order_by(LightVehicleRecognition.recognition_time.desc()).all()
    disabled_vehicle_data = DisabledVehicleRecognition.query.filter(DisabledVehicleRecognition.recognition_time >= three_hours_ago).order_by(DisabledVehicleRecognition.recognition_time.desc()).all()
    illegal_parking_data = IllegalParkingVehicleRecognition.query.filter(IllegalParkingVehicleRecognition.recognition_time >= three_hours_ago).order_by(IllegalParkingVehicleRecognition.recognition_time.desc()).all()

    # 모든 데이터를 합침
    all_data = entry_data + exit_data + light_vehicle_data + disabled_vehicle_data + illegal_parking_data

    # 시간순으로 정렬 (내림차순)
    all_data.sort(key=lambda x: x.recognition_time, reverse=True)

    # 페이지 번호 가져오기 (기본값은 1)
    page = request.args.get('page', 1, type=int)

    # 10개씩 페이지네이션 적용
    per_page = 10
    start_index = (page - 1) * per_page
    end_index = page * per_page
    paginated_data = all_data[start_index:end_index]

    # 총 페이지 수 계산
    total_pages = len(all_data) // per_page + (1 if len(all_data) % per_page != 0 else 0)

    return render_template(
        'alerts.html',
        all_data=paginated_data,
        page=page,
        total_pages=total_pages
    )


# 긴급 상황 페이지
@app.route('/emergencies')
@login_required  # 로그인된 사용자만 접근 가능
def emergencies():
    return render_template('emergencies.html')

# 보고서 페이지 및 데이터 입력, 표시
@app.route('/report', methods=['GET', 'POST'])
@login_required
def report():
    user_name = session['username']  # 로그인된 사용자의 이름 가져오기

    # 설정 데이터 가져오기
    setting = Setting.query.first()  # 설정에서 10분당 요금을 가져옴
    fee_per_10_minutes = setting.fee_per_10_minutes if setting else 100

    if request.method == 'POST':
        # 출근 버튼 클릭 시 start_time 설정
        if 'start_time_button' in request.form:
            # 퇴근하지 않은 상태인 보고서가 있는지 확인
            existing_report = Report.query.filter_by(user_name=user_name, end_time=None).first()
            if existing_report:
                flash("현재 퇴근하지 않은 상태입니다. 퇴근 후 출근을 할 수 있습니다.", "danger")
            else:
                # 출근 시간은 현재 시간으로 기록
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

        # 퇴근 버튼 클릭 시 end_time 설정
        elif 'end_time_button' in request.form:
            # 퇴근 시간은 현재 시간으로 기록
            end_time = datetime.now()

            # 출근 시간이 기록되지 않은 보고서를 찾음
            report = Report.query.filter_by(user_name=user_name, end_time=None).order_by(Report.start_time.asc()).first()
            if report:
                # 퇴근 시간 설정
                report.end_time = end_time

                # 출근-퇴근 시간 사이의 입차 및 출차 데이터를 가져옴
                entry_records = EntryRecognition.query.filter(
                    EntryRecognition.recognition_time >= report.start_time,
                    EntryRecognition.recognition_time <= end_time
                ).all()

                exit_records = ExitRecognition.query.filter(
                    ExitRecognition.recognition_time >= report.start_time,
                    ExitRecognition.recognition_time <= end_time
                ).all()

                # 입차 수와 출차 수 계산
                report.entry_count = len(entry_records)
                report.exit_count = len(exit_records)

                # 현재 주차 수 계산 (입차 차량 중 출차되지 않은 차량)
                entry_vehicle_numbers = {record.vehicle_number for record in entry_records}
                exit_vehicle_numbers = {record.vehicle_number for record in exit_records}
                report.current_parking_count = len(entry_vehicle_numbers - exit_vehicle_numbers)

                # 총 요금 계산
                total_parking_minutes = sum(
                    (end_time - record.recognition_time).total_seconds() // 60 for record in entry_records
                )
                report.total_fee = (total_parking_minutes // 10) * fee_per_10_minutes

                db.session.commit()
                flash("퇴근 시간이 기록되었습니다!", "success")
            else:
                flash("출근 기록이 없습니다. 출근 버튼을 먼저 눌러주세요.", "danger")

    # GET 요청 시 보고서 목록 가져오기
    page = request.args.get('page', 1, type=int)
    reports = Report.query.filter_by(user_name=user_name).order_by(Report.start_time.desc()).paginate(page=page, per_page=10, error_out=False)

    return render_template('report.html', reports=reports)


    # GET 요청 시 보고서 목록 가져오기
    page = request.args.get('page', 1, type=int)
    reports = Report.query.filter_by(user_name=user_name).order_by(Report.start_time.desc()).paginate(page=page, per_page=10, error_out=False)

    return render_template('report.html', reports=reports)

# 보안 / 로그인 페이지
@app.route('/security',  methods=['GET', 'POST'])
@login_required  # 로그인된 사용자만 접근 가능
def security():
    # 관리자 권한 확인
    if session['username'] != 'admin':  # 예시: 'admin'이 관리자 아이디로 설정
        flash("관리자 권한이 필요합니다.", "danger")
        return redirect(url_for('home'))  # 관리자만 접근 가능

    # 모든 사용자 정보 조회
    users = User.query.all()

    if request.method == 'POST':
        # 사용자 삭제 요청 처리
        user_id_to_delete = request.form.get('user_id_to_delete')
        user_to_delete = User.query.get(user_id_to_delete)
        
        if user_to_delete:
            try:
                db.session.delete(user_to_delete)
                db.session.commit()
                flash(f"사용자 '{user_to_delete.username}'가 삭제되었습니다.", "success")
            except Exception:
                db.session.rollback()
                flash("사용자 삭제에 실패했습니다.", "danger")

    return render_template('security.html', users=users)

# 비디오 피드와 관련 HTML 템플릿
@app.route('/<category>-recognition')
@login_required
def video_recognition(category):
    # 카테고리 정보
    categories = {
        'entry': {
            'title': '입차 인식',
            'video_feed': 'entry_video_feed',
            'list_page': 'entry_recognition_data',
            'button_text': '입차 리스트'
        },
        'exit': {
            'title': '출차 인식',
            'video_feed': 'exit_video_feed',
            'list_page': 'exit_recognition_data',
            'button_text': '출차 리스트'
        },
        'light-vehicle': {
            'title': '경차 인식',
            'video_feed': 'light_vehicle_recognition_video_feed',
            'list_page': 'light_vehicle_recognition_data',
            'button_text': '경차 구역 주차 리스트'
        },
        'disabled-vehicle': {
            'title': '장애인 차량 인식',
            'video_feed': 'disabled_vehicle_recognition_video_feed',
            'list_page': 'disabled_vehicle_recognition_data',
            'button_text': '장애인 구역 주차 리스트'
        },
        'illegal-parking': {
            'title': '불법 주차 인식',
            'video_feed': 'illegal_parking_vehicle_recognition_video_feed',
            'list_page': 'illegal_parking_vehicle_recognition_data',
            'button_text': '불법 주차 리스트'
        }
    }

    if category not in categories:
        flash('잘못된 카테고리입니다.', 'danger')
        return redirect(url_for('home'))

    # 카테고리 데이터 가져오기
    data = categories[category]

    return render_template(
        'video_recognition.html',
        title=data['title'],
        video_feed=data['video_feed'],
        list_page=data['list_page'],
        button_text=data['button_text'],
        category=category 
    )

camera = None  # 전역 카메라 객체

# 웹캠 설정 함수
def setup_camera():
    global camera
    if not camera or not camera.isOpened():
        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            app.logger.error("웹캠 초기화 실패")
            raise RuntimeError("웹캠 초기화 실패")

# 웹캠 종료 함수
@app.teardown_appcontext
def release_camera(exception=None):
    global camera
    if camera and camera.isOpened():
        camera.release()
        app.logger.info("카메라 리소스 해제 완료")

        

# 웹캠 스트리밍을 위한 함수
def generate_frames(category=None):
    global camera

    if not camera or not camera.isOpened():
        app.logger.error(f"카메라 열기 실패: {category}")
        return

    while True:
        success, frame = camera.read()
        if not success:
            app.logger.warning(f"{category} 카테고리: 프레임 읽기 실패")
            break

        # 카테고리에 따른 비디오 오버레이
        if category:
            cv2.putText(frame, f"{category.capitalize()} Feed", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')


    camera.release()

# 웹캠 동적함수
@app.route('/video-feed/<string:category>')
def video_feed(category):
    valid_categories = ['entry', 'exit', 'light-vehicle', 'disabled-vehicle', 'illegal-parking']

    if category not in valid_categories:
        app.logger.error(f"잘못된 카테고리 요청: {category}")
        return jsonify({"error": "Invalid category"}), 400

    return Response(generate_frames(category), mimetype='multipart/x-mixed-replace; boundary=frame')

# 이미지 캡처 후 DB 저장
@app.route('/capture-image', methods=['POST'])
def capture_image():
    # 카테고리와 모델 매핑
    category_models = {
        'entry': EntryRecognition,
        'exit': ExitRecognition,
        'light_vehicle': LightVehicleRecognition,
        'disabled_vehicle': DisabledVehicleRecognition,
        'illegal_parking': IllegalParkingVehicleRecognition
    }

    try:
        # 요청 데이터 확인
        data = request.get_json()
        if not data or 'image_data' not in data or 'category' not in data:
            return jsonify({"status": "error", "error": "Invalid input data"}), 400

        category = data.get('category')
        if category not in category_models:
            return jsonify({"status": "error", "error": "Invalid category"}), 400

        # 모델 선택
        model = category_models[category]

        # 이미지 데이터 디코딩 및 저장
        image_data = data['image_data'].split(",")[1]
        decoded_image = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(decoded_image))
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        save_image_folder = "static/captured_images"
        os.makedirs(save_image_folder, exist_ok=True)
        image_path = os.path.join(save_image_folder, f"{category}_{timestamp}.jpg")
        image.save(image_path)

        # OCR 처리
        reader = easyocr.Reader(['en', 'ko'])
        ocr_results = reader.readtext(image_path)
        vehicle_number = ocr_results[0][1] if ocr_results else "Unknown"

        # 데이터베이스 저장
        new_record = model(
            vehicle_number=vehicle_number,
            phone_number=None,
            recognition_time=datetime.now(),
            image_path=image_path
        )
        db.session.add(new_record)
        db.session.commit()

        return jsonify({
            "status": "success",
            "ocr_text": vehicle_number,
            "image_path": image_path
        })
    except Exception as e:
        app.logger.error(f"Error in /capture-image: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500



# PDF, EXEL 저장
@app.route('/export/<string:category>/<string:file_format>', methods=['GET'])
@login_required
def export_category_data(category, file_format):
    # 카테고리 모델 매핑
    allowed_categories = {
        'entry': EntryRecognition,
        'exit': ExitRecognition,
        'light_vehicle': LightVehicleRecognition,
        'disabled_vehicle': DisabledVehicleRecognition,
        'illegal_parking': IllegalParkingVehicleRecognition,
    }

    if category not in allowed_categories:
        flash("Invalid category!", "danger")
        return redirect(url_for('search'))

    # 데이터 가져오기
    model = allowed_categories[category]
    data = model.query.all()

    # 데이터 프레임 생성
    df = pd.DataFrame([{
        '차량 번호': d.vehicle_number if hasattr(d, 'vehicle_number') else None,
        '핸드폰 번호': d.phone_number if hasattr(d, 'phone_number') else None,
        '인식 시간': d.recognition_time.strftime('%Y-%m-%d %H:%M:%S') if hasattr(d, 'recognition_time') and d.recognition_time else None,
        '이미지 경로': d.image_path if hasattr(d, 'image_path') else None
    } for d in data])

    if file_format == 'pdf':
        # PDF 생성
        file_path = f'{category}_data.pdf'
        pdf = FPDF()
        pdf.add_page()

        # 유니코드 폰트 추가
        font_path = os.path.join('static', 'fonts', 'NanumGothic.ttf')
        pdf.add_font('Nanum', '', font_path, uni=True)
        pdf.set_font('Nanum', size=12)

        # PDF 내용 작성
        pdf.cell(200, 10, txt=f"{category.capitalize()} Data", ln=True, align='C')
        for index, row in df.iterrows():
            pdf.multi_cell(0, 10, txt=f"{row.to_dict()}")
        pdf.output(file_path)
        return send_file(file_path, as_attachment=True)

    elif file_format == 'excel':
        # Excel 생성
        file_path = f'{category}_data.xlsx'
        df.to_excel(file_path, index=False)
        return send_file(file_path, as_attachment=True)

    flash("Invalid file format!", "danger")
    return redirect(url_for('search'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # 관리자 권한 확인
    if session['username'] != 'admin':  # 'admin' 계정만 설정 가능
        flash("관리자 권한이 필요합니다.", "danger")
        return redirect(url_for('home'))

    setting = Setting.query.first()  # 첫 번째 설정 가져오기 (단일 행)
    
    if request.method == 'POST':
        # 폼에서 설정 값 가져오기
        fee = request.form.get('fee_per_10_minutes', type=int)
        total_slots = request.form.get('total_parking_slots', type=int)
        total_floors = request.form.get('total_floors', type=int)
        
        if setting:
            # 기존 설정 업데이트
            setting.fee_per_10_minutes = fee if fee and fee > 0 else setting.fee_per_10_minutes
            setting.total_parking_slots = total_slots if total_slots and total_slots > 0 else setting.total_parking_slots
            setting.total_floors = total_floors if total_floors and total_floors > 0 else setting.total_floors
        else:
            # 새 설정 추가
            setting = Setting(
                fee_per_10_minutes=fee if fee and fee > 0 else 100,
                total_parking_slots=total_slots if total_slots and total_slots > 0 else 50,
                total_floors=total_floors if total_floors and total_floors > 0 else 5
            )
            db.session.add(setting)
        
        db.session.commit()
        flash("설정이 성공적으로 업데이트되었습니다!", "success")
    
    return render_template('settings.html', setting=setting)


# 서버 실행
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
