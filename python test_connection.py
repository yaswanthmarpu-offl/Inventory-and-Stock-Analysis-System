import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

try:
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "inventory_db")
    )

    if connection.is_connected():
        print("MySQL connected successfully!")
        print("Database:", connection.database)

    connection.close()

except mysql.connector.Error as error:
    print("Connection failed:", error)