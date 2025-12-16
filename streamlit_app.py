import streamlit as st
import requests
import json
import pandas as pd
from typing import List, Dict, Any, Optional 
from datetime import date
import pathlib

# --- Configuration ---
FASTAPI_BASE_URL = "http://127.0.0.1:8000" 

st.set_page_config(
    page_title="Book Management System",
    layout="wide"
)
if 'view_db' not in st.session_state:
    st.session_state.view_db = False

st.title("📚 Book Management System")

# Function to load local CSS
def local_css(file_name):
    with open(file_name) as f:
        st.html(f'<style>{f.read()}</style>')

# Load the External CSS
css_path = pathlib.Path("style.css") 
local_css(css_path)

# --- HELPER FUNCTION: To handle successful API calls ---
def handle_success(message):
    st.session_state.success_message = message
    st.cache_data.clear()
    st.rerun()

# --- HELPER FUNCTION: To handle API errors ---
def handle_error(response, default_message="An unknown error occurred."):
    try:
        error_detail = response.json().get("detail", default_message)
        st.error(f"API Error ({response.status_code}): {error_detail}")
    except json.JSONDecodeError:
        st.error(f"API Error ({response.status_code}): Failed to decode error message.")

# --- Helper Function for Displaying All Books ---
@st.cache_data(ttl=5) # Cache data for 5 seconds to reduce API calls
def fetch_all_books() -> pd.DataFrame:
    """Fetches all book records from the FastAPI /books/ endpoint."""
    try:
        response = requests.get(f"{FASTAPI_BASE_URL}/books/")
        if response.status_code == 200:
            return pd.DataFrame(response.json())
        elif response.status_code == 404:
            st.info("Local database is empty.")
        else:
            st.error(f"Error fetching all books: Status {response.status_code}")
        return pd.DataFrame()
    except requests.exceptions.ConnectionError:
        st.error("🚨 Connection Error: Is the FastAPI server running?")
        return pd.DataFrame()

# --- Session State Management ---
if 'fetched_book_data' not in st.session_state:
    st.session_state.fetched_book_data: Optional[Dict[str, Any]] = None

