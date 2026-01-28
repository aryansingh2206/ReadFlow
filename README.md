# 📖 ReadFlow - End-to-End Book Analytics Platform

A production-style data engineering project built with 100% free, open-source tools. Process real-time book data through a complete data lake and warehouse architecture.

## 🎯 Project Overview

**ReadFlow** is an end-to-end data pipeline that:
- Ingests book data from GoodReads API in real-time
- Stores raw and processed data in a data lake (MinIO)
- Transforms data using Apache Spark (Bronze → Silver → Gold)
- Loads data into a SQL warehouse (DuckDB)
- Provides interactive analytics via Streamlit

## 🏗️ Architecture

```
GoodReads API (real-time)
        ↓
Local Landing (JSON)
        ↓
Apache Airflow (10-min schedule)
        ↓
MinIO Data Lake (Parquet)
        ↓
Apache Spark ETL (Bronze → Silver → Gold)
        ↓
DuckDB Warehouse (Star Schema)
        ↓
Streamlit Analytics App
```

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Data Source** | GoodReads API | Book, author, review data |
| **Ingestion** | Python | API client with retry logic |
| **Orchestration** | Apache Airflow | Workflow scheduling |
| **Object Storage** | MinIO | S3-compatible data lake |
| **File Format** | Parquet | Columnar storage |
| **Processing** | Apache Spark | Distributed ETL |
| **Data Quality** | Python + Great Expectations | Validation & checks |
| **Warehouse** | DuckDB | SQL analytics engine |
| **Analytics UI** | Streamlit | Interactive dashboards |
| **Infrastructure** | Docker Compose | Container orchestration |

## 📁 Project Structure

```
readflow/
├── airflow/
│   ├── dags/
│   │   ├── goodreads_ingestion_dag.py
│   │   └── spark_etl_dag.py
│   ├── plugins/
│   └── config/
├── spark/
│   ├── jobs/
│   │   ├── bronze_to_silver.py
│   │   └── silver_to_gold.py
│   ├── transformations/
│   └── utils/
├── ingestion/
│   ├── api_client.py
│   ├── schema_validator.py
│   └── landing_zone.py
├── data_quality/
│   ├── expectations/
│   └── validation.py
├── warehouse/
│   ├── models/
│   │   ├── fact_book_ratings.sql
│   │   └── dim_book.sql
│   └── queries/
├── analytics/
│   ├── streamlit_app.py
│   ├── pages/
│   └── components/
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.9+
- 8GB RAM minimum
- GoodReads API Key (free signup)

### 1. Clone and Setup

```bash
git clone <your-repo>
cd readflow

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your GoodReads API key
```

### 3. Start Infrastructure

```bash
# Start MinIO, Airflow, Spark
docker-compose up -d

# Wait for services to be healthy
docker-compose ps
```

### 4. Access Services

- **Airflow UI**: http://localhost:8080 (admin/admin)
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)
- **Streamlit App**: http://localhost:8501
- **Spark UI**: http://localhost:4040 (when jobs running)

### 5. Initialize Data Lake

```bash
python scripts/init_minio_buckets.py
```

### 6. Run the Pipeline

Enable the DAG in Airflow UI or trigger manually:

```bash
airflow dags trigger goodreads_ingestion_pipeline
```

## 📊 Data Pipeline Details

### Layer 1: Bronze (Raw Data)

**Purpose**: Store raw API responses without transformation

**Location**: `s3://readflow/bronze/goodreads_raw/`

**Format**: JSON (partitioned by ingestion_date)

**Schema**: Exact API response structure

### Layer 2: Silver (Cleaned Data)

**Purpose**: Cleaned, deduplicated, and normalized data

**Location**: `s3://readflow/silver/goodreads_clean/`

**Format**: Parquet (partitioned by ingestion_date, genre)

**Transformations**:
- Flatten nested JSON structures
- Deduplicate records by book_id
- Standardize timestamps (UTC)
- Clean text fields (remove special chars)
- Handle nulls and default values

### Layer 3: Gold (Analytics Models)

**Purpose**: Business-ready star schema for analytics

**Location**: `s3://readflow/gold/goodreads_analytics/`

**Format**: Parquet (partitioned by date, genre)

**Star Schema**:

**Fact Tables**:
- `fact_book_ratings` - Rating events with FK to dimensions
- `fact_reviews` - Review details with metadata

**Dimension Tables**:
- `dim_book` - Book master data
- `dim_author` - Author information
- `dim_genre` - Genre hierarchy
- `dim_time` - Date dimension

## 🔄 Airflow DAG Design

### Main DAG: `goodreads_ingestion_pipeline`

```
fetch_api_data >> validate_schema >> write_to_bronze >> trigger_spark_etl
                                            ↓
                                    data_quality_check
```

**Schedule**: Every 10 minutes

**Features**:
- Retry logic with exponential backoff
- API rate limit handling
- Incremental data fetch
- Idempotent operations

### ETL DAG: `spark_transformation_pipeline`

```
bronze_to_silver >> silver_to_gold >> load_to_warehouse >> refresh_analytics
```

## ⚡ Spark Job Optimization

### Performance Features

1. **Partition Pruning**: Query only relevant partitions
2. **Columnar Scans**: Read only needed columns
3. **Broadcast Joins**: For small dimension tables
4. **Incremental Processing**: Process only new data
5. **Caching**: Cache frequently used DataFrames

