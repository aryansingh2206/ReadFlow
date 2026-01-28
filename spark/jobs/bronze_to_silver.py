"""
Bronze to Silver Spark ETL Job
Cleans, deduplicates, and normalizes raw JSON data from Bronze layer
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *
from pyspark.sql.window import Window
import logging
from datetime import datetime
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BronzeToSilverETL:
    """
    ETL job to transform Bronze (raw) data to Silver (cleaned) data
    
    Transformations:
    - Flatten nested JSON structures
    - Deduplicate records
    - Standardize timestamps
    - Clean text fields
    - Handle nulls and defaults
    - Add processing metadata
    """
    
    def __init__(self, spark: SparkSession):
        """
        Initialize ETL job
        
        Args:
            spark: SparkSession instance
        """
        self.spark = spark
        self.bronze_path = os.getenv('BRONZE_PATH', 's3a://readflow/bronze/goodreads_raw')
        self.silver_path = os.getenv('SILVER_PATH', 's3a://readflow/silver/goodreads_clean')
        
        logger.info(f"Initialized Bronze to Silver ETL")
        logger.info(f"Bronze path: {self.bronze_path}")
        logger.info(f"Silver path: {self.silver_path}")
    
    def run(self, ingestion_date: str):
        """
        Run the complete ETL pipeline
        
        Args:
            ingestion_date: Date to process (YYYY-MM-DD format)
        """
        logger.info(f"Starting Bronze to Silver ETL for {ingestion_date}")
        
        try:
            # Process each data type
            self.process_books(ingestion_date)
            self.process_authors(ingestion_date)
            self.process_reviews(ingestion_date)
            self.process_genres(ingestion_date)
            
            logger.info(f"✓ Successfully completed Bronze to Silver ETL for {ingestion_date}")
            
        except Exception as e:
            logger.error(f"✗ Bronze to Silver ETL failed: {str(e)}")
            raise
    
    def process_books(self, ingestion_date: str):
        """Process books data from Bronze to Silver"""
        logger.info("Processing books...")
        
        # Read Bronze data
        bronze_df = self.spark.read.json(
            f"{self.bronze_path}/ingestion_date={ingestion_date}/books/*.json"
        )
        
        # Extract data array
        books_df = bronze_df.select(F.explode("data").alias("book"))
        
        # Flatten and clean
        clean_df = books_df.select(
            F.col("book.id").cast("string").alias("book_id"),
            F.trim(F.col("book.title")).alias("title"),
            F.trim(F.col("book.isbn")).alias("isbn"),
            F.trim(F.col("book.isbn13")).alias("isbn13"),
            
            # Author handling - flatten array
            F.expr("transform(book.authors, x -> x.name)").alias("author_names"),
            F.expr("transform(book.authors, x -> x.id)").alias("author_ids"),
            
            # Ratings and counts
            F.col("book.average_rating").cast("double").alias("average_rating"),
            F.col("book.ratings_count").cast("long").alias("ratings_count"),
            F.col("book.text_reviews_count").cast("long").alias("text_reviews_count"),
            
            # Publication info
            F.col("book.publication_year").cast("int").alias("publication_year"),
            F.col("book.publication_month").cast("int").alias("publication_month"),
            F.col("book.publication_day").cast("int").alias("publication_day"),
            F.trim(F.col("book.publisher")).alias("publisher"),
            
            # Description and metadata
            F.regexp_replace(
                F.col("book.description"),
                "[\\r\\n\\t]+",
                " "
            ).alias("description"),
            
            F.col("book.image_url").alias("image_url"),
            F.col("book.num_pages").cast("int").alias("num_pages"),
            F.col("book.language_code").alias("language_code"),
            
            # Metadata
            F.to_timestamp(F.col("book.ingestion_timestamp")).alias("ingestion_timestamp"),
            F.lit(ingestion_date).alias("ingestion_date"),
            F.current_timestamp().alias("processing_timestamp")
        )
        
        # Data quality transformations
        quality_df = clean_df \
            .withColumn(
                "average_rating",
                F.when(
                    (F.col("average_rating") < 1) | (F.col("average_rating") > 5),
                    None
                ).otherwise(F.col("average_rating"))
            ) \
            .withColumn(
                "ratings_count",
                F.when(F.col("ratings_count") < 0, 0).otherwise(F.col("ratings_count"))
            ) \
            .withColumn(
                "publication_year",
                F.when(
                    (F.col("publication_year") < 1000) | (F.col("publication_year") > 2100),
                    None
                ).otherwise(F.col("publication_year"))
            ) \
            .withColumn(
                "is_valid_isbn",
                (F.length(F.col("isbn")) == 10) | (F.length(F.col("isbn13")) == 13)
            )
        
        # Deduplicate - keep latest by ingestion_timestamp
        window_spec = Window.partitionBy("book_id").orderBy(F.desc("ingestion_timestamp"))
        
        dedup_df = quality_df \
            .withColumn("row_num", F.row_number().over(window_spec)) \
            .filter(F.col("row_num") == 1) \
            .drop("row_num")
        
        # Write to Silver layer (partitioned by ingestion_date and language)
        dedup_df \
            .repartition("ingestion_date", "language_code") \
            .write \
            .mode("overwrite") \
            .partitionBy("ingestion_date", "language_code") \
            .parquet(f"{self.silver_path}/books")
        
        record_count = dedup_df.count()
        logger.info(f"✓ Processed {record_count} unique books")
    
    def process_authors(self, ingestion_date: str):
        """Process authors data from Bronze to Silver"""
        logger.info("Processing authors...")
        
        # Read Bronze data
        bronze_df = self.spark.read.json(
            f"{self.bronze_path}/ingestion_date={ingestion_date}/authors/*.json"
        )
        
        # Extract and clean
        authors_df = bronze_df.select(F.explode("data").alias("author"))
        
        clean_df = authors_df.select(
            F.col("author.id").cast("string").alias("author_id"),
            F.trim(F.col("author.name")).alias("name"),
            
            # Clean about text
            F.regexp_replace(
                F.col("author.about"),
                "[\\r\\n\\t]+",
                " "
            ).alias("about"),
            
            # Parse birth date
            F.to_date(F.col("author.born_at"), "yyyy-MM-dd").alias("born_at"),
            F.trim(F.col("author.hometown")).alias("hometown"),
            
            F.col("author.image_url").alias("image_url"),
            F.col("author.works_count").cast("int").alias("works_count"),
            F.col("author.average_rating").cast("double").alias("average_rating"),
            F.col("author.ratings_count").cast("long").alias("ratings_count"),
            
            # Metadata
            F.to_timestamp(F.col("author.ingestion_timestamp")).alias("ingestion_timestamp"),
            F.lit(ingestion_date).alias("ingestion_date"),
            F.current_timestamp().alias("processing_timestamp")
        )
        
        # Deduplicate
        window_spec = Window.partitionBy("author_id").orderBy(F.desc("ingestion_timestamp"))
        
        dedup_df = clean_df \
            .withColumn("row_num", F.row_number().over(window_spec)) \
            .filter(F.col("row_num") == 1) \
            .drop("row_num")
        
        # Write to Silver
        dedup_df \
            .repartition("ingestion_date") \
            .write \
            .mode("overwrite") \
            .partitionBy("ingestion_date") \
            .parquet(f"{self.silver_path}/authors")
        
        record_count = dedup_df.count()
        logger.info(f"✓ Processed {record_count} unique authors")
    
    def process_reviews(self, ingestion_date: str):
        """Process reviews data from Bronze to Silver"""
        logger.info("Processing reviews...")
        
        # Read Bronze data
        bronze_df = self.spark.read.json(
            f"{self.bronze_path}/ingestion_date={ingestion_date}/reviews/*.json"
        )
        
        # Extract and clean
        reviews_df = bronze_df.select(F.explode("data").alias("review"))
        
        clean_df = reviews_df.select(
            F.col("review.id").cast("string").alias("review_id"),
            F.col("review.book_id").cast("string").alias("book_id"),
            F.col("review.user_id").cast("string").alias("user_id"),
            
            # Rating must be 1-5
            F.when(
                (F.col("review.rating") >= 1) & (F.col("review.rating") <= 5),
                F.col("review.rating").cast("int")
            ).otherwise(None).alias("rating"),
            
            # Clean review text
            F.regexp_replace(
                F.col("review.body"),
                "[\\r\\n\\t]+",
                " "
            ).alias("review_text"),
            
            # Calculate text length
            F.length(F.col("review.body")).alias("review_length"),
            
            # Parse timestamps
            F.to_timestamp(F.col("review.created_at")).alias("created_at"),
            F.to_timestamp(F.col("review.updated_at")).alias("updated_at"),
            
            F.col("review.likes_count").cast("int").alias("likes_count"),
            
            # Metadata
            F.to_timestamp(F.col("review.ingestion_timestamp")).alias("ingestion_timestamp"),
            F.lit(ingestion_date).alias("ingestion_date"),
            F.current_timestamp().alias("processing_timestamp")
        )
        
        # Add derived fields
        enriched_df = clean_df \
            .withColumn(
                "has_text",
                F.col("review_length") > 0
            ) \
            .withColumn(
                "review_category",
                F.when(F.col("review_length") == 0, "rating_only")
                 .when(F.col("review_length") < 100, "short")
                 .when(F.col("review_length") < 500, "medium")
                 .otherwise("long")
            )
        
        # Deduplicate
        window_spec = Window.partitionBy("review_id").orderBy(F.desc("ingestion_timestamp"))
        
        dedup_df = enriched_df \
            .withColumn("row_num", F.row_number().over(window_spec)) \
            .filter(F.col("row_num") == 1) \
            .drop("row_num")
        
        # Write to Silver (partitioned by ingestion_date)
        dedup_df \
            .repartition("ingestion_date") \
            .write \
            .mode("overwrite") \
            .partitionBy("ingestion_date") \
            .parquet(f"{self.silver_path}/reviews")
        
        record_count = dedup_df.count()
        logger.info(f"✓ Processed {record_count} unique reviews")
    
    def process_genres(self, ingestion_date: str):
        """Process genres data from Bronze to Silver"""
        logger.info("Processing genres...")
        
        # Read Bronze data
        bronze_df = self.spark.read.json(
            f"{self.bronze_path}/ingestion_date={ingestion_date}/genres/*.json"
        )
        
        # Extract and clean
        genres_df = bronze_df.select(F.explode("data").alias("genre"))
        
        clean_df = genres_df.select(
            F.col("genre.id").cast("string").alias("genre_id"),
            F.trim(F.col("genre.name")).alias("name"),
            
            # Metadata
            F.lit(ingestion_date).alias("ingestion_date"),
            F.current_timestamp().alias("processing_timestamp")
        )
        
        # Deduplicate
        dedup_df = clean_df.dropDuplicates(["genre_id"])
        
        # Write to Silver
        dedup_df \
            .write \
            .mode("overwrite") \
            .partitionBy("ingestion_date") \
            .parquet(f"{self.silver_path}/genres")
        
        record_count = dedup_df.count()
        logger.info(f"✓ Processed {record_count} unique genres")


def main():
    """Main entry point for Spark job"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: bronze_to_silver.py <ingestion_date>")
        sys.exit(1)
    
    ingestion_date = sys.argv[1]
    
    # Create Spark session
    spark = SparkSession.builder \
        .appName("ReadFlow - Bronze to Silver ETL") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .config("spark.sql.files.maxPartitionBytes", "128MB") \
        .config("spark.hadoop.fs.s3a.endpoint", os.getenv('MINIO_ENDPOINT', 'minio:9000')) \
        .config("spark.hadoop.fs.s3a.access.key", os.getenv('MINIO_ACCESS_KEY', 'minioadmin')) \
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv('MINIO_SECRET_KEY', 'minioadmin')) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .getOrCreate()
    
    try:
        # Run ETL
        etl = BronzeToSilverETL(spark)
        etl.run(ingestion_date)
        
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
