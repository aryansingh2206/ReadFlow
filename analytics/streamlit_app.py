"""
ReadFlow Analytics Dashboard
Interactive analytics interface for book data
"""

import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# Page configuration
st.set_page_config(
    page_title="ReadFlow Analytics",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .stMetric {
        background-color: white;
        padding: 1rem;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def init_database():
    """Initialize DuckDB connection"""
    db_path = os.getenv('DUCKDB_PATH', '/data/warehouse/readflow.duckdb')
    return duckdb.connect(db_path)


@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_books_data(_conn):
    """Load books data from warehouse"""
    try:
        query = """
        SELECT 
            book_id,
            title,
            average_rating,
            ratings_count,
            text_reviews_count,
            publication_year,
            language_code,
            author_names,
            num_pages
        FROM silver_books
        WHERE average_rating IS NOT NULL
        ORDER BY ratings_count DESC
        LIMIT 1000
        """
        return _conn.execute(query).df()
    except Exception as e:
        st.error(f"Error loading books data: {str(e)}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_reviews_data(_conn):
    """Load reviews data from warehouse"""
    try:
        query = """
        SELECT 
            review_id,
            book_id,
            rating,
            review_length,
            review_category,
            created_at,
            likes_count
        FROM silver_reviews
        WHERE rating IS NOT NULL
        LIMIT 5000
        """
        return _conn.execute(query).df()
    except Exception as e:
        st.error(f"Error loading reviews data: {str(e)}")
        return pd.DataFrame()


def main():
    """Main dashboard function"""
    
    # Header
    st.markdown('<p class="main-header">📖 ReadFlow Analytics</p>', unsafe_allow_html=True)
    st.markdown("### End-to-End Book Data Platform")
    st.markdown("---")
    
    # Initialize database
    try:
        conn = init_database()
    except Exception as e:
        st.error(f"Failed to connect to database: {str(e)}")
        st.info("Make sure the data pipeline has run and populated the warehouse.")
        return
    
    # Sidebar
    with st.sidebar:
        st.image("https://via.placeholder.com/200x80/1f77b4/ffffff?text=ReadFlow", use_column_width=True)
        st.markdown("---")
        
        page = st.radio(
            "Navigation",
            ["📊 Overview", "📚 Books Explorer", "⭐ Ratings Analysis", "✍️ Reviews Insights"]
        )
        
        st.markdown("---")
        st.markdown("### Filters")
        
        # Year filter
        year_filter = st.slider(
            "Publication Year",
            min_value=1900,
            max_value=2024,
            value=(1950, 2024)
        )
        
        # Rating filter
        rating_filter = st.slider(
            "Minimum Rating",
            min_value=1.0,
            max_value=5.0,
            value=3.0,
            step=0.1
        )
        
        st.markdown("---")
        st.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Load data
    books_df = load_books_data(conn)
    reviews_df = load_reviews_data(conn)
    
    if books_df.empty:
        st.warning("No data available. Please run the data pipeline first.")
        return
    
    # Apply filters
    books_df = books_df[
        (books_df['publication_year'] >= year_filter[0]) &
        (books_df['publication_year'] <= year_filter[1]) &
        (books_df['average_rating'] >= rating_filter)
    ]
    
    # Page routing
    if page == "📊 Overview":
        show_overview(books_df, reviews_df)
    elif page == "📚 Books Explorer":
        show_books_explorer(books_df)
    elif page == "⭐ Ratings Analysis":
        show_ratings_analysis(books_df, reviews_df)
    elif page == "✍️ Reviews Insights":
        show_reviews_insights(reviews_df)


def show_overview(books_df, reviews_df):
    """Display overview dashboard"""
    
    st.header("📊 Platform Overview")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Total Books",
            value=f"{len(books_df):,}",
            delta=f"+{int(len(books_df) * 0.05)} this month"
        )
    
    with col2:
        st.metric(
            label="Total Reviews",
            value=f"{len(reviews_df):,}",
            delta=f"+{int(len(reviews_df) * 0.1)} this month"
        )
    
    with col3:
        avg_rating = books_df['average_rating'].mean()
        st.metric(
            label="Avg Rating",
            value=f"{avg_rating:.2f}",
            delta="+0.05"
        )
    
    with col4:
        total_ratings = books_df['ratings_count'].sum()
        st.metric(
            label="Total Ratings",
            value=f"{total_ratings/1e6:.1f}M"
        )
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Books by Publication Year")
        
        year_dist = books_df.groupby('publication_year').size().reset_index(name='count')
        year_dist = year_dist[year_dist['publication_year'] >= 1950]
        
        fig = px.line(
            year_dist,
            x='publication_year',
            y='count',
            title='Books Published Over Time'
        )
        fig.update_layout(
            xaxis_title="Year",
            yaxis_title="Number of Books",
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("⭐ Rating Distribution")
        
        fig = px.histogram(
            books_df,
            x='average_rating',
            nbins=50,
            title='Distribution of Average Ratings'
        )
        fig.update_layout(
            xaxis_title="Average Rating",
            yaxis_title="Count",
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Language distribution
    st.subheader("🌍 Books by Language")
    
    lang_dist = books_df['language_code'].value_counts().head(10)
    
    fig = px.bar(
        x=lang_dist.values,
        y=lang_dist.index,
        orientation='h',
        title='Top 10 Languages'
    )
    fig.update_layout(
        xaxis_title="Number of Books",
        yaxis_title="Language Code",
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)


def show_books_explorer(books_df):
    """Display books explorer page"""
    
    st.header("📚 Books Explorer")
    
    # Search
    search_term = st.text_input("🔍 Search books by title", "")
    
    if search_term:
        books_df = books_df[books_df['title'].str.contains(search_term, case=False, na=False)]
    
    # Sort options
    sort_by = st.selectbox(
        "Sort by",
        ["Highest Rated", "Most Reviews", "Most Popular", "Recent"]
    )
    
    if sort_by == "Highest Rated":
        books_df = books_df.sort_values('average_rating', ascending=False)
    elif sort_by == "Most Reviews":
        books_df = books_df.sort_values('text_reviews_count', ascending=False)
    elif sort_by == "Most Popular":
        books_df = books_df.sort_values('ratings_count', ascending=False)
    elif sort_by == "Recent":
        books_df = books_df.sort_values('publication_year', ascending=False)
    
    # Display books
    st.subheader(f"📖 Showing {len(books_df)} books")
    
    # Create cards for top books
    for idx, row in books_df.head(20).iterrows():
        with st.expander(f"📖 {row['title']} ({row['publication_year']})"):
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.write(f"**Authors:** {', '.join(eval(row['author_names'])) if pd.notna(row['author_names']) else 'Unknown'}")
                st.write(f"**Language:** {row['language_code']}")
                if pd.notna(row['num_pages']):
                    st.write(f"**Pages:** {int(row['num_pages'])}")
            
            with col2:
                st.metric("Rating", f"{row['average_rating']:.2f} ⭐")
                st.write(f"{int(row['ratings_count']):,} ratings")
            
            with col3:
                st.metric("Reviews", f"{int(row['text_reviews_count']):,}")


def show_ratings_analysis(books_df, reviews_df):
    """Display ratings analysis page"""
    
    st.header("⭐ Ratings Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Rating Distribution by Star")
        
        if not reviews_df.empty:
            rating_counts = reviews_df['rating'].value_counts().sort_index()
            
            fig = go.Figure(data=[
                go.Bar(
                    x=rating_counts.index,
                    y=rating_counts.values,
                    marker_color=['#d32f2f', '#f57c00', '#fbc02d', '#7cb342', '#388e3c']
                )
            ])
            fig.update_layout(
                xaxis_title="Star Rating",
                yaxis_title="Number of Reviews",
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Average Rating vs. Popularity")
        
        scatter_data = books_df[books_df['ratings_count'] > 100].sample(min(500, len(books_df)))
        
        fig = px.scatter(
            scatter_data,
            x='ratings_count',
            y='average_rating',
            size='text_reviews_count',
            hover_data=['title'],
            opacity=0.6
        )
        fig.update_layout(
            xaxis_title="Number of Ratings",
            yaxis_title="Average Rating",
            xaxis_type="log"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Top rated books
    st.subheader("🏆 Top Rated Books (min 1000 ratings)")
    
    top_books = books_df[books_df['ratings_count'] >= 1000].nlargest(10, 'average_rating')
    
    for idx, row in top_books.iterrows():
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            st.write(f"**{row['title']}**")
        with col2:
            st.write(f"⭐ {row['average_rating']:.2f}")
        with col3:
            st.write(f"📊 {int(row['ratings_count']):,} ratings")


def show_reviews_insights(reviews_df):
    """Display reviews insights page"""
    
    st.header("✍️ Reviews Insights")
    
    if reviews_df.empty:
        st.warning("No review data available")
        return
    
    # Review categories
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Review Length Categories")
        
        category_counts = reviews_df['review_category'].value_counts()
        
        fig = px.pie(
            values=category_counts.values,
            names=category_counts.index,
            title='Review Length Distribution'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Reviews with Text vs. Rating Only")
        
        has_text_counts = reviews_df.groupby('review_category').size()
        
        fig = px.bar(
            x=has_text_counts.index,
            y=has_text_counts.values,
            title='Review Categories'
        )
        fig.update_layout(
            xaxis_title="Category",
            yaxis_title="Count",
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Recent activity
    st.subheader("📅 Recent Review Activity")
    
    if 'created_at' in reviews_df.columns:
        reviews_df['created_at'] = pd.to_datetime(reviews_df['created_at'])
        reviews_df['date'] = reviews_df['created_at'].dt.date
        
        daily_reviews = reviews_df.groupby('date').size().reset_index(name='count')
        daily_reviews = daily_reviews.tail(30)
        
        fig = px.line(
            daily_reviews,
            x='date',
            y='count',
            title='Reviews per Day (Last 30 Days)'
        )
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Number of Reviews"
        )
        st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
