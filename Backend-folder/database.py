import mysql.connector
from mysql.connector import Error, pooling
import os
from dotenv import load_dotenv

load_dotenv()


class Database:
    def __init__(self):
        # FIX #5: Handle missing or empty env vars with clear errors
        self.host = os.getenv('DB_HOST')
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.database = os.getenv('DB_NAME')
        port_str = os.getenv('DB_PORT', '3306')
        self.port = int(port_str) if port_str else 3306

        # FIX #1: Validate required env vars at startup, not at request time
        missing = []
        if not self.host:
            missing.append('DB_HOST')
        if not self.user:
            missing.append('DB_USER')
        if not self.password:
            missing.append('DB_PASSWORD')
        if not self.database:
            missing.append('DB_NAME')

        if missing:
            print(f"⚠️  WARNING: Missing environment variables: {', '.join(missing)}")
            print("   The application will start but all database operations will fail.")

        # FIX #3: Connection pooling for better performance
        self._pool = None
        if not missing:
            try:
                self._pool = pooling.MySQLConnectionPool(
                    pool_name="exam_portal_pool",
                    pool_size=5,
                    pool_reset_session=True,
                    host=self.host,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    port=self.port,
                    connection_timeout=10,  # FIX #4: Don't hang forever
                    autocommit=False
                )
                print(f"✅ Database connection pool created ({self.host}:{self.port}/{self.database})")
            except Error as e:
                print(f"❌ Failed to create connection pool: {e}")
                self._pool = None

    def get_connection(self):
        # Try connection pool first
        if self._pool:
            try:
                connection = self._pool.get_connection()
                if connection.is_connected():
                    return connection
            except Error as e:
                print(f"⚠️  Pool connection failed, trying direct: {e}")

        # Fallback: direct connection (for when pool fails or isn't initialized)
        try:
            connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
                connection_timeout=10,
                autocommit=False
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
        # FIX #2: Removed unreachable second return None


db = Database()
