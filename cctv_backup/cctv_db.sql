CREATE DATABASE cctv_db;

use cctv_db;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password VARCHAR(120) NOT NULL,
    email VARCHAR(120) NOT NULL,
    name VARCHAR(80) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL
);
ALTER TABLE users ADD CONSTRAINT unique_name UNIQUE (name);
SHOW CREATE TABLE users;

CREATE TABLE reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    entry_count INT DEFAULT 0,
    exit_count INT DEFAULT 0,
    current_parking_count INT DEFAULT 0,
    start_time DATETIME NULL,  -- DATETIME 형식
    end_time DATETIME NULL,    -- DATETIME 형식
    total_fee INT DEFAULT 0,   -- 총 요금을 정수로 설정
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_name VARCHAR(80)      -- 사용자 이름으로 참조
);

CREATE TABLE recognition (
    id INT AUTO_INCREMENT PRIMARY KEY, -- 고유 ID
    vehicle_number VARCHAR(20) NOT NULL, -- 차량 번호
    phone_number VARCHAR(20), -- 핸드폰 번호
    recognition_time DATETIME DEFAULT CURRENT_TIMESTAMP, -- 인식 시간
    entry_exit_input VARCHAR(10), -- 입차 또는 출차
    vehicle_type VARCHAR(10), -- 차량 종류
    image_path VARCHAR(255) -- 이미지 경로 (옵션)
);

TRUNCATE TABLE entry_recognition;

CALL InsertRandom5(100);

DELETE FROM disabled_vehicle_recognition 
WHERE id NOT IN (
    SELECT id 
    FROM (
        SELECT id 
        FROM disabled_vehicle_recognition 
        ORDER BY recognition_time DESC 
        LIMIT 10
    ) AS temp
);

CREATE TABLE category (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(80) UNIQUE NOT NULL,
    description VARCHAR(255)
);

TRUNCATE TABLE inquiry;

SELECT * FROM illegal_parking_vehicle_recognitioninquiries;

INSERT INTO users (username, password, email, name, phone, role) 
VALUES 
('admin', '$2b$12$frfPuO51upyvC6UNoqTLFOWpJmUptEuwSLHaWjsoV.CHJrsBCGJSi', 'admin@example.com', '관리자', '010-0000-0000', 'admin');

select * from users;
ALTER TABLE inquiry MODIFY COLUMN user_id VARCHAR(80);


use cctv_db;

CREATE TABLE reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    entry_count INT DEFAULT 0,
    exit_count INT DEFAULT 0,
    current_parking_count INT DEFAULT 0,
    start_time DATETIME NULL,
    end_time DATETIME NULL,
    total_fee INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_name VARCHAR(80),
    CONSTRAINT fk_reports_user_name FOREIGN KEY (user_name) REFERENCES users(name)
);

ALTER TABLE reports ADD CONSTRAINT fk_user_name FOREIGN KEY (user_name) REFERENCES users(name);


TRUNCATE TABLE recognition;