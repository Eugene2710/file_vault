# File Hub Backend

Django-based backend for the File Hub application, providing a robust API for file management.

## 🚀 Technology Stack

- Python 3.9+
- Django 4.x
- Django REST Framework
- SQLite (Development database)
- Docker
- WhiteNoise for static file serving

## 📋 Prerequisites

- Python 3.9 or higher
- pip
- Docker (if using containerized setup)
- virtualenv or venv (recommended)

## 🛠️ Installation & Setup

### Local Development

1. **Create and activate virtual environment**
   ```bash
   pip install poetry==1.8.3
   poetry shell
   ```

2. **Install Dependencies**
   ```bash
   poetry install
   ```

3. **Environment Setup**
   Create a `.env` file in the backend directory:
   ```env
   DEBUG=True
   SECRET_KEY=your-secret-key
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```

4. **S3 Minio Container Setup**
   Set up a local S3-compatible object storage using Minio:
   ```bash
   # Create and run Minio container
      docker run --rm -d \
      --name minio \
      -p 9000:9000 \
      -p 9001:9001 \
      -e MINIO_ROOT_USER=minioadmin \
      -e MINIO_ROOT_PASSWORD=minioadmin \
      -v ~/minio-data:/data \
      minio/minio server /data --console-address ":9001"

   # Create bucket using mc (Minio Client)
   docker exec -it minio mc alias set myminio http://localhost:9000 minioadmin minioadmin
   docker exec -it minio mc mb myminio/file-hub-bucket
   ```

   Export AWS credentials
   ```bash
   export AWS_ACCESS_KEY_ID=minioadmin
   export AWS_SECRET_ACCESS_KEY=minioadmin
   export AWS_ENDPOINT_URL=http://localhost:9000
   export AWS_DEFAULT_REGION=us-east-1
   ```
   
   Alternatively, you can access the Minio Console at http://localhost:9001 and create the bucket manually.

5. **Database Setup**
   SQLLite uses a file to persist data as a database. 
   
   Create a directory to store the database file.
   
   The Django app is configured in dettings.py to store the database file under ./data/db.sqlite3

   Create the data folder
   ```bash
   mkdir -p data
   ```

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```
   Note: SQLite database will be automatically created at `db.sqlite3`

6. **Run Development Server**
   ```bash
   python manage.py runserver
   ```
   Access the API at http://localhost:8000/api

### Docker Setup

```bash
# Build the image
docker build -t file-hub-backend .

# Run the container
docker run -p 8000:8000 file-hub-backend
```

## 📁 Project Structure

```
backend/
├── core/           # Project settings and main URLs
├── files/          # File management app
│   ├── models.py   # Data models
│   ├── views.py    # API views
│   ├── urls.py     # URL routing
│   └── tests.py    # Unit tests
├── db.sqlite3      # SQLite database
└── manage.py       # Django management script
```

## 🔌 API Endpoints

### Files API (`/api/files/`)

- `GET /api/files/`: List all files
  - Query Parameters:
    - `search`: Search files by name
    - `sort`: Sort by created_at, name, or size

- `POST /api/files/`: Upload new file
  - Request: Multipart form data
  - Fields:
    - `file`: File to upload
    - `description`: Optional file description

- `GET /api/files/<uuid>/`: Get file details
- `DELETE /api/files/<uuid>/`: Delete file

## 🔒 Security Features

- UUID-based file identification
- WhiteNoise for secure static file serving
- CORS configuration for frontend integration
- Django's built-in security features:
  - CSRF protection
  - XSS prevention
  - SQL injection protection

## 🧪 Testing

```bash
# Run all tests
python manage.py test

# Run specific test file
python manage.py test files.tests
```

## 🐛 Troubleshooting

1. **Database Issues**
   ```bash
   # Reset database
   rm db.sqlite3
   python manage.py migrate
   ```

2. **Static Files**
   ```bash
   python manage.py collectstatic
   ```

3. **Permission Issues**
   - Check file permissions in media directory
   - Ensure write permissions for SQLite database directory

## 📚 Contributing

1. Fork the repository
2. Create your feature branch
3. Write and run tests
4. Commit your changes
5. Push to the branch
6. Create a Pull Request

## 📖 Documentation

- API documentation available at `/api/docs/`
- Admin interface at `/admin/`
- Detailed API schema at `/api/schema/` 