if not st.session_state.view_db:
    # --- UI Layout ---
    col1, col2 = st.columns([1, 2])

    # 🚀 COLUMN 1: ISBN LOOKUP AND SAVE FEATURE
    with col1:
        st.subheader("🔍 Add Or Remove Book")
        # --- STEP 1: ISBN Search ---
        search_isbn = st.text_input("Enter ISBN (10 or 13 digits)", key="isbn_search_input")
        cleaned_isbn = search_isbn.replace("-", "").replace(" ", "")
        
        col_submit, col_clear = st.columns([1, 1])
        with col_submit:
            if st.button("", key="submit"):
                if search_isbn:
                    st.session_state.fetched_book_data = None 
                    with st.spinner("⏳ Contacting API..."):
                        try:
                            # Call the FastAPI ISBN search endpoint
                            response = requests.get(f"{FASTAPI_BASE_URL}/search-isbn/{cleaned_isbn}")
                            
                            if response.status_code == 200:
                                book_data = response.json()
                                st.session_state.fetched_book_data = book_data 
                                st.success("✅ Book details fetched successfully! Review and Save below.")
                            else:
                                handle_error(response, default_message="Could not fetch book details.")
                                
                        except requests.exceptions.ConnectionError:
                            st.error("🚨 Connection Error: Is the FastAPI server running?")
                else:
                    st.warning("Please enter an ISBN to search.")
        
        with col_clear:
            if st.button("", key="clear"):
                if search_isbn:
                    st.session_state.fetched_book_data = None
                    with st.spinner("⏳ Contacting API to remove book..."):
                        try:
                            response = requests.delete(f"{FASTAPI_BASE_URL}/books/{cleaned_isbn}")
                            if response.status_code == 200:
                                handle_success(f"✅ Book with ISBN {cleaned_isbn} removed successfully!")
                            else:
                                handle_error(response, default_message="Could not remove book.")
                        except requests.exceptions.ConnectionError:
                            st.error("🚨 Connection Error: Is the FastAPI server running?")
        
        # --- STEP 2: Review and Save ---
        if st.session_state.fetched_book_data:
            data = st.session_state.fetched_book_data
            st.subheader("Review & Save")
            
            # Display the fetched data for review/editing
            final_title = st.text_input("Title", value=data.get('title', 'N/A'))
            final_author = st.text_input("Author", value=data.get('author', 'N/A'))
            final_pages = st.number_input("Pages", value=int(data.get('pages', 1)), min_value=1)
            final_genre = st.text_input("Genre", value=data.get('genre', 'General'))
            
            # The ISBN, status, and availability are typically hidden or set by the API/system
            isbn_display = data.get('isbn', 'N/A')
            st.caption(f"ISBN: **{isbn_display}**")
            
            # Save Button
            if st.button(
                    "SAVE BOOK TO DATABASE",
                    key="save_button"
                ):
                # 1. Prepare the final payload (must match your FastAPI Book model)
                book_to_save = {
                    "title": final_title,
                    "author": final_author,
                    "pages": int(final_pages),
                    "available": True, 
                    "isbn": isbn_display,
                    "genre": final_genre 
                }
                try:
                    # 2. Send the POST request to the saving endpoint
                    response = requests.post(f"{FASTAPI_BASE_URL}/books/", json=book_to_save)
                    
                    # 3. Handle response and clear state
                    if response.status_code == 201:
                        # Use helper function for success and UI refresh
                        st.session_state.fetched_book_data = None # Clear state for new entry
                        handle_success(f"✅ Book '{final_title}' saved successfully!")
                    else:
                        # Use helper function for API error response
                        handle_error(response, default_message="Failed to save book.")
                
                except requests.exceptions.ConnectionError:
                    st.error("🚨 Connection Error: Cannot connect to the FastAPI server.")
        
        # --- STEP 3: Loan & Status Update ---
        st.divider() 
        st.subheader("🔄 Loan & Status Update")

        loan_isbn = st.text_input("Enter ISBN to Issue or Return", key="loan_isbn_input_final")
        coustomer_id = st.text_input("Coustomer ID", key="customer_id_input_final")
        
        col_issue, col_spacer = st.columns([1, 1]) 

        with col_issue:
            # --- ACTION BUTTON: This button now acts as the final 'Submit' ---
            if st.button("ISSUE BOOK", key="button-77"):
                if loan_isbn and coustomer_id:
                    cleaned_loan_isbn = loan_isbn.replace("-", "").replace(" ", "")
                    
                    # 1. Safely convert to integer
                    try:
                        coustomer_id_int = int(coustomer_id)
                    except ValueError:
                        st.error("Customer ID must be a valid whole number (integer).")
                        st.stop() # Prevents the code from continuing with an empty ID

                    # 2. Build payload
                    payload = {
                        "isbn": cleaned_loan_isbn,
                        "coustomer_id": coustomer_id_int, 
                        "issue_date": date.today().isoformat()
                    }
                    
                    # 3. API Call
                    with st.spinner("Processing Issue..."):
                        try:
                            response = requests.post(
                                f"{FASTAPI_BASE_URL}/loans/",
                                json=payload
                            )
                            if response.status_code == 201:
                                # Clear inputs
                                if 'loan_isbn_input_final' in st.session_state:
                                    del st.session_state.loan_isbn_input_final
                                if 'customer_id_input_final' in st.session_state:
                                    del st.session_state.customer_id_input_final
                                
                                handle_success(f"✅ Success! ISBN {cleaned_loan_isbn} has been issued to Customer {coustomer_id_int}.")
                            else:
                                handle_error(response, "Failed to issue book.")

                        except requests.exceptions.ConnectionError:
                            st.error("Connection Error: Ensure your FastAPI backend server is running.")

                else:
                    if not loan_isbn:
                        st.warning("Please enter the **ISBN**.")
                    elif not coustomer_id:
                        st.warning("Please enter the **Customer ID**.")
                        
        with col_spacer:
            if st.button("RETURN BOOK", key="button-78"):
                if loan_isbn and coustomer_id:
                    cleaned_loan_isbn = loan_isbn.replace("-", "").replace(" ", "")
                    
                    # Build the payload to match the ReturnRequest Pydantic model
                    try:
                        coustomer_id_int = int(coustomer_id)
                    except ValueError:
                        st.error("Customer ID must be a valid number.")

                    payload = {
                        "isbn": cleaned_loan_isbn,
                        "coustomer_id": coustomer_id_int,
                    }
                    
                    # --- FastAPI Endpoint Call for RETURN ---
                    try:
                        response = requests.post(
                            f"{FASTAPI_BASE_URL}/loans/return/",
                            json=payload
                        )
                        
                        if response.status_code == 200:
                            # Success: Loan record updated and book status updated
                            st.success("✅ Book issued successfully!")
                            handle_success(f"ISBN {cleaned_loan_isbn} *returned* and marked available. Status updated.")
                        else:
                            handle_error(response, "Failed to return book.")
                            
                    except requests.exceptions.ConnectionError:
                        st.error("Connection Error: Ensure your FastAPI backend server is running.")

                else:
                    if not loan_isbn:
                        st.warning("Please enter the **ISBN** to return the book.")
                    elif not coustomer_id:
                        st.warning("Please enter the **Coustomer ID** before clicking the button.")
            
    # Column 2: Quick Actions
    with col2:
        st.header("Quick Actions")
        if st.button("🔍 OPEN FULL DATABASE", type="primary", use_container_width=True):
            st.session_state.view_db = True
            st.rerun()
        
        # Show mini stats
        df_books = fetch_all_books()
        if not df_books.empty:
            st.metric("Total Books", len(df_books))
            st.metric("Available", df_books['available'].sum())

else:
    # --- DATABASE VIEW ---
    st.subheader("📊 Full Book Database")
    
    if st.button("⬅️ Back to Management"):
        st.session_state.view_db = False
        st.rerun()

    # Load and display the table
    df_books = fetch_all_books()
    if not df_books.empty:
        # Add a search bar for the database
        search = st.text_input("Filter by Title or Author")
        if search:
            df_books = df_books[df_books['title'].str.contains(search, case=False) | 
                                df_books['author'].str.contains(search, case=False)]
        
        st.dataframe(df_books, use_container_width=True, height=500)
    else:
        st.info("No books found in the database.")
