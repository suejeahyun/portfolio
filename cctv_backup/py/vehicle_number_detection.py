import cv2
import easyocr

reader = easyocr.Reader(['en','ko'])

# 이미지 로드
image_path = "carimg.jpg"
image = cv2.imread(image_path)

# 그레이스케일 변환
gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# 대비 조정 (선택적)
enhanced_image = cv2.convertScaleAbs(gray_image, alpha=1.5, beta=0)

# 이미지 저장 (디버깅용)
cv2.imwrite('enhanced_image.jpg', enhanced_image)

    # EasyOCR을 사용하여 번호판 인식
result = reader.readtext(enhanced_image)

# 인식된 번호판 텍스트 출력
for detection in result:
    print(f"차 번호: {detection[1]}")