"""
ReadFlow Data Ingestion Pipeline
Orchestrates GoodReads API data fetch and loading to Bronze layer
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.utils.dates import days_ago
import os
import json
import logging

# Default arguments for the DAG
default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email': [os.getenv('ALERT_EMAIL', 'alert@example.com')],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
}

# DAG definition
dag = DAG(
    'goodreads_ingestion_pipeline',
    default_args=default_args,
    description='Fetch data from GoodReads API and load to Bronze layer',
    schedule_interval='*/10 * * * *',  # Every 10 minutes
    catchup=False,
    tags=['ingestion', 'api', 'bronze'],
    max_active_runs=1,
)


def fetch_goodreads_data(**context):
    """
    Fetch data from GoodReads API with rate limiting and retry logic
    """
    from ingestion.api_client import GoodReadsClient
    
    logger = logging.getLogger(__name__)
    execution_date = context['execution_date']
    
    logger.info(f"Starting data fetch for execution_date: {execution_date}")
    
    # Initialize API client
    client = GoodReadsClient(
        api_key=os.getenv('GOODREADS_API_KEY'),
        rate_limit=10,  # requests per second
        max_retries=3
    )
    
    # Fetch data for different endpoints
    data = {
        'books': [],
        'authors': [],
        'reviews': [],
        'genres': []
    }
    
    try:
        # Fetch recent books (example - adjust based on actual API)
        logger.info("Fetching books data...")
        data['books'] = client.get_recent_books(limit=100)
        
        # Fetch authors
        logger.info("Fetching authors data...")
        data['authors'] = client.get_popular_authors(limit=50)
        
        # Fetch recent reviews
        logger.info("Fetching reviews data...")
        data['reviews'] = client.get_recent_reviews(limit=500)
        
        # Fetch genres
        logger.info("Fetching genres data...")
        data['genres'] = client.get_all_genres()
        
        logger.info(f"Successfully fetched: {len(data['books'])} books, "
                   f"{len(data['authors'])} authors, "
                   f"{len(data['reviews'])} reviews, "
                   f"{len(data['genres'])} genres")
        
        # Push data to XCom for next task
        context['ti'].xcom_push(key='raw_data', value=data)
        context['ti'].xcom_push(key='record_count', value={
            'books': len(data['books']),
            'authors': len(data['authors']),
            'reviews': len(data['reviews']),
            'genres': len(data['genres'])
        })
        
        return data
        
    except Exception as e:
        logger.error(f"Failed to fetch data: {str(e)}")
        raise


def validate_api_data(**context):
    """
    Validate schema and data quality of API response
    """
    from ingestion.schema_validator import SchemaValidator
    
    logger = logging.getLogger(__name__)
    
    # Get data from previous task
    ti = context['ti']
    data = ti.xcom_pull(task_ids='fetch_api_data', key='raw_data')
    
    logger.info("Starting schema validation...")
    
    validator = SchemaValidator()
    
    # Validate each data type
    validation_results = {}
    
    for data_type, records in data.items():
        try:
            is_valid, errors = validator.validate(data_type, records)
            validation_results[data_type] = {
                'valid': is_valid,
                'errors': errors,
                'record_count': len(records)
            }
            
            if not is_valid:
                logger.warning(f"Validation issues for {data_type}: {errors}")
            else:
                logger.info(f"Successfully validated {data_type}")
                
        except Exception as e:
            logger.error(f"Validation failed for {data_type}: {str(e)}")
            validation_results[data_type] = {
                'valid': False,
                'errors': [str(e)],
                'record_count': len(records)
            }
    
    # Push validation results
    context['ti'].xcom_push(key='validation_results', value=validation_results)
    
    # Fail if critical validations failed
    if not all(r['valid'] for r in validation_results.values()):
        failed = [k for k, v in validation_results.items() if not v['valid']]
        raise ValueError(f"Validation failed for: {', '.join(failed)}")
    
    return validation_results


def write_to_landing_zone(**context):
    """
    Write raw JSON data to local landing zone
    """
    import json
    from pathlib import Path
    
    logger = logging.getLogger(__name__)
    ti = context['ti']
    execution_date = context['execution_date']
    
    # Get data
    data = ti.xcom_pull(task_ids='fetch_api_data', key='raw_data')
    
    # Create landing zone path
    landing_path = Path(f"/opt/data/landing/{execution_date.strftime('%Y-%m-%d')}")
    landing_path.mkdir(parents=True, exist_ok=True)
    
    # Write each data type to separate file
    file_paths = {}
    
    for data_type, records in data.items():
        file_path = landing_path / f"{data_type}_{execution_date.strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(file_path, 'w') as f:
            json.dump({
                'metadata': {
                    'ingestion_timestamp': execution_date.isoformat(),
                    'record_count': len(records),
                    'data_type': data_type
                },
                'data': records
            }, f, indent=2)
        
        file_paths[data_type] = str(file_path)
        logger.info(f"Written {len(records)} {data_type} records to {file_path}")
    
    # Push file paths for next task
    context['ti'].xcom_push(key='landing_files', value=file_paths)
    
    return file_paths


def upload_to_bronze_layer(**context):
    """
    Upload JSON files from landing zone to MinIO Bronze layer
    """
    from minio import Minio
    from minio.error import S3Error
    
    logger = logging.getLogger(__name__)
    ti = context['ti']
    execution_date = context['execution_date']
    
    # Get file paths from previous task
    file_paths = ti.xcom_pull(task_ids='write_to_landing_zone', key='landing_files')
    
    # Initialize MinIO client
    minio_client = Minio(
        os.getenv('MINIO_ENDPOINT', 'minio:9000'),
        access_key=os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
        secret_key=os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
        secure=False
    )
    
    bucket_name = os.getenv('MINIO_BUCKET_NAME', 'readflow')
    
    # Ensure bucket exists
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)
        logger.info(f"Created bucket: {bucket_name}")
    
    uploaded_objects = []
    
    for data_type, file_path in file_paths.items():
        try:
            # S3 object path in Bronze layer
            object_name = (
                f"bronze/goodreads_raw/"
                f"ingestion_date={execution_date.strftime('%Y-%m-%d')}/"
                f"{data_type}/"
                f"{execution_date.strftime('%Y%m%d_%H%M%S')}.json"
            )
            
            # Upload file
            minio_client.fput_object(
                bucket_name,
                object_name,
                file_path,
                content_type='application/json'
            )
            
            uploaded_objects.append(object_name)
            logger.info(f"Uploaded {data_type} to s3://{bucket_name}/{object_name}")
            
        except S3Error as e:
            logger.error(f"Failed to upload {data_type}: {str(e)}")
            raise
    
    # Push uploaded object paths
    context['ti'].xcom_push(key='bronze_objects', value=uploaded_objects)
    
    return uploaded_objects


def check_data_quality(**context):
    """
    Run data quality checks on Bronze layer data
    """
    import json
    
    logger = logging.getLogger(__name__)
    ti = context['ti']
    
    # Get validation results and record counts
    validation_results = ti.xcom_pull(task_ids='validate_schema', key='validation_results')
    record_count = ti.xcom_pull(task_ids='fetch_api_data', key='record_count')
    
    logger.info("Running data quality checks...")
    
    quality_checks = {
        'schema_validation': all(v['valid'] for v in validation_results.values()),
        'record_count_check': all(count > 0 for count in record_count.values()),
        'no_empty_datasets': len([k for k, v in record_count.items() if v == 0]) == 0
    }
    
    # Log results
    for check, passed in quality_checks.items():
        status = "PASSED" if passed else "FAILED"
        logger.info(f"Quality Check - {check}: {status}")
    
    if not all(quality_checks.values()):
        failed_checks = [k for k, v in quality_checks.items() if not v]
        logger.warning(f"Some quality checks failed: {', '.join(failed_checks)}")
    
    # Push results
    context['ti'].xcom_push(key='quality_checks', value=quality_checks)
    
    return quality_checks


# Define tasks
fetch_task = PythonOperator(
    task_id='fetch_api_data',
    python_callable=fetch_goodreads_data,
    dag=dag,
)

validate_task = PythonOperator(
    task_id='validate_schema',
    python_callable=validate_api_data,
    dag=dag,
)

landing_task = PythonOperator(
    task_id='write_to_landing_zone',
    python_callable=write_to_landing_zone,
    dag=dag,
)

bronze_upload_task = PythonOperator(
    task_id='upload_to_bronze',
    python_callable=upload_to_bronze_layer,
    dag=dag,
)

quality_check_task = PythonOperator(
    task_id='data_quality_check',
    python_callable=check_data_quality,
    dag=dag,
)

trigger_etl_task = BashOperator(
    task_id='trigger_spark_etl',
    bash_command='echo "Triggering Spark ETL pipeline..."',
    dag=dag,
)

# Define task dependencies
fetch_task >> validate_task >> landing_task >> bronze_upload_task >> quality_check_task >> trigger_etl_task
