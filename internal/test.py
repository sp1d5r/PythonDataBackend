# db_test.py
import os
import sys
import time
import psycopg2


def test_connection():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    print("Attempting to connect to database...")

    # Try to connect a few times in case of network delays
    for i in range(5):
        try:
            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()
            cursor.execute('SELECT version()')
            version = cursor.fetchone()
            print(f"Successfully connected to database!")
            print(f"PostgreSQL version: {version[0]}")
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"Attempt {i + 1} failed: {str(e)}")
            if i < 4:  # Don't sleep on the last attempt
                time.sleep(5)

    print("Failed to connect to database after 5 attempts")
    sys.exit(1)


if __name__ == "__main__":
    test_connection()