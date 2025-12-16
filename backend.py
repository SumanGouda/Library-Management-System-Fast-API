from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import requests
import json
import os
from datetime import date, timedelta

# --- Configuration & Data Model ---
GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"
app = FastAPI()

DB_FILE_PATH = "book_database.json" 
books_db: List['Book'] = []

LOAN_DB_FILE_PATH = "loan_records.json"
loans_db: List['LoanRecord'] = []

class Book(BaseModel):
    title: str
    author: str # Note: Streamlit sends a single author string
    pages: int
    available: bool = True
    isbn: str
    genre: str

class LoanRecord(BaseModel):
    isbn: str
    coustomer_id: int
    issue_date: date = date.today()
    due_date: date = Field(default_factory=lambda: date.today() + timedelta(days=30))
    returned: bool = False

class ReturnRequest(BaseModel):
    isbn: str
    coustomer_id: int
    
# --- File I/O Helper Functions ---
def load_data_from_json():
    """Loads book data from a local JSON file into the global list."""
    global books_db
    if os.path.exists(DB_FILE_PATH):
        try:
            with open(DB_FILE_PATH, "r") as f:
                raw_data = json.load(f)
                # Convert raw data into Pydantic models for validation
                books_db = [Book(**record) for record in raw_data]
            print(f"Loaded {len(books_db)} books from {DB_FILE_PATH}")
        except Exception as e:
            print(f"Error loading database: {e}")
            books_db = []
    else:
        print("Database file not found. Starting with an empty database.")

def save_data_to_json():
    """Saves the current global books list back to the JSON file."""
    # Convert Pydantic models to dictionaries for JSON serialization
    data_to_save = [book.model_dump() for book in books_db]
    try:
        with open(DB_FILE_PATH, "w") as f:
            json.dump(data_to_save, f, indent=4)
    except Exception as e:
        print(f"Error saving database: {e}")

def load_loans_from_json():
    """Loads loan records from a local JSON file into a global list."""
    global loans_db
    loans_db = []
    if os.path.exists(LOAN_DB_FILE_PATH):
        try:
            with open(LOAN_DB_FILE_PATH, "r") as f:
                raw_data = json.load(f)
                loans_db = [LoanRecord(**record) for record in raw_data]
            print(f"Loaded {len(loans_db)} loan records from {LOAN_DB_FILE_PATH}")
        except Exception as e:
            print(f"Error loading loan records: {e}")
            loans_db = []
    else:
        print("Loan records file not found. Starting with an empty loan database.")

def save_loans_to_json():
    """Saves the current global loans list back to the JSON file."""
    json_list = [
        loan.model_dump(
            mode='json',
            exclude_none=False,      
            exclude_defaults=False   
        ) 
        for loan in loans_db
    ]
    try:
        with open(LOAN_DB_FILE_PATH, "w") as f:
            json.dump(json_list, f, indent=4)
    except Exception as e:
        print(f"Error saving loan records: {e}")       
        
# Initialize the database on startup
load_data_from_json()
load_loans_from_json()

# --- Google Books API Helper ---
def fetch_book_data_from_google(isbn: str) -> Optional[dict]:
    """Queries the Google Books API using ISBN and returns simplified book data."""
    try:
        params = {'q': f'isbn:{isbn}'}
        response = requests.get(GOOGLE_BOOKS_API_URL, params=params)
        response.raise_for_status() # Raises an HTTPError for 4xx/5xx status codes
        
        data = response.json()
        
        if data.get('totalItems', 0) > 0 and 'items' in data:
            volume_info = data['items'][0]['volumeInfo']
            
            # Extract authors and join them into a single string for the Book model
            authors_list = volume_info.get('authors', ["Unknown Author"])
            single_author = ", ".join(authors_list)
            
            # Simple guess for genre based on categories, otherwise default
            genres = volume_info.get('categories', ["General"])
            
            book_info = {
                "isbn": isbn,
                "title": volume_info.get('title', 'No Title'),
                "author": single_author,
                "pages": volume_info.get('pageCount', 0),
                "genre": genres[0],
                "available": True
            }
            return book_info
        
        return None # Book not found
        
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Google Books API: {e}")
        return None

# --- FastAPI Endpoints ---
@app.get("/books/", response_model=List[Book], summary="Retrieve all books from local database")
def get_all_books():
    """Returns the entire list of books loaded from the JSON file."""
    if not books_db:
        raise HTTPException(status_code=404, detail="Database is empty or not loaded.")
    return books_db

