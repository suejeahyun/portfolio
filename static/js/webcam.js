const videoFeed = document.getElementById("videoFeed");
const startButton = document.getElementById("startButton");
const stopButton = document.getElementById("stopButton");
const captureButton = document.getElementById("captureButton");
const ocrResults = document.getElementById("ocrResults");
const ocrSection = document.querySelector(".ocr-results-section");
const categoryContainer = document.getElementById("categoryContainer");
const category = categoryContainer.dataset.category || "entry";

let webcamStream = null;

// 버튼 상태 초기화
function resetButtons() {
  startButton.style.display = "block";
  stopButton.style.display = "none";
  captureButton.style.display = "none";
  ocrSection.style.display = "none";
}

// 웹캠 시작
startButton.addEventListener("click", () => {
  navigator.mediaDevices
    .getUserMedia({
      video: { width: 1280, height: 720 }, // 해상도 설정
    })
    .then((stream) => {
      videoFeed.srcObject = stream;
      webcamStream = stream;

      startButton.style.display = "none";
      stopButton.style.display = "block";
      captureButton.style.display = "block";
    })
    .catch((err) => {
      console.error("웹캠 시작 오류:", err);
      alert(
        "웹캠을 시작할 수 없습니다. 권한을 확인하거나 관리자에게 문의하세요."
      );
    });
});

// 웹캠 종료
stopButton.addEventListener("click", () => {
  if (webcamStream) {
    webcamStream.getTracks().forEach((track) => track.stop());
    videoFeed.srcObject = null;
  }
  resetButtons();
});

// 이미지 캡처 및 OCR 실행
captureButton.addEventListener("click", () => {
  const canvas = document.createElement("canvas");
  canvas.width = videoFeed.videoWidth;
  canvas.height = videoFeed.videoHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(videoFeed, 0, 0, canvas.width, canvas.height);

  const imageData = canvas.toDataURL("image/jpeg");

  // 서버로 이미지 데이터와 카테고리 전송
  fetch("/capture-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image_data: imageData,
      category: category,
    }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.status === "success") {
        console.log("Server response:", data);

        // OCR 결과를 리스트에 추가
        const listItem = document.createElement("li");
        listItem.textContent = `${data.ocr_text} (${data.image_path})`;
        ocrResults.appendChild(listItem);
        ocrSection.style.display = "block";
      } else {
        console.error("OCR Error:", data.error);
        alert("OCR 처리 중 오류가 발생했습니다: " + data.error);
      }
    })
    .catch((err) => {
      console.error("이미지 전송 오류:", err);
      alert(
        "이미지 데이터를 서버로 전송하는 중 오류가 발생했습니다. 네트워크 상태를 확인하세요."
      );
    });
});
