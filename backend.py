from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import requests
import json
import os
from datetime import date, timedelta

# --- Configuration & Data Model ---
GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"
app = FastAPI()

DB_FILE_PATH = "book_database.json" 
books_map: Dict[str, Book] = {} 
def load_data_from_json():
    global books_map
    if os.path.exists(DB_FILE_PATH):
        with open(DB_FILE_PATH, "r") as f:
            raw_data = json.load(f)
            # Store in a dictionary for O(1) lookup
            books_map = {record['isbn']: Book(**record) for record in raw_data}

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

class RegisterCostomer(BaseModel):
    coustomer_id : int
    name : str
    email_id : str
    mobile_number : int
    
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
    """Saves the current global books map back to the JSON file."""
    data_to_save = [book.model_dump() for book in books_map.values()]
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

def register_user_json(user: RegisterCostomer):
    try:
        users_db = []
        if os.path.exists("user_database.json"):
            with open("user_database.json", "r") as f:
                try:
                    raw_data = json.load(f)
                    users_db = [RegisterCostomer(**record) for record in raw_data]
                except json.JSONDecodeError:
                    users_db = []

        # 1. Add user and Sort by coustomer_id
        users_db.append(user)
        # Sort the list based on the ID key
        users_db.sort(key=lambda x: x.coustomer_id)

        # 2. Save the new-sorted list
        with open("user_database.json", "w") as f:
            json.dump([u.model_dump() for u in users_db], f, indent=4)
        
        return user
    except Exception as e:
        raise Exception(f"Failed to save user: {str(e)}")

# 3. Efficient Binary Search Helper
def find_user_binary(target_id: int, users_list: list) -> bool:
    low = 0
    high = len(users_list) - 1

    while low <= high:
        mid = (low + high) // 2
        mid_id = users_list[mid].get("coustomer_id")
        
        if mid_id == target_id:
            return True # User found!
        elif mid_id < target_id:
            low = mid + 1
        else:
            high = mid - 1
            
    return False # User not found
        
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
@app.post("/customers/", response_model=RegisterCostomer, status_code=201, summary="Add a new customer record")
def register_user(user: RegisterCostomer):
    try:
        users_db = []
        file_path = "user_database.json"

        # Load existing data
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                try:
                    users_db = json.load(f)
                except json.JSONDecodeError:
                    users_db = []

        # Check if ID already exists (using binary search before adding)
        if find_user_binary(user.coustomer_id, users_db):
            raise HTTPException(status_code=400, detail="User ID already registered.")

        # Add and Sort
        users_db.append(user.model_dump())
        users_db.sort(key=lambda x: x['coustomer_id'])

        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
    
        # Save sorted data
        with open(file_path, "w") as f:
            json.dump(users_db, f, indent=4)
        
        return {"message": "User registered successfully", "user": user}

    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/books/", response_model=List[Book], summary="Retrieve all books from local database")
def get_all_books():
    global books_map
    # Check if the map is empty
    if not books_map:
        return [] 
    
    # Return dictionary values as a list
    return list(books_map.values())

@app.get("/search-isbn/{isbn}", summary="Look up book details by ISBN using Google Books API")
def lookup_book(isbn: str):
    global books_map
    
    # OPTIMIZED: Constant time check
    if isbn in books_map:
        raise HTTPException(status_code=400, detail=f"Book with ISBN {isbn} is already in the database.")
        
    book_data = fetch_book_data_from_google(isbn)
    
    if book_data:
        return book_data 
    else:
        raise HTTPException(status_code=404, detail=f"Book with ISBN {isbn} not found on Google Books API.")
    
@app.post("/books/", response_model=Book, status_code=201, summary="Add a new book record")
def add_book(book: Book):
    global books_map
    
    # OPTIMIZED: Instant check for duplicate
    if book.isbn in books_map:
        raise HTTPException(status_code=400, detail="Book with this ISBN already exists.")
    
    # OPTIMIZED: O(1) Insertion
    books_map[book.isbn] = book
    
    save_data_to_json() 
    return book

@app.post("/loans/", response_model=LoanRecord, status_code=201, summary="Record a new book loan")
def issue_book(loan: LoanRecord):
    # We reference books_map (dict)
    global books_map, loans_db 
    
    # 1. Load users to verify registration
    if not os.path.exists("user_database.json"):
         raise HTTPException(status_code=500, detail="User database not found.")
    
    with open("user_database.json", "r") as f:
        try:
            users_list = json.load(f)
        except json.JSONDecodeError:
            users_list = []

    # 2. APPLY BINARY SEARCH (O(log n))
    if not find_user_binary(loan.coustomer_id, users_list):
        raise HTTPException(
            status_code=403, 
            detail=f"Access Denied: Customer ID {loan.coustomer_id} is not registered."
        )

    # 3. HASH MAP LOOKUP (O(1))
    book_to_update = books_map.get(loan.isbn)
    
    if not book_to_update:
        raise HTTPException(status_code=404, detail="Book with this ISBN does not exist in the library.")
        
    if not book_to_update.available:
        raise HTTPException(status_code=400, detail="This book is already issued to another customer.")

    # 4. Finalize Loan
    loans_db.append(loan)
    save_loans_to_json()
    
    # Update the object inside the map
    book_to_update.available = False
    
    # 5. Save changes back to file
    save_data_to_json() 
    
    return loan

@app.post("/loans/return/", response_model=Book, status_code=200, summary="Records a book return and updates availability")
def return_book(return_request: ReturnRequest):
    # Use the optimized books_map and loans_db
    global books_map, loans_db
    isbn = return_request.isbn
    
    # --- 1. OPTIMIZED: Find the Book using Hash Map (O(1)) ---
    book_to_update = books_map.get(isbn)
    
    if not book_to_update:
        raise HTTPException(status_code=404, detail=f"Book with ISBN {isbn} not found in collection.")
    
    if book_to_update.available:
        raise HTTPException(status_code=400, detail="Book is already marked as available. No return needed.")

    # --- 2. Find the Active Loan Record ---
    # We still search the list reversed to find the MOST RECENT active loan
    active_loan = next(
        (loan for loan in reversed(loans_db) if loan.isbn == isbn and not loan.returned), 
        None
    )
    
    if not active_loan:
        raise HTTPException(status_code=400, detail="No active loan record found for this ISBN.")
        
    # --- 3. Update the Loan Record ---
    active_loan.returned = True
    active_loan.due_date = date.today()  # Record the actual return date
    save_loans_to_json() 

    # --- 4. Update Status in Hash Map ---
    book_to_update.available = True 
    save_data_to_json() 
    
    return book_to_update

@app.delete("/books/{isbn}", status_code=200, summary="Delete a book record by ISBN")
def delete_book(isbn: str):
    global books_map, loans_db
    
    # 1. OPTIMIZED: O(1) Lookup
    book_to_delete = books_map.get(isbn)
    
    if not book_to_delete:
        raise HTTPException(status_code=404, detail=f"Book with ISBN {isbn} not found.")
    
    # 2. Safety Check: Don't delete books that are currently out
    if not book_to_delete.available:
        # Check if there is an unreturned loan
        active_loan_exists = any(loan.isbn == isbn and not loan.returned for loan in loans_db)
        if active_loan_exists:
            raise HTTPException(
                status_code=400, 
                detail="Cannot delete book: It is currently on loan."
            )

    # 3. OPTIMIZED: O(1) Deletion from Hash Map
    books_map.pop(isbn)
    save_data_to_json() 
    
    return {"message": f"Book {isbn} successfully removed from catalog."}

@app.get("/loans/coustomer/{coustomer_id}")
def get_student_loans(coustomer_id: int):
    try:
        # 1. PRE-CHECK: Use Binary Search to verify user exists first
        if os.path.exists("user_database.json"):
            with open("user_database.json", "r") as f:
                users_list = json.load(f)
            
            if not find_user_binary(coustomer_id, users_list):
                raise HTTPException(status_code=404, detail="Customer ID not found in registration.")

        # 2. Fetch Loans
        if not os.path.exists(LOAN_DB_FILE_PATH):
            return []

        with open(LOAN_DB_FILE_PATH, "r") as f:
            all_loans = json.load(f)

        # 3. Filter history
        coustomer_history = [
            loan for loan in all_loans 
            if loan.get("coustomer_id") == coustomer_id
        ]
        
        return coustomer_history

    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))