### Example Spark Configuration

```python
spark = SparkSession.builder \
    .appName("ReadFlow ETL") \
    .config("spark.sql.adaptive.enabled", "true") \
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
    .config("spark.sql.files.maxPartitionBytes", "128MB") \
    .getOrCreate()
```

## 🧪 Data Quality Framework

### Validation Checks

**Schema Validation**:
- Column presence
- Data type verification
- Required field checks

**Business Rules**:
- Rating range: 1-5
- Non-null book_id
- Valid ISBN format
- Future date prevention

**Statistical Checks**:
- Row count anomalies
- Null percentage thresholds
- Duplicate detection

### Great Expectations Integration

```python
# Example expectation suite
{
    "expect_column_values_to_be_between": {
        "column": "rating",
        "min_value": 1,
        "max_value": 5
    },
    "expect_column_values_to_not_be_null": {
        "column": "book_id"
    }
}
```

## 📈 Analytics Application

### Streamlit Features

1. **Genre Explorer**
   - Top books by genre
   - Rating distributions
   - Popularity trends

2. **Author Dashboard**
   - Publication timeline
   - Average ratings
   - Review counts

3. **Review Analytics**
   - Sentiment proxy (rating-based)
   - Review length analysis
   - Temporal patterns

4. **Search & Discovery**
   - Semantic book search
   - Similar books recommendation
   - Author lookup

5. **Performance Metrics**
   - Pipeline health dashboard
   - Data freshness indicators
   - Quality score trends

## 🎯 Key Concepts Demonstrated

### Data Engineering Principles

✅ **Medallion Architecture**: Bronze → Silver → Gold layers
✅ **Idempotency**: Safe to re-run pipelines
✅ **Incremental Processing**: Process only new data
✅ **Schema Evolution**: Handle API changes gracefully
✅ **Data Quality**: First-class validation
✅ **Partition Strategy**: Optimize for query patterns
✅ **Separation of Concerns**: Clear layer boundaries

### Production Best Practices

✅ **Retry Logic**: Handle transient failures
✅ **Monitoring**: Log all operations
✅ **Alerting**: Notify on failures
✅ **Testing**: Unit and integration tests
✅ **Documentation**: Clear README and comments
✅ **Configuration Management**: Environment variables
✅ **CI/CD Ready**: GitHub Actions templates included

## 🧪 Testing

```bash
# Run unit tests
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Validate Airflow DAGs
python -m pytest tests/dags/

# Check data quality
python scripts/run_quality_checks.py
```

## 📦 Deployment Options

### Option 1: Local Development (Current)
- Docker Compose on laptop
- Perfect for development and demos

### Option 2: Cloud Migration (Future)
- MinIO → AWS S3
- Local Spark → EMR/Databricks
- DuckDB → Redshift/BigQuery
- **Same code works!** Just change configs

### Option 3: Kubernetes (Advanced)
- Helm charts for all services
- Auto-scaling Spark executors
- Production-grade monitoring

## 🎤 Interview Talking Points

### When asked about this project:

**"What does it do?"**
> "ReadFlow is an end-to-end data platform that ingests book data from GoodReads API, transforms it through a medallion architecture data lake, and serves analytics through a SQL warehouse and interactive dashboard."

**"What's impressive about it?"**
> "It demonstrates production patterns: orchestrated workflows, data quality checks, incremental processing, star schema modeling, and performance optimization - all using industry-standard tools like Airflow, Spark, and Parquet."

**"What challenges did you solve?"**
> "API rate limiting with retry logic, schema evolution handling, incremental vs full loads, partition strategy for query performance, and building idempotent pipelines that are safe to re-run."

**"How does it scale?"**
> "The architecture is cloud-portable. MinIO uses the S3 API, so migrating to AWS S3 is a config change. Spark jobs use partitioning and columnar formats for efficiency. The medallion architecture separates hot and cold data."

## 📚 Learning Resources

- [Apache Airflow Documentation](https://airflow.apache.org/docs/)
- [Apache Spark Best Practices](https://spark.apache.org/docs/latest/)
- [Data Lake Design Patterns](https://www.databricks.com/glossary/data-lakehouse)
- [Medallion Architecture](https://www.databricks.com/glossary/medallion-architecture)
- [DuckDB Analytics](https://duckdb.org/docs/)

## 🤝 Contributing

This is a portfolio project, but feedback welcome! Open an issue or PR.

## 📄 License

MIT License - Feel free to use for your portfolio

## 🔥 Resume Description

**ReadFlow — End-to-End Book Analytics Platform**

Built an end-to-end data pipeline processing real-time GoodReads API data for book and review analytics. Designed a data lake and warehouse architecture using S3-compatible object storage and Parquet datasets. Orchestrated Spark ETL jobs with Apache Airflow, scheduled at 10-minute intervals. Implemented data cleaning, deduplication, and star-schema modeling for analytics workloads. Enabled SQL-based analytics using DuckDB and delivered insights via an interactive Streamlit application. Applied data quality checks and performance optimizations to ensure reliable and scalable analytics.

---

**Built with ❤️ using 100% free, open-source tools**

Total cost: **₹0** | Production vibes: **100%**
