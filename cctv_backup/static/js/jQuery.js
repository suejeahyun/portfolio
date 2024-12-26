<script>
  $(document).ready(function() {
    function adjustTableSize() {
      let windowWidth = $(window).width();
      let windowHeight = $(window).height();

      $('#report-table').css({
        width: windowWidth * 0.8 + 'px', // 창 너비의 80%
        maxHeight: windowHeight * 0.6 + 'px', // 창 높이의 60%
        overflowY: 'auto' // 내용이 넘칠 경우 세로 스크롤
      });
    }

    // 처음 로드 시 실행
    adjustTableSize();

    // 창 크기 변경 시 재조정
    $(window).resize(adjustTableSize);
  });
</script>