from pydantic import BaseModel, EmailStr, AnyUrl
from typing import List, Dict, Optional
import fastapi

class Book(BaseModel):
    title: str
    email:EmailStr
    url: AnyUrl
    author: str
    pages: int
    available: bool
    
app = fastapi.FastAPI()

book_db = []

@app.post("/books/")
def add_book(book: Book):
    book_db.append(book)
    return {"message": "Book added successfully", "book": book}

@app.get("/books/{title}")
def get_books(title: str):
    for book in book_db:
        if book.title == title:
            return {"book": book}
    return {"message": "Book not found"}

@app.get("/books/")
def list_books():
    return {"books": book_db}

@app.patch("/books/{title}")
def update_book_availability(title: str, available: bool):
    for book in book_db:
        if book.title == title:
            book.available = available
            return {"message": "Book availability updated", "book": book}
    return {"message": "Book not found"}

@app.delete("/books/{title}")
def delete_book(title: str):
    for book in book_db:
        if book.title == title:
            book_db.remove(book)
            return {"message": "Book deleted successfully"}
    return {"message": "Book not found"}