ALTER TABLE recognition MODIFY entry_exit_input VARCHAR(50) NULL;
ALTER TABLE recognition MODIFY vehicle_type VARCHAR(50) NULL;

DROP PROCEDURE IF EXISTS InsertRandom;

TRUNCATE TABLE recognition;

DROP PROCEDURE IF EXISTS InsertRandom;

DROP PROCEDURE IF EXISTS InsertExitData;

DROP PROCEDURE IF EXISTS InsertExitData;



CREATE PROCEDURE InsertExitData()
BEGIN
    DECLARE selected_exit_count INT;

    -- entry 차량 수의 70% 계산
    SET selected_exit_count = (SELECT FLOOR(COUNT(*) * 0.7) FROM recognition WHERE entry_exit_input = 'entry');

    -- 랜덤으로 선택한 entry 차량을 임시 테이블에 저장
    CREATE TEMPORARY TABLE temp_exit_ids (id INT);

    INSERT INTO temp_exit_ids (id)
    SELECT id
    FROM recognition
    WHERE entry_exit_input = 'entry'
    ORDER BY RAND()
    LIMIT selected_exit_count;

    -- 임시 테이블을 이용해 entry_exit_input을 'exit'으로 업데이트
    UPDATE recognition r
    JOIN temp_exit_ids t ON r.id = t.id
    SET r.entry_exit_input = 'exit';

    -- 임시 테이블 삭제
    DROP TEMPORARY TABLE IF EXISTS temp_exit_ids;

END //

DELIMITER ;

use cctv_db;
select * from recognition;

DELIMITER //
CREATE PROCEDURE InsertExitData()
BEGIN
    DECLARE selected_exit_count INT; -- 선택된 exit 차량 수
    DECLARE vehicle_ids TEXT; -- vehicle_id 목록을 저장할 변수
    DECLARE query VARCHAR(1000); -- 동적 쿼리 저장할 변수

    -- entry 차량 수의 70% 계산
    SET selected_exit_count = (SELECT FLOOR(COUNT(*) * 0.7) FROM recognition WHERE entry_exit_input = 'entry');

    -- 동적 쿼리로 entry 차량의 id 목록을 랜덤으로 선택하여 하나의 문자열로 합침
    SET query = CONCAT(
        'SELECT GROUP_CONCAT(id ORDER BY RAND() LIMIT ', selected_exit_count, ') INTO @vehicle_ids FROM recognition WHERE entry_exit_input = "entry"'
    );

    -- 동적 쿼리 실행
    PREPARE stmt FROM query;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;

    -- vehicle_ids가 비어있지 않으면 exit으로 업데이트
    IF @vehicle_ids IS NOT NULL AND @vehicle_ids != '' THEN
        UPDATE recognition
        SET entry_exit_input = 'exit'
        WHERE FIND_IN_SET(id, @vehicle_ids) > 0;
    END IF;
END //

DELIMITER ;

DESCRIBE recognition;
DROP PROCEDURE IF EXISTS InsertExitData;

SELECT * 
FROM recognition 
WHERE entry_exit_input = 'exit';


CALL InsertEntryData(1000); -- 예시로 5000개의 입차 데이터를 삽입
CALL InsertExitData(1000);