@app.get("/search-isbn/{isbn}", summary="Look up book details by ISBN using Google Books API")
def lookup_book(isbn: str):
    """Fetches detailed book information from Google Books API for frontend review."""
    
    # Check if the book is already in the database
    if any(b.isbn == isbn for b in books_db):
        raise HTTPException(status_code=400, detail=f"Book with ISBN {isbn} is already in the database.")
        
    book_data = fetch_book_data_from_google(isbn)
    
    if book_data:
        # We return the raw dictionary; the frontend will display it.
        # We don't use response_model=Book here because we just return a dict of fetched data
        return book_data 
    else:
        raise HTTPException(status_code=404, detail=f"Book with ISBN {isbn} not found on Google Books API.")

@app.post("/books/", response_model=Book, status_code=201, summary="Add a new book record")
def add_book(book: Book):
    """Receives validated book data from the frontend and saves it to the local database."""
    global books_db
    
    # Final check for duplicate ISBN
    if any(b.isbn == book.isbn for b in books_db):
        raise HTTPException(status_code=400, detail="Book with this ISBN already exists.")
    
    books_db.append(book)
    save_data_to_json() 
    
    return book

@app.post("/loans/", response_model=LoanRecord, status_code=201, summary="Record a new book loan")
def issue_book(loan: LoanRecord):
    """
    1. Checks if the book exists and is available.
    2. Records the loan to the loans_db.
    3. Updates the book's status in books_db (sets available=False) and saves the main database.
    """
    global books_db, loans_db
    
    # 1. Check if the book exists and get a reference to it
    book_to_update = next((b for b in books_db if b.isbn == loan.isbn), None)
    
    if not book_to_update:
        # 404: Not Found
        raise HTTPException(status_code=404, detail="Book with this ISBN does not exist.")
        
    if not book_to_update.available:
        # 400: Bad Request (Cannot issue an unavailable book)
        raise HTTPException(status_code=400, detail="Book is currently not available for loan.")
    
    # 2. Record the loan
    loans_db.append(loan)
    save_loans_to_json()
    
    # 3. Update the book's status (This updates the object in books_db)
    book_to_update.available = False
    
    # Save the main database with the updated status
    save_data_to_json()
    
    return loan

@app.post("/loans/return/", response_model=Book, status_code=200, summary="Records a book return and updates availability")
def return_book(return_request: ReturnRequest):
    """
    Accepts an ISBN in the request body, records the book as returned in loans_db,
    and updates the book's status in the main books_db to available=True.
    """
    global books_db, loans_db
    isbn = return_request.isbn
    
    # --- 1. Find the Book ---
    book_to_update = next((b for b in books_db if b.isbn == isbn), None)
    
    if not book_to_update:
        raise HTTPException(status_code=404, detail=f"Book with ISBN {isbn} not found in collection.")
    
    if book_to_update.available:
        raise HTTPException(status_code=400, detail="Book is already marked as available. No return needed.")

    # --- 2. Find the Active Loan Record ---
    active_loan = next(
        (loan for loan in reversed(loans_db) if loan.isbn == isbn and loan.returned == False), 
        None
    )
    
    if not active_loan:
        raise HTTPException(status_code=400, detail="No active loan record found for this ISBN. Check the main database for status.")
        
    # --- 3. Update the Loan Record ---
    active_loan.returned = True
    active_loan.due_date = date.today()  # Record the actual return date
    save_loans_to_json() # Save the updated loan record

    # --- 4. Update Main Book Database Status ---
    book_to_update.available = True 
    save_data_to_json() 
    
    return book_to_update

@app.delete("/books/{isbn}", status_code=200, summary="Delete a book record by ISBN")
def delete_book(isbn: str):
    """Deletes a book from the main database if it exists and is available."""
    global books_db
    
    # Check if the book exists
    book_to_delete = next((b for b in books_db if b.isbn == isbn), None)
    
    if not book_to_delete:
        raise HTTPException(status_code=404, detail=f"Book with ISBN {isbn} not found in database.")
    
    # Optionally, check if the book is currently on loan before deletion
    if not book_to_delete.available:
        active_loan_exists = any(loan.isbn == isbn and loan.returned == False for loan in loans_db)
        if active_loan_exists:
            raise HTTPException(status_code=400, detail=f"Book with ISBN {isbn} is currently on loan and cannot be deleted.")

    # Remove the book from the global list
    books_db = [b for b in books_db if b.isbn != isbn]
    save_data_to_json() 
    
    return {"message": f"Book with ISBN {isbn} successfully deleted."}