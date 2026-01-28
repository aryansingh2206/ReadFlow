"""
Schema Validator for GoodReads Data
Validates API responses against expected schemas
"""

import logging
from typing import Dict, List, Tuple, Any
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class SchemaValidator:
    """
    Validates data schemas and performs basic quality checks
    """
    
    # Define expected schemas for each data type
    SCHEMAS = {
        'books': {
            'required_fields': ['id', 'title', 'isbn', 'authors'],
            'optional_fields': ['description', 'publication_year', 'average_rating', 'ratings_count', 'image_url'],
            'field_types': {
                'id': (int, str),
                'title': str,
                'isbn': str,
                'average_rating': (int, float, type(None)),
                'ratings_count': (int, type(None)),
                'publication_year': (int, str, type(None))
            },
            'field_validators': {
                'average_rating': lambda x: x is None or (1 <= float(x) <= 5),
                'ratings_count': lambda x: x is None or int(x) >= 0,
                'isbn': lambda x: len(str(x)) in [10, 13] or x == ''
            }
        },
        'authors': {
            'required_fields': ['id', 'name'],
            'optional_fields': ['about', 'born_at', 'hometown', 'image_url', 'works_count'],
            'field_types': {
                'id': (int, str),
                'name': str,
                'works_count': (int, type(None))
            },
            'field_validators': {
                'works_count': lambda x: x is None or int(x) >= 0
            }
        },
        'reviews': {
            'required_fields': ['id', 'book_id', 'rating'],
            'optional_fields': ['user_id', 'review_text', 'created_at', 'likes_count'],
            'field_types': {
                'id': (int, str),
                'book_id': (int, str),
                'rating': (int, float),
                'likes_count': (int, type(None))
            },
            'field_validators': {
                'rating': lambda x: 1 <= float(x) <= 5,
                'likes_count': lambda x: x is None or int(x) >= 0
            }
        },
        'genres': {
            'required_fields': ['id', 'name'],
            'optional_fields': ['description'],
            'field_types': {
                'id': (int, str),
                'name': str
            },
            'field_validators': {}
        }
    }
    
    def validate(
        self,
        data_type: str,
        records: List[Dict]
    ) -> Tuple[bool, List[str]]:
        """
        Validate a list of records against expected schema
        
        Args:
            data_type: Type of data (books, authors, reviews, genres)
            records: List of record dictionaries
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        if data_type not in self.SCHEMAS:
            return False, [f"Unknown data type: {data_type}"]
        
        schema = self.SCHEMAS[data_type]
        errors = []
        
        logger.info(f"Validating {len(records)} {data_type} records")
        
        if not records:
            errors.append(f"No records found for {data_type}")
            return False, errors
        
        # Validate each record
        for idx, record in enumerate(records):
            record_errors = self._validate_record(record, schema, data_type, idx)
            errors.extend(record_errors)
        
        is_valid = len(errors) == 0
        
        if is_valid:
            logger.info(f"✓ All {len(records)} {data_type} records are valid")
        else:
            logger.warning(f"✗ Found {len(errors)} validation errors in {data_type}")
        
        return is_valid, errors
    
    def _validate_record(
        self,
        record: Dict,
        schema: Dict,
        data_type: str,
        record_idx: int
    ) -> List[str]:
        """
        Validate a single record
        
        Args:
            record: Record dictionary
            schema: Expected schema
            data_type: Type of data
            record_idx: Index of record in list
            
        Returns:
            List of error messages
        """
        errors = []
        record_id = f"{data_type}[{record_idx}]"
        
        # Check required fields
        for field in schema['required_fields']:
            if field not in record or record[field] is None:
                errors.append(f"{record_id}: Missing required field '{field}'")
        
        # Check field types
        for field, expected_types in schema['field_types'].items():
            if field in record and record[field] is not None:
                if not isinstance(record[field], expected_types):
                    errors.append(
                        f"{record_id}: Field '{field}' has wrong type. "
                        f"Expected {expected_types}, got {type(record[field])}"
                    )
        
        # Run custom validators
        for field, validator in schema['field_validators'].items():
            if field in record and record[field] is not None:
                try:
                    if not validator(record[field]):
                        errors.append(
                            f"{record_id}: Field '{field}' failed validation. "
                            f"Value: {record[field]}"
                        )
                except Exception as e:
                    errors.append(
                        f"{record_id}: Error validating field '{field}': {str(e)}"
                    )
        
        return errors
    
    def validate_isbn(self, isbn: str) -> bool:
        """
        Validate ISBN-10 or ISBN-13 format
        
        Args:
            isbn: ISBN string
            
        Returns:
            True if valid, False otherwise
        """
        if not isbn:
            return False
        
        # Remove hyphens and spaces
        isbn = re.sub(r'[\s-]', '', isbn)
        
        # Check ISBN-10
        if len(isbn) == 10:
            return self._validate_isbn10(isbn)
        
        # Check ISBN-13
        if len(isbn) == 13:
            return self._validate_isbn13(isbn)
        
        return False
    
    def _validate_isbn10(self, isbn: str) -> bool:
        """Validate ISBN-10 checksum"""
        if not isbn[:-1].isdigit():
            return False
        
        check_digit = isbn[-1]
        if check_digit.upper() != 'X' and not check_digit.isdigit():
            return False
        
        total = sum((10 - i) * int(digit) for i, digit in enumerate(isbn[:-1]))
        
        if check_digit.upper() == 'X':
            total += 10
        else:
            total += int(check_digit)
        
        return total % 11 == 0
    
    def _validate_isbn13(self, isbn: str) -> bool:
        """Validate ISBN-13 checksum"""
        if not isbn.isdigit():
            return False
        
        total = sum(
            int(digit) * (1 if i % 2 == 0 else 3)
            for i, digit in enumerate(isbn)
        )
        
        return total % 10 == 0
    
    def check_data_freshness(
        self,
        records: List[Dict],
        max_age_hours: int = 24
    ) -> Tuple[bool, str]:
        """
        Check if data is fresh (recently ingested)
        
        Args:
            records: List of records with ingestion_timestamp
            max_age_hours: Maximum age in hours
            
        Returns:
            Tuple of (is_fresh, message)
        """
        if not records:
            return False, "No records to check"
        
        now = datetime.utcnow()
        
        for record in records:
            if 'ingestion_timestamp' not in record:
                return False, "Records missing ingestion_timestamp"
            
            try:
                timestamp = datetime.fromisoformat(
                    record['ingestion_timestamp'].replace('Z', '+00:00')
                )
                age_hours = (now - timestamp).total_seconds() / 3600
                
                if age_hours > max_age_hours:
                    return False, f"Data is {age_hours:.1f} hours old (max: {max_age_hours})"
            
            except Exception as e:
                return False, f"Invalid timestamp format: {str(e)}"
        
        return True, f"Data is fresh (< {max_age_hours} hours old)"
    
    def check_duplicates(
        self,
        records: List[Dict],
        key_field: str = 'id'
    ) -> Tuple[int, List[Any]]:
        """
        Check for duplicate records
        
        Args:
            records: List of records
            key_field: Field to use for duplicate detection
            
        Returns:
            Tuple of (duplicate_count, list_of_duplicate_ids)
        """
        seen = set()
        duplicates = []
        
        for record in records:
            if key_field not in record:
                continue
            
            key_value = record[key_field]
            
            if key_value in seen:
                duplicates.append(key_value)
            else:
                seen.add(key_value)
        
        return len(duplicates), duplicates


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    validator = SchemaValidator()
    
    # Test data
    test_books = [
        {
            'id': '1',
            'title': 'The Great Gatsby',
            'isbn': '9780743273565',
            'authors': ['F. Scott Fitzgerald'],
            'average_rating': 3.9,
            'ratings_count': 1000000,
            'publication_year': 1925,
            'ingestion_timestamp': datetime.utcnow().isoformat()
        },
        {
            'id': '2',
            'title': '1984',
            'isbn': '9780451524935',
            'authors': ['George Orwell'],
            'average_rating': 4.2,
            'ratings_count': 2000000,
            'publication_year': 1949,
            'ingestion_timestamp': datetime.utcnow().isoformat()
        }
    ]
    
    # Validate
    is_valid, errors = validator.validate('books', test_books)
    
    if is_valid:
        print("✓ Validation passed!")
    else:
        print("✗ Validation failed:")
        for error in errors:
            print(f"  - {error}")
    
    # Check freshness
    is_fresh, msg = validator.check_data_freshness(test_books, max_age_hours=1)
    print(f"\nFreshness check: {msg}")
    
    # Check duplicates
    dup_count, dup_ids = validator.check_duplicates(test_books)
    print(f"Duplicate check: Found {dup_count} duplicates")
