#!/bin/bash

# ReadFlow Project Setup Script
# Initializes all services and creates required resources

set -e  # Exit on error

echo "========================================="
echo "  ReadFlow Setup & Initialization"
echo "========================================="
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check prerequisites
echo "1. Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi
print_success "Docker is installed"

if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi
print_success "Docker Compose is installed"

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.9+ first."
    exit 1
fi
print_success "Python 3 is installed"

echo ""

# Create directory structure
echo "2. Creating directory structure..."

directories=(
    "data/landing"
    "data/warehouse"
    "data/logs"
    "airflow/logs"
    "airflow/plugins"
    "spark/logs"
    "analytics/cache"
)

for dir in "${directories[@]}"; do
    mkdir -p "$dir"
    print_success "Created $dir"
done

echo ""

# Create .env file if it doesn't exist
echo "3. Setting up environment configuration..."

if [ ! -f .env ]; then
    cp .env.example .env
    print_success "Created .env file from template"
    print_warning "Please edit .env and add your GoodReads API key"
else
    print_success ".env file already exists"
fi

echo ""

# Install Python dependencies
echo "4. Installing Python dependencies..."

if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_success "Created virtual environment"
fi

source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
print_success "Installed Python dependencies"

echo ""

# Initialize Airflow database
echo "5. Initializing Airflow..."

export AIRFLOW_HOME=$(pwd)/airflow

# Create Airflow user script
cat > airflow/init_airflow.sh << 'EOF'
#!/bin/bash
airflow db init
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin
EOF

chmod +x airflow/init_airflow.sh
print_success "Airflow initialization script created"

echo ""

# Create MinIO initialization script
echo "6. Creating MinIO setup script..."

cat > scripts/init_minio_buckets.py << 'EOF'
"""Initialize MinIO buckets and folder structure"""

from minio import Minio
from minio.error import S3Error
import os
from dotenv import load_dotenv

load_dotenv()

def init_minio():
    """Create MinIO buckets and folder structure"""
    
    # Initialize MinIO client
    client = Minio(
        os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
        access_key=os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
        secret_key=os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
        secure=False
    )
    
    bucket_name = os.getenv('MINIO_BUCKET_NAME', 'readflow')
    
    # Create bucket if it doesn't exist
    try:
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            print(f"✓ Created bucket: {bucket_name}")
        else:
            print(f"✓ Bucket already exists: {bucket_name}")
    except S3Error as e:
        print(f"✗ Error creating bucket: {e}")
        return False
    
    # Create folder structure (by uploading empty .gitkeep files)
    folders = [
        'bronze/goodreads_raw/books/',
        'bronze/goodreads_raw/authors/',
        'bronze/goodreads_raw/reviews/',
        'bronze/goodreads_raw/genres/',
        'silver/goodreads_clean/books/',
        'silver/goodreads_clean/authors/',
        'silver/goodreads_clean/reviews/',
        'silver/goodreads_clean/genres/',
        'gold/goodreads_analytics/fact_book_ratings/',
        'gold/goodreads_analytics/fact_reviews/',
        'gold/goodreads_analytics/dim_book/',
        'gold/goodreads_analytics/dim_author/',
        'gold/goodreads_analytics/dim_genre/',
        'gold/goodreads_analytics/dim_time/',
    ]
    
    for folder in folders:
        try:
            # Create empty file to represent folder
            client.put_object(
                bucket_name,
                f"{folder}.gitkeep",
                io.BytesIO(b""),
                0
            )
            print(f"✓ Created folder: {folder}")
        except S3Error as e:
            print(f"⚠ Warning for {folder}: {e}")
    
    print("\n✓ MinIO initialization complete!")
    return True

if __name__ == "__main__":
    import io
    init_minio()
EOF

chmod +x scripts/init_minio_buckets.py
print_success "MinIO initialization script created"

echo ""

# Create Dockerfile for Airflow
echo "7. Creating Docker configurations..."

mkdir -p airflow
cat > airflow/Dockerfile << 'EOF'
FROM apache/airflow:2.8.1-python3.9

USER root

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Install Python packages
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install additional packages
RUN pip install --no-cache-dir \
    apache-airflow-providers-amazon==8.16.0 \
    minio==7.2.3 \
    pyspark==3.5.0
EOF

print_success "Created Airflow Dockerfile"

# Create Dockerfile for Streamlit
mkdir -p analytics
cat > analytics/Dockerfile << 'EOF'
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Run Streamlit
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
EOF

print_success "Created Streamlit Dockerfile"

echo ""

# Create test data generator
echo "8. Creating test data generator..."

mkdir -p scripts
cat > scripts/generate_test_data.py << 'EOF'
"""Generate test data for development"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

def generate_test_data():
    """Generate sample GoodReads-like data"""
    
    # Sample data
    genres = ["Fiction", "Non-fiction", "Mystery", "Romance", "Sci-Fi", "Fantasy"]
    authors_data = [
        {"id": "1", "name": "Jane Austen"},
        {"id": "2", "name": "George Orwell"},
        {"id": "3", "name": "J.K. Rowling"},
        {"id": "4", "name": "Stephen King"},
        {"id": "5", "name": "Agatha Christie"}
    ]
    
    # Generate books
    books = []
    for i in range(100):
        book = {
            "id": str(i + 1),
            "title": f"Test Book {i + 1}",
            "isbn": f"978{random.randint(1000000000, 9999999999)}",
            "isbn13": f"978{random.randint(1000000000, 9999999999)}",
            "authors": [random.choice(authors_data)],
            "average_rating": round(random.uniform(3.0, 5.0), 2),
            "ratings_count": random.randint(100, 100000),
            "publication_year": random.randint(1950, 2023),
            "description": f"This is a test description for book {i + 1}",
            "language_code": random.choice(["eng", "spa", "fra"]),
            "ingestion_timestamp": datetime.utcnow().isoformat()
        }
        books.append(book)
    
    # Generate reviews
    reviews = []
    for i in range(500):
        review = {
            "id": str(i + 1),
            "book_id": str(random.randint(1, 100)),
            "user_id": str(random.randint(1, 1000)),
            "rating": random.randint(1, 5),
            "body": f"This is a test review #{i + 1}",
            "created_at": (datetime.utcnow() - timedelta(days=random.randint(0, 365))).isoformat(),
            "likes_count": random.randint(0, 100),
            "ingestion_timestamp": datetime.utcnow().isoformat()
        }
        reviews.append(review)
    
    # Save to files
    output_dir = Path("data/landing/test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / "books_test.json", "w") as f:
        json.dump({"data": books}, f, indent=2)
    
    with open(output_dir / "authors_test.json", "w") as f:
        json.dump({"data": authors_data}, f, indent=2)
    
    with open(output_dir / "reviews_test.json", "w") as f:
        json.dump({"data": reviews}, f, indent=2)
    
    with open(output_dir / "genres_test.json", "w") as f:
        json.dump({"data": [{"id": str(i), "name": g} for i, g in enumerate(genres, 1)]}, f, indent=2)
    
    print("✓ Generated test data in data/landing/test/")

if __name__ == "__main__":
    generate_test_data()
EOF

chmod +x scripts/generate_test_data.py
print_success "Created test data generator"

echo ""

# Create README for quick start
echo "9. Creating documentation..."

cat > QUICKSTART.md << 'EOF'
# ReadFlow Quick Start Guide

## 1. Initial Setup

```bash
# Run setup script
./setup.sh

# Edit .env file with your GoodReads API key
nano .env
```

## 2. Start Services

```bash
# Start all Docker services
docker-compose up -d

# Wait for services to be healthy (may take 2-3 minutes)
docker-compose ps
```

## 3. Initialize Data Infrastructure

```bash
# Activate virtual environment
source venv/bin/activate

# Initialize MinIO buckets
python scripts/init_minio_buckets.py

# Generate test data (optional)
python scripts/generate_test_data.py
```

## 4. Access Services

- **Airflow UI**: http://localhost:8080 (admin/admin)
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)
- **Streamlit App**: http://localhost:8501
- **Spark UI**: http://localhost:8081

## 5. Run the Pipeline

### Via Airflow UI:
1. Go to http://localhost:8080
2. Enable the `goodreads_ingestion_pipeline` DAG
3. Trigger the DAG manually

### Via Command Line:
```bash
docker-compose exec airflow-webserver airflow dags trigger goodreads_ingestion_pipeline
```

## 6. Monitor Progress

- Check Airflow UI for task status
- View logs in `airflow/logs/`
- Check data in MinIO Console

## 7. View Analytics

Open Streamlit app at http://localhost:8501

## Troubleshooting

### Services won't start:
```bash
docker-compose down -v
docker-compose up -d
```

### Airflow DAG not appearing:
```bash
docker-compose exec airflow-webserver airflow dags list
```

### Check logs:
```bash
docker-compose logs -f [service-name]
```
EOF

print_success "Created QUICKSTART.md"

echo ""

# Final message
echo "========================================="
print_success "Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file and add your GoodReads API key"
echo "2. Run: docker-compose up -d"
echo "3. Run: python scripts/init_minio_buckets.py"
echo "4. Access Airflow UI: http://localhost:8080"
echo ""
echo "See QUICKSTART.md for detailed instructions"
echo ""
