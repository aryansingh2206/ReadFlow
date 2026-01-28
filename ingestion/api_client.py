"""
GoodReads API Client
Handles API requests with rate limiting, retries, and error handling
"""

import requests
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime
import backoff
from requests_ratelimiter import LimiterSession

logger = logging.getLogger(__name__)


class GoodReadsClient:
    """
    Client for interacting with GoodReads API
    
    Features:
    - Rate limiting to respect API limits
    - Exponential backoff retry logic
    - Comprehensive error handling
    - Pagination support
    - Incremental data fetching
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://www.goodreads.com/api",
        rate_limit: int = 10,  # requests per second
        max_retries: int = 3,
        timeout: int = 30
    ):
        """
        Initialize GoodReads API client
        
        Args:
            api_key: GoodReads API key
            base_url: Base URL for API endpoints
            rate_limit: Maximum requests per second
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = base_url
        self.max_retries = max_retries
        self.timeout = timeout
        
        # Initialize rate-limited session
        self.session = LimiterSession(per_second=rate_limit)
        self.session.headers.update({
            'User-Agent': 'ReadFlow/1.0',
            'Accept': 'application/json'
        })
        
        logger.info(f"Initialized GoodReads client with rate limit: {rate_limit} req/s")
    
    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.RequestException, requests.exceptions.Timeout),
        max_tries=3,
        max_time=300
    )
    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        method: str = 'GET'
    ) -> Dict:
        """
        Make HTTP request with retry logic
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            method: HTTP method
            
        Returns:
            JSON response as dictionary
            
        Raises:
            requests.exceptions.RequestException: On request failure
        """
        url = f"{self.base_url}/{endpoint}"
        
        # Add API key to params
        if params is None:
            params = {}
        params['key'] = self.api_key
        
        try:
            logger.debug(f"Making {method} request to {endpoint}")
            
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                timeout=self.timeout
            )
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                return self._make_request(endpoint, params, method)
            
            # Raise for HTTP errors
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout for {endpoint}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {endpoint}: {str(e)}")
            raise
    
    def get_recent_books(
        self,
        limit: int = 100,
        page: int = 1,
        updated_since: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Fetch recently added/updated books
        
        Args:
            limit: Number of books per page
            page: Page number
            updated_since: Only fetch books updated after this date
            
        Returns:
            List of book dictionaries
        """
        logger.info(f"Fetching recent books (limit={limit}, page={page})")
        
        params = {
            'per_page': limit,
            'page': page,
            'sort': 'updated_at',
            'order': 'desc'
        }
        
        if updated_since:
            params['updated_since'] = updated_since.isoformat()
        
        try:
            response = self._make_request('books.json', params)
            books = response.get('books', [])
            
            # Enrich with metadata
            enriched_books = []
            for book in books:
                enriched_book = {
                    **book,
                    'ingestion_timestamp': datetime.utcnow().isoformat(),
                    'source': 'goodreads_api'
                }
                enriched_books.append(enriched_book)
            
            logger.info(f"Successfully fetched {len(enriched_books)} books")
            return enriched_books
            
        except Exception as e:
            logger.error(f"Failed to fetch books: {str(e)}")
            raise
    
    def get_book_by_id(self, book_id: str) -> Dict:
        """
        Fetch detailed book information by ID
        
        Args:
            book_id: GoodReads book ID
            
        Returns:
            Book dictionary with full details
        """
        logger.debug(f"Fetching book details for ID: {book_id}")
        
        try:
            response = self._make_request(f'book/show/{book_id}.json')
            book = response.get('book', {})
            
            book['ingestion_timestamp'] = datetime.utcnow().isoformat()
            book['source'] = 'goodreads_api'
            
            return book
            
        except Exception as e:
            logger.error(f"Failed to fetch book {book_id}: {str(e)}")
            raise
    
    def get_popular_authors(
        self,
        limit: int = 50,
        page: int = 1
    ) -> List[Dict]:
        """
        Fetch popular authors
        
        Args:
            limit: Number of authors per page
            page: Page number
            
        Returns:
            List of author dictionaries
        """
        logger.info(f"Fetching popular authors (limit={limit}, page={page})")
        
        params = {
            'per_page': limit,
            'page': page,
            'sort': 'popularity'
        }
        
        try:
            response = self._make_request('authors.json', params)
            authors = response.get('authors', [])
            
            # Enrich with metadata
            enriched_authors = []
            for author in authors:
                enriched_author = {
                    **author,
                    'ingestion_timestamp': datetime.utcnow().isoformat(),
                    'source': 'goodreads_api'
                }
                enriched_authors.append(enriched_author)
            
            logger.info(f"Successfully fetched {len(enriched_authors)} authors")
            return enriched_authors
            
        except Exception as e:
            logger.error(f"Failed to fetch authors: {str(e)}")
            raise
    
    def get_recent_reviews(
        self,
        limit: int = 500,
        page: int = 1,
        book_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Fetch recent book reviews
        
        Args:
            limit: Number of reviews per page
            page: Page number
            book_id: Optional book ID to filter reviews
            
        Returns:
            List of review dictionaries
        """
        logger.info(f"Fetching reviews (limit={limit}, page={page}, book_id={book_id})")
        
        params = {
            'per_page': limit,
            'page': page,
            'sort': 'created_at',
            'order': 'desc'
        }
        
        if book_id:
            params['book_id'] = book_id
        
        try:
            response = self._make_request('reviews.json', params)
            reviews = response.get('reviews', [])
            
            # Enrich with metadata
            enriched_reviews = []
            for review in reviews:
                enriched_review = {
                    **review,
                    'ingestion_timestamp': datetime.utcnow().isoformat(),
                    'source': 'goodreads_api'
                }
                enriched_reviews.append(enriched_review)
            
            logger.info(f"Successfully fetched {len(enriched_reviews)} reviews")
            return enriched_reviews
            
        except Exception as e:
            logger.error(f"Failed to fetch reviews: {str(e)}")
            raise
    
    def get_all_genres(self) -> List[Dict]:
        """
        Fetch all available genres
        
        Returns:
            List of genre dictionaries
        """
        logger.info("Fetching all genres")
        
        try:
            response = self._make_request('genres.json')
            genres = response.get('genres', [])
            
            # Enrich with metadata
            enriched_genres = []
            for genre in genres:
                enriched_genre = {
                    **genre,
                    'ingestion_timestamp': datetime.utcnow().isoformat(),
                    'source': 'goodreads_api'
                }
                enriched_genres.append(enriched_genre)
            
            logger.info(f"Successfully fetched {len(enriched_genres)} genres")
            return enriched_genres
            
        except Exception as e:
            logger.error(f"Failed to fetch genres: {str(e)}")
            raise
    
    def search_books(
        self,
        query: str,
        limit: int = 20,
        page: int = 1
    ) -> List[Dict]:
        """
        Search for books by query string
        
        Args:
            query: Search query
            limit: Number of results per page
            page: Page number
            
        Returns:
            List of book dictionaries matching query
        """
        logger.info(f"Searching books: '{query}' (limit={limit}, page={page})")
        
        params = {
            'q': query,
            'per_page': limit,
            'page': page
        }
        
        try:
            response = self._make_request('search/books.json', params)
            books = response.get('search', {}).get('results', [])
            
            # Enrich with metadata
            enriched_books = []
            for book in books:
                enriched_book = {
                    **book.get('best_book', {}),
                    'search_query': query,
                    'ingestion_timestamp': datetime.utcnow().isoformat(),
                    'source': 'goodreads_api'
                }
                enriched_books.append(enriched_book)
            
            logger.info(f"Found {len(enriched_books)} books matching '{query}'")
            return enriched_books
            
        except Exception as e:
            logger.error(f"Search failed for '{query}': {str(e)}")
            raise
    
    def get_book_reviews(
        self,
        book_id: str,
        limit: int = 100,
        page: int = 1
    ) -> List[Dict]:
        """
        Fetch reviews for a specific book
        
        Args:
            book_id: GoodReads book ID
            limit: Number of reviews per page
            page: Page number
            
        Returns:
            List of review dictionaries
        """
        return self.get_recent_reviews(limit=limit, page=page, book_id=book_id)
    
    def close(self):
        """Close the session"""
        self.session.close()
        logger.info("Closed GoodReads client session")


# Example usage for testing
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize client
    client = GoodReadsClient(
        api_key=os.getenv('GOODREADS_API_KEY'),
        rate_limit=5
    )
    
    try:
        # Test API calls
        print("\n=== Testing GoodReads API Client ===\n")
        
        # Fetch recent books
        print("Fetching recent books...")
        books = client.get_recent_books(limit=5)
        print(f"✓ Fetched {len(books)} books")
        
        # Fetch popular authors
        print("\nFetching popular authors...")
        authors = client.get_popular_authors(limit=5)
        print(f"✓ Fetched {len(authors)} authors")
        
        # Fetch recent reviews
        print("\nFetching recent reviews...")
        reviews = client.get_recent_reviews(limit=10)
        print(f"✓ Fetched {len(reviews)} reviews")
        
        # Fetch genres
        print("\nFetching genres...")
        genres = client.get_all_genres()
        print(f"✓ Fetched {len(genres)} genres")
        
        # Search books
        print("\nSearching for 'harry potter'...")
        search_results = client.search_books('harry potter', limit=5)
        print(f"✓ Found {len(search_results)} books")
        
        print("\n=== All tests passed! ===\n")
        
    finally:
        client.close()
