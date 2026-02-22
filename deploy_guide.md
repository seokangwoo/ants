# ANTS INVEST: Oracle Cloud Deployment Guide 🚀

본 문서는 로컬에서 개발된 **ANTS Trading Bot**과 **대시보드**를 오라클 클라우드(OCI) Linux 서버로 이전하여 24시간 안정적으로 구동하는 방법을 설명합니다.

## 1. 서버 준비 (OCI Instance)
*   **OS**: Ubuntu 22.04 LTS 추천
*   **보안 리스트 (Ingress Rules)**: OCI 콘솔에서 아래 포트를 개방해야 합니다.
    *   `8000` (FastAPI Backend)
    *   `80` (HTTP - Nginx 사용 시)

## 2. 코드 배포 (Code Transfer)
서버에 접속한 후 코드를 가져옵니다.
```bash
# Git 사용 시
git clone https://github.com/[your-repo]/antsinvest.git
cd antsinvest

# 또는 SCP로 파일 전송 후 이동
```

## 3. 환경 구축 (Environment Setup)
```bash
# 패키지 업데이트 및 Python 설치
sudo apt update && sudo apt install -y python3-pip python3-venv nginx

# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

## 4. 백그라운드 서비스 등록 (Systemd)
서버가 재부팅되어도 자동으로 실행되도록 서비스로 등록합니다.

### A. 대시보드 API 서비스 (`/etc/systemd/system/ants-api.service`)
```ini
[Unit]
Description=ANTS Dashboard API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/antsinvest
ExecStart=/home/ubuntu/antsinvest/venv/bin/python dashboard/backend/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### B. 트레이딩 봇 서비스 (`/etc/systemd/system/ants-bot.service`)
```ini
[Unit]
Description=ANTS Trading Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/antsinvest
ExecStart=/home/ubuntu/antsinvest/venv/bin/python trade.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**서비스 활성화:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable ants-api ants-bot
sudo systemctl start ants-api ants-bot
```

## 5. 프론트엔드 배포 (Nginx)
`index.html`을 외부에서 접속 가능하게 설정합니다.
1. `dashboard/frontend/index.html` 파일을 `/var/www/html/index.html`로 복사하거나 Nginx 설정에서 루트 경로를 지정합니다.
2. 이제 브라우저에서 `http://[서버-IP]`로 접속하면 대시보드가 열립니다.

## 6. 주의 사항
*   **환경 변수**: `.env` 파일(KIS API Key 등)을 반드시 서버의 프로젝트 루트 폴더에 복사해야 합니다.
*   **시간대**: 오라클 서버의 시간이 KST(한국 표준시)로 설정되어 있는지 확인하세요. (`sudo timedatectl set-timezone Asia/Seoul`)
