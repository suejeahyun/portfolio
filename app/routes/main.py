from flask import render_template, request, Response, Blueprint, url_for, redirect
from app.models import DailyCount
import logging
import pandas as pd
import matplotlib
from datetime import datetime

matplotlib.use('Agg')

main_bp = Blueprint('main', __name__, template_folder='../templates')

# ✅ 모든 요청 로깅
@main_bp.before_request
def log_request_info():
    logging.info(f"📌 요청: {request.method} {request.url}")

@main_bp.route("/")
def home():
    logging.info("✅ 홈 페이지 접속")
    return render_template("home.html")

@main_bp.route("/standard")
def standard_cam():
    logging.info("✅ Standard 페이지 접속")
    return render_template("standard.html")

@main_bp.route("/break")
def break_cam():
    logging.info("✅ break 페이지 접속")
    return render_template("break.html")

@main_bp.route("/dashboard", methods=["GET"])
def dashboard():
    logging.info("✅ Dashboard 접속")
    
    from app.utils import create_pie_chart, create_bar_chart, create_daily_bar_chart, create_daily_line_chart

    today = datetime.today().strftime("%Y-%m-%d")
    # 날짜 범위 파라미터 받아오기
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    pie_chart_path = None
    bar_chart_path = None
    daily_bar_chart_path = None
    daily_line_chart_path = None  

    if start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        logging.info("🚨 날짜 범위 미설정")
        return render_template("dashboard.html", error_message="날짜 범위를 설정해 주세요.")
    
    # 데이터 쿼리
    daily_counts = DailyCount.query.filter(DailyCount.date >= start_date, DailyCount.date <= end_date).all()    

    # 당일 데이터 조회 처리
    if start_date == end_date == today:
        if not daily_counts:
            logging.info("🚨 당일 데이터 조회 불가")
            return render_template(
                "dashboard.html",
                error_message="당일 데이터 조회는 불가능합니다. 데이터를 저장한 후 실행해 주세요."
            )
        
        logging.info("✅ 당일 데이터 조회 완료")        
        return render_template(
            "dashboard.html",
            start_date=start_date.date(),
            end_date=end_date.date(),
            pie_chart=pie_chart_path,
            bar_chart=bar_chart_path
        )

    if start_date > end_date :
        logging.info("🚨 날짜 범위 재설정")
        return render_template("dashboard.html", error_message="시작 날짜가 끝 날짜 이전으로 다시 설정해 주세요.")
    
  
    if not daily_counts:
        logging.warning(f"🚨 {start_date.date()} ~ {end_date.date()} 기간 데이터 없음")
        return render_template(
            "dashboard.html",
            error_message="해당 기간의 데이터가 존재하지 않습니다.",
            start_date=start_date.date(),
            end_date=end_date.date(),
            pie_chart=pie_chart_path,
            bar_chart=bar_chart_path,
            daily_bar_chart=daily_bar_chart_path,
            daily_line_chart=daily_line_chart_path
        )
    
    # 데이터프레임 변환 및 그래프 생성
    data = {
        "date": [log.date.strftime("%Y-%m-%d") if hasattr(log.date, "strftime") else log.date for log in daily_counts],
        "standard": [log.final_standard_count for log in daily_counts],
        "break": [log.final_break_count for log in daily_counts],
        "normal": [log.final_normal_count for log in daily_counts]
    }
    df = pd.DataFrame(data)

    total_standard = df["standard"].sum()
    total_break = df["break"].sum()
    total_normal = df["normal"].sum()

    pie_chart_path = create_pie_chart(total_standard, total_break, total_normal)
    bar_chart_path = create_bar_chart(total_standard, total_break, total_normal)

    if (start_date != end_date) :
        daily_bar_chart_path = create_daily_bar_chart(df)
        daily_line_chart_path = create_daily_line_chart(df)

    logging.info(f"✅ 그래프 생성 완료: {start_date.date()} ~ {end_date.date()}")

    return render_template(
        "dashboard.html",
        pie_chart=pie_chart_path,
        bar_chart=bar_chart_path,
        daily_bar_chart=daily_bar_chart_path,
        daily_line_chart=daily_line_chart_path,
        start_date=start_date.date(),
        end_date=end_date.date()
    )

@main_bp.route('/standard_frame')
def standard_frame():
    from app.utils import standard_frame
    logging.info("🎥 Video Feed 1 스트리밍 시작")
    return Response(standard_frame(), mimetype='multipart/x-mixed-replace; boundary=frame')

@main_bp.route('/break_frame')
def break_frame():
    from app.utils import break_frame
    logging.info("🎥 Video Feed 2 스트리밍 시작")
    return Response(break_frame(), mimetype='multipart/x-mixed-replace; boundary=frame')

@main_bp.route("/update_daily_counts", methods=["GET"])
def update_daily_counts_route():
    from app.utils.update_daily_final_counts import update_daily_final_counts

    try:
        update_daily_final_counts()
        logging.info("✅ DailyCount 업데이트 완료")
    except Exception as e:
        logging.error(f"🚨 DailyCount 업데이트 실패: {str(e)}")

    return redirect(request.referrer or url_for("main.home"))
