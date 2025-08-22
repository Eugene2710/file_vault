# File Vault

A full-stack file management application built with React and Django, designed for efficient file handling and storage.

## 🚀 Technology Stack

### Backend
- Django 4.x (Python web framework)
- Django REST Framework (API development)
- SQLite (Development database)
- Gunicorn (WSGI HTTP Server)
- WhiteNoise (Static file serving)

### Frontend
- React 18 with TypeScript
- TanStack Query (React Query) for data fetching
- Axios for API communication
- Tailwind CSS for styling
- Heroicons for UI elements

### Infrastructure
- Docker and Docker Compose
- MinIO (S3-compatible object storage)
- SQLite database with persistent volumes
- Local file storage with volume mounting

## 📋 Prerequisites

Before you begin, ensure you have installed:
- Docker (20.10.x or higher) and Docker Compose (2.x or higher)
- Node.js (18.x or higher) - for local development
- Python (3.9 or higher) - for local development

## 🛠️ Installation & Setup

### Using Docker (Recommended) - One Command Setup

Start the entire application stack with a single command:

```bash
docker-compose up --build
```

This will spin up:
- **Frontend** (React app) - http://localhost:3000
- **Backend** (Django API) - http://localhost:8000  
- **MinIO** (S3-compatible storage) - http://localhost:9000 (API) / http://localhost:9001 (Console)
- **SQLite database** with persistent volumes

#### What happens during startup:
1. MinIO S3 storage service starts and creates the `file-hub` bucket
2. Backend Django server runs migrations and starts the API server
3. Frontend React app builds and serves the application
4. All data persists in Docker volumes (database, uploaded files, static files)

#### Accessing the services:
- **Web Application**: http://localhost:3000
- **Backend API**: http://localhost:8000/api
- **MinIO Console**: http://localhost:9001 (Login: `minioadmin` / `minioadmin123`)

#### Managing the application:
```bash
# Stop all services
docker-compose down

# Start with logs visible
docker-compose up --build

# Run in background
docker-compose up -d --build

# View logs
docker-compose logs -f

# Rebuild specific service
docker-compose up --build backend
```

### Local Development Setup

#### Backend Setup
1. **Create and activate virtual environment**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create necessary directories**
   ```bash
   mkdir -p media staticfiles data
   ```

4. **Run migrations**
   ```bash
   python manage.py migrate
   ```

5. **Start the development server**
   ```bash
   python manage.py runserver
   ```

#### Frontend Setup
1. **Install dependencies**
   ```bash
   cd frontend
   npm install
   ```

2. **Create environment file**
   Create `.env.local`:
   ```
   REACT_APP_API_URL=http://localhost:8000/api
   ```

3. **Start development server**
   ```bash
   npm start
   ```

## 🌐 Accessing the Application

When using Docker Compose:
- **Frontend Application**: http://localhost:3000
- **Backend API**: http://localhost:8000/api  
- **MinIO S3 Console**: http://localhost:9001 (minioadmin/minioadmin123)

When running locally:
- **Frontend Application**: http://localhost:3000
- **Backend API**: http://localhost:8000/api

## 📝 API Documentation

### File Management Endpoints

#### List Files
- **GET** `/api/files/`
- Returns a list of all uploaded files
- Response includes file metadata (name, size, type, upload date)

#### Upload File
- **POST** `/api/files/`
- Upload a new file
- Request: Multipart form data with 'file' field
- Returns: File metadata including ID and upload status

#### Get File Details
- **GET** `/api/files/<file_id>/`
- Retrieve details of a specific file
- Returns: Complete file metadata

#### Delete File
- **DELETE** `/api/files/<file_id>/`
- Remove a file from the system
- Returns: 204 No Content on success

#### Download File
- Access file directly through the file URL provided in metadata

## ⚡ Rate Limiting

The application includes a built-in rate limiter to prevent abuse and ensure fair usage:

### Configuration
Rate limiting is configured via environment variables:
- `RATE_LIMIT_N_CALLS`: Maximum number of API calls allowed (default: 2)
- `RATE_LIMIT_X_SECONDS`: Time window in seconds (default: 1)

### Behavior
- Uses sliding window algorithm for accurate rate limiting
- Returns HTTP 429 "Call Limit Reached" when limit exceeded
- Applies per-user rate limiting based on client IP or user authentication

### Example
With default settings (2 calls per 1 second):
- User can make 2 API calls within any 1-second window
- 3rd call within the same window returns 429 error
- Rate limit resets as the sliding window moves

## 💾 Storage Limits

The application enforces per-user storage quotas to manage resource usage:

### Configuration
Storage limits are configured via environment variables:
- `TOTAL_STORAGE_LIMIT_Z_MB`: Maximum storage per user in MB (default: 10)

### Behavior
- Tracks total file size for each user across all uploaded files
- Returns HTTP 429 "Storage Quota Exceeded" when limit would be exceeded
- Applies to cumulative storage usage, not individual file sizes

### Example
With default settings (10MB per user):
- User can upload files up to 10MB total storage
- Subsequent uploads that would exceed 10MB return 429 error
- Storage is reclaimed when files are deleted

## 🔧 Development Features

- Hot reloading for both frontend and backend
- React Query DevTools for debugging data fetching
- TypeScript for better development experience
- Tailwind CSS for rapid UI development

## 🐛 Troubleshooting

### Docker Issues

1. **Port Conflicts**
   ```bash
   # If ports are in use, modify docker-compose.yml ports section:
   # 3000 (frontend), 8000 (backend), 9000/9001 (MinIO)
   ```

2. **MinIO Connection Issues**
   ```bash
   # Check MinIO health
   docker-compose logs minio
   
   # Recreate MinIO bucket
   docker-compose up minio-create-bucket
   ```

3. **Database Issues**
   ```bash
   # Reset database (removes all data)
   docker-compose down
   docker volume rm abnormal-file-hub-main_backend_data
   docker-compose up --build
   ```

4. **Clean Start (removes all data)**
   ```bash
   # Stop and remove all containers and volumes
   docker-compose down -v
   docker-compose up --build
   ```

### Local Development Issues

1. **Port Conflicts**
   ```bash
   # If ports 3000 or 8000 are in use:
   # Frontend: npm start -- --port 3001
   # Backend: python manage.py runserver 8001
   ```

2. **File Upload Issues**
   - Maximum file size: 10MB
   - Ensure proper permissions on media directory
   - Check network tab for detailed error messages

3. **Database Issues**
   ```bash
   # Reset database
   rm backend/data/db.sqlite3
   python manage.py migrate
   ```
