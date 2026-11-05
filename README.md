# Inventory and Stock Analysis System

A web-based inventory management application developed using **Python, Flask, MySQL, HTML, CSS, and JavaScript**.

## Project Overview

The Inventory and Stock Analysis System helps manage products, suppliers, stock movements, and inventory information through a centralized web interface.

It provides inventory summaries, low-stock alerts, transaction history, and CSV export functionality.

## Features

- **Product Management:** Add, view, search, update, and delete products.
- **Supplier Management:** Maintain supplier information.
- **Stock IN:** Record received stock.
- **Stock OUT:** Record issued stock.
- **Transaction History:** Track stock movements.
- **Low-Stock Alerts:** Identify products at or below reorder level.
- **Dashboard Analysis:** View inventory summaries and charts.
- **CSV Reports:** Export inventory and transaction records.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, Flask |
| Frontend | HTML, CSS, JavaScript |
| Database | MySQL |
| Database Connector | mysql.connector |
| Data Analysis | Pandas |
| Visualization | Chart.js |

## Project Structure

```text
Inventory_Stock_Analysis/
│
├── app.py
├── templates/
│   └── index.html
├── requirements.txt
├── .gitignore
├── .env.example
└── README.md
```

## Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/yaswanthmarpu-offl/Inventory-and-Stock-Analysis-System.git
```

### 2. Navigate to the Project Folder

```bash
cd Inventory-and-Stock-Analysis-System
```

### 3. Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables

Create a `.env` file in the project root using `.env.example` as a reference.

Add your own MySQL connection details:

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=inventory_db
```

### 6. Configure MySQL

Install and start MySQL. Create the `inventory_db` database and configure the required tables before running the application.

The database must contain the tables and columns expected by the application.

### 7. Run the Application

```bash
python app.py
```

Open your browser:

```text
http://127.0.0.1:5000/
```

## Team Members

| Roll Number | Name |
|---|---|
| 25102A030085 | Yaswanth Marpu |
| 25102A030102 | Lakkireddy Vinay Kumar Reddy |
| 25102A030103 | Kattubadi Amrutha |
| 25102A030104 | Abbu Jaher Ali |

## Department

**Department of Data Science**  
Mohan Babu University  
Academic Year: 2026–2027

## Future Enhancements

- User authentication and role-based access.
- Cloud deployment.
- Barcode and QR-code scanning.
- Purchase-order management.
- PDF report generation.
- Automated low-stock notifications.

---

**Project:** Inventory and Stock Analysis System  
**Developed as an academic project at Mohan Babu University.**