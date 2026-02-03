# ⚡ AeroLib | High-Performance Library Engine
# <p align="center"><img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Books.png" width="50" align = "Center" /> AeroLib Engine
<p align="center"> <b>A high-speed Library Management System for the Desktop Web.</b><br> <i>Now powered by a Cleaned SQL Architecture.</i> </p>
---
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![MySQL](https://img.shields.io/badge/Database-MySQL-4479A1?style=for-the-badge&logo=mysql)](https://www.mysql.com/)
[![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B?style=for-the-badge&logo=streamlit)](https://streamlit.io/)

> **The Goal:** Building a lightning-fast, persistent library management system for the modern desktop web.

---

## 💎 The "Aero" Update: SQL Migration
The latest version of AeroLib introduces a **Cleaned Feature** architecture. We moved away from volatile, memory-heavy JSON lists to a **Relational SQL Database**.



**Why this matters:**
* **Instant Retrieval:** Replaced manual Binary Search with **B-Tree SQL Indexing**. Finding a user is now $O(\log n)$ at the hardware level.
* **Data Integrity:** Primary Key constraints prevent duplicate `coustomer_id` entries automatically.
* **Persistence:** Your library data survives server restarts and crashes.
* **Scalability:** Optimized to handle 100,000+ records without slowing down the RAM.

---

## 🌟 Key Features

* 🔍 **Google Books Integration:** Instant metadata fetching (Title, Author, Genre) via ISBN.
* 🛡️ **Smart Deletion Safety:** Users with unreturned books are protected from accidental deletion.
* ⚡ **Hash Map Catalog:** Books are stored in an $O(1)$ Hash Map for the fastest possible UI response.
* 🎨 **Aero UI:** A clean, responsive desktop webpage interface built with Streamlit.

---

## 📂 Project Architecture

### **The Database Schema**
Our SQL core is designed for efficiency:

```sql
CREATE TABLE customers (
    coustomer_id INT PRIMARY KEY,   -- Indexed unique identifier
    name VARCHAR(50) NOT NULL,
    email_id VARCHAR(100),
    mobile_number BIGINT
);