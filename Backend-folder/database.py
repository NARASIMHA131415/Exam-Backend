import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self):
        self.host = os.getenv('DB_HOST')
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.database = os.getenv('DB_NAME')
        self.port = int(os.getenv('DB_PORT', 3306))

    def get_connection(self):
        try:
            connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port
            )
            return connection
        except Error as e:
            print("========== DATABASE ERROR ==========")
            print(f"Host: {self.host}")
            print(f"User: {self.user}")
            print(f"Database: {self.database}")
            print(f"Port: {self.port}")
            print(f"MySQL Error: {e}")
            print("===================================")
            return None
            return None

db = Database()
