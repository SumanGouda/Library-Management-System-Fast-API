from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import requests
import json
import os
from datetime import date, timedelta

# --- Configuration & Paths ---
app = FastAPI()
DB_FILE_PATH = "book_database.json" 
LOAN_DB_FILE_PATH = "loan_records.json"
GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"

# --- Pydantic Models ---
class Book(BaseModel):
    title: str
    author: str
    pages: int
    available: bool = True
    isbn: str
    genre: str

class LoanRecord(BaseModel):
    isbn: str
    coustomer_id: int
    issue_date: date = Field(default_factory=date.today)
    due_date: date = Field(
        default_factory=lambda: date.today() + timedelta(days=30)
    )
    returned: bool = False

class ReturnRequest(BaseModel):
    isbn: str
    coustomer_id: int

class RegisterCostomer(BaseModel):
    coustomer_id: int
    name: str
    email_id: str
    mobile_number: int

# --- Global State for Books & Loans (In-Memory for Speed) ---
books_map: Dict[str, Book] = {}
loans_db: List[LoanRecord] = []

def load_all_data():
    global books_map, loans_db
    # Load Books into Hash Map (O(1) lookup)
    if os.path.exists(DB_FILE_PATH):
        with open(DB_FILE_PATH, "r") as f:
            try:
                raw_books = json.load(f)
                books_map = {r['isbn']: Book(**r) for r in raw_books}
            except json.JSONDecodeError: books_map = {}
    
    # Load Loans into List
    if os.path.exists(LOAN_DB_FILE_PATH):
        with open(LOAN_DB_FILE_PATH, "r") as f:
            try:
                raw_loans = json.load(f)
                loans_db = [LoanRecord(**r) for r in raw_loans]
            except json.JSONDecodeError: loans_db = []

def save_books():
    with open(DB_FILE_PATH, "w") as f:
        json.dump([b.model_dump() for b in books_map.values()], f, indent=4)

def save_loans():
    json_list = [l.model_dump(mode='json') for l in loans_db]
    with open(LOAN_DB_FILE_PATH, "w") as f:
        json.dump(json_list, f, indent=4)

@app.post("/customers/", status_code=201)
def register_user(user: RegisterCostomer):
    conn = get_db_connection()
    try:
        # Check existence via SQL Index (Faster than Binary Search)
        existing = conn.execute('SELECT 1 FROM customers WHERE coustomer_id = ?', (user.coustomer_id,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="User ID already registered.")
        
        conn.execute('''
            INSERT INTO customers (coustomer_id, name, email_id, mobile_number)
            VALUES (?, ?, ?, ?)
        ''', (user.coustomer_id, user.name, user.email_id, user.mobile_number))
        conn.commit()
        return user
    finally:
        conn.close()

@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: int):
    # 1. Verification: User must have NO active loans
    global loans_db
    active_loans = [l for l in loans_db if l.coustomer_id == customer_id and not l.returned]
    if active_loans:
        raise HTTPException(status_code=400, detail=f"Cannot delete: User has {len(active_loans)} books issued.")

    # 2. Delete from SQL
    conn = get_db_connection()
    try:
        cursor = conn.execute('DELETE FROM customers WHERE coustomer_id = ?', (customer_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found.")
        return {"message": "User successfully removed from database."}
    finally:
        conn.close()

@app.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM customers WHERE coustomer_id = ?', (customer_id,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return dict(user)

# --- Book Endpoints (Hash Map Powered) ---
@app.get("/books/", response_model=List[Book])
def get_all_books():
    return list(books_map.values())

@app.get("/search-isbn/{isbn}")
def lookup_book(isbn: str):
    if isbn in books_map:
        raise HTTPException(status_code=400, detail="Book already in local database.")
    
    # Google Books Fetch
    clean_isbn = isbn.strip().replace("-", "").replace(" ", "")
    try:
        response = requests.get(f"{GOOGLE_BOOKS_API_URL}?q=isbn:{clean_isbn}", timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get("totalItems", 0) == 0:
            raise HTTPException(status_code=404, detail="Not found in Google API.")
        
        vol = data["items"][0]["volumeInfo"]
        return {
            "isbn": clean_isbn,
            "title": vol.get("title", "Unknown"),
            "author": ", ".join(vol.get("authors", ["Unknown"])),
            "pages": vol.get("pageCount", 0),
            "genre": vol.get("categories", ["General"])[0],
            "available": True
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/books/", status_code=201)
def add_book(book: Book):
    if book.isbn in books_map:
        raise HTTPException(status_code=400, detail="ISBN exists.")
    books_map[book.isbn] = book
    save_books()
    return book

# --- Loan Endpoints (Combined Logic) ---

@app.post("/loans/", status_code=201)
def issue_book(loan: LoanRecord):
    global books_map, loans_db
    
    # 1. Verify User exists in SQL
    conn = get_db_connection()
    user = conn.execute('SELECT 1 FROM customers WHERE coustomer_id = ?', (loan.coustomer_id,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=403, detail="Customer not registered.")

    # 2. Check Book in Hash Map
    book = books_map.get(loan.isbn)
    if not book or not book.available:
        raise HTTPException(status_code=400, detail="Book unavailable or doesn't exist.")

    # 3. Finalize
    book.available = False
    loans_db.append(loan)
    save_books()
    save_loans()
    return loan

@app.post("/loans/return/")
def return_book(req: ReturnRequest):
    global books_map, loans_db
    
    book = books_map.get(req.isbn)
    if not book or book.available:
        raise HTTPException(status_code=400, detail="Invalid return request.")

    # Find active loan
    loan = next(
    (
        l for l in reversed(loans_db)
        if l.isbn == req.isbn
        and l.coustomer_id == req.coustomer_id
        and not l.returned
    ),
    None
    )
    if not loan:
        raise HTTPException(status_code=404, detail="No active loan found.")

    loan.returned = True
    book.available = True
    save_books()
    save_loans()
    return book

@app.get("/loans/coustomer/{coustomer_id}")
def get_customer_history(coustomer_id: int):
    history = [l for l in loans_db if l.coustomer_id == coustomer_id]
    return history