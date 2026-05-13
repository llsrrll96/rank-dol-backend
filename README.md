# Idol Crawler API

이 프로젝트는 아이돌 그룹 데이터를 크롤링하고 관리하기 위한 FastAPI 기반의 백엔드 서비스입니다. 크롤링된 데이터와 이미지는 Supabase (PostgreSQL & Storage)에 저장됩니다.

## 🚀 주요 기능

- **자동 크롤링**: 외부 사이트에서 아이돌 그룹 정보를 크롤링합니다.
- **이미지 자동 업로드**: 크롤링된 이미지를 Supabase Storage에 자동으로 저장합니다.
- **RESTful API**: 아이돌 그룹 데이터를 조회, 생성, 수정, 삭제하는 API를 제공합니다.
- **중복 방지**: 이미 존재하는 그룹은 크롤링 시 자동으로 건너뜁니다.

## 🛠 기술 스택

- **Framework**: FastAPI
- **Database/Storage**: Supabase (PostgreSQL, Storage)
- **Scraping**: BeautifulSoup4, Playwright (async)
- **Container**: Docker, Docker Compose

## ⚙️ 설정 (Environment Variables)

`.env` 파일을 생성하고 다음 변수들을 설정해야 합니다.

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_or_service_key
SUPABASE_BUCKET=images
```

## 📋 API 명세

### 1. 루트 (Root)
- **URL**: `/`
- **Method**: `GET`
- **설명**: API 서버의 가동 상태를 확인합니다.

### 2. 크롤링 실행 (Trigger Crawl)
- **URL**: `/api/crawl`
- **Method**: `POST`
- **설명**: 백그라운드에서 아이돌 그룹 크롤링 작업을 시작합니다.
- **응답 예시**:
  ```json
  {
    "success": true,
    "message": "Crawling task started in the background."
  }
  ```

### 3. 아이돌 목록 조회 (Get Idols)
- **URL**: `/api/idols`
- **Method**: `GET`
- **설명**: 저장된 모든 아이돌 그룹 목록을 가져옵니다.

### 4. 특정 아이돌 조회 (Get Idol Detail)
- **URL**: `/api/idols/{id}`
- **Method**: `GET`
- **설명**: ID를 사용하여 특정 아이돌 그룹의 상세 정보를 조회합니다.

### 5. 아이돌 생성 (Create Idol)
- **URL**: `/api/idols`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **파라미터**:
  - `name`: (string, 필수) 그룹 이름
  - `image`: (file, 선택) 그룹 이미지 파일
- **설명**: 새로운 아이돌 그룹을 수동으로 생성합니다.

### 6. 아이돌 수정 (Update Idol)
- **URL**: `/api/idols/{id}`
- **Method**: `PUT`
- **Content-Type**: `multipart/form-data`
- **파라미터**:
  - `name`: (string, 선택) 수정할 이름
  - `image`: (file, 선택) 수정할 이미지 파일
- **설명**: 기존 아이돌 그룹의 이름이나 이미지를 수정합니다.

### 7. 아이돌 삭제 (Delete Idol)
- **URL**: `/api/idols/{id}`
- **Method**: `DELETE`
- **설명**: 특정 아이돌 그룹을 삭제하고, 관련 이미지도 Storage에서 제거합니다.

## 🏃 실행 방법

### 로컬 실행
1. 의존성 설치:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
2. 서버 가동:
   ```bash
   uvicorn app.main:app --reload
   ```

### Docker 사용
```bash
docker-compose up --build
```

## 📁 프로젝트 구조
- `app/main.py`: API 엔드포인트 정의
- `app/crawler.py`: 크롤링 로직 (Playwright/BS4)
- `app/storage.py`: Supabase 연동 (DB, Storage)
- `app/schemas.py`: Pydantic 모델 (Request/Response)
