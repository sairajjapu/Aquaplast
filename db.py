import sqlite3
from werkzeug.security import generate_password_hash
import os
from datetime import datetime

# Database path
DB_PATH = "database.db"

# Remove existing database if you want a fresh start
if os.path.exists(DB_PATH):
    print(f"Removing existing database: {DB_PATH}")
    os.remove(DB_PATH)

# Connect to database
db = sqlite3.connect(DB_PATH)
cur = db.cursor()

print("=" * 60)
print("CREATING DATABASE TABLES FOR AQUAPLAST")
print("=" * 60)

# ============================================
# 1. CREATE USERS TABLE (with password reset fields)
# ============================================
print("\n📋 Creating users table...")
cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'analyst',
    status TEXT NOT NULL DEFAULT 'pending',
    reset_token TEXT,
    reset_expiry TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
print("✓ Users table created with password reset fields")

# ============================================
# 2. CREATE ANALYSIS TABLE (with all required fields)
# ============================================
print("\n📋 Creating analysis table...")
cur.execute("""
CREATE TABLE IF NOT EXISTS analysis(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT NOT NULL,
    analysis_mode TEXT DEFAULT 'both',
    tds REAL,
    water_source TEXT,
    collection_date TEXT,
    collection_time TEXT,
    notes TEXT,
    conditions TEXT,
    detected TEXT,
    confidence REAL,
    plastic_type TEXT,
    ph REAL,
    temperature REAL,
    turbidity REAL,
    contaminants TEXT,
    usage TEXT,
    uploaded_images TEXT,
    result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
print("✓ Analysis table created with all fields")

# ============================================
# 3. CREATE SENSOR READINGS TABLE (for ESP32 data)
# ============================================
print("\n📋 Creating sensor_readings table...")
cur.execute("""
CREATE TABLE IF NOT EXISTS sensor_readings(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tds REAL,
    ph REAL,
    turbidity REAL,
    temperature REAL,
    device_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
print("✓ Sensor readings table created")

# ============================================
# 4. CREATE REPORTS TABLE
# ============================================
print("\n📋 Creating reports table...")
cur.execute("""
CREATE TABLE IF NOT EXISTS reports(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER,
    user TEXT,
    report_name TEXT,
    report_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (analysis_id) REFERENCES analysis(id)
)
""")
print("✓ Reports table created")

# ============================================
# 5. CREATE SENSORS TABLE (for device management)
# ============================================
print("\n📋 Creating sensors table...")
cur.execute("""
CREATE TABLE IF NOT EXISTS sensors(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    device_id TEXT UNIQUE,
    status TEXT DEFAULT 'inactive',
    last_reading TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
print("✓ Sensors table created")

# ============================================
# INSERT DEFAULT USERS
# ============================================
print("\n👤 Inserting default users...")

# Clear existing users
cur.execute("DELETE FROM users")
print("✓ Cleared existing users")

# Hash passwords
admin_password = generate_password_hash('admin123')
researcher_password = generate_password_hash('researcher123')
analyst_password = generate_password_hash('analyst123')

# Insert default users
users_data = [
    ('Admin', 'admin@aquaplast.com', admin_password, 'admin', 'active', None, None),
    ('Researcher', 'researcher@aquaplast.com', researcher_password, 'researcher', 'active', None, None),
    ('Analyst', 'analyst@aquaplast.com', analyst_password, 'analyst', 'active', None, None)
]

for user in users_data:
    try:
        cur.execute("""
        INSERT INTO users (name, email, password, role, status, reset_token, reset_expiry)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, user)
        print(f"  ✓ Created user: {user[1]} ({user[3]})")
    except sqlite3.IntegrityError:
        print(f"  ⚠ User {user[1]} already exists")

# ============================================
# INSERT SAMPLE SENSOR DEVICES (Optional - for testing)
# ============================================
print("\n📊 Inserting sample sensor devices (for testing)...")

sample_sensors = [
    ('ESP32_Kitchen', 'ESP32_001', 'active', 'No data yet'),
    ('ESP32_Lab', 'ESP32_002', 'active', 'No data yet'),
]

for sensor in sample_sensors:
    try:
        cur.execute("""
        INSERT INTO sensors (name, device_id, status, last_reading)
        VALUES (?, ?, ?, ?)
        """, sensor)
        print(f"  ✓ Added sensor: {sensor[0]}")
    except sqlite3.IntegrityError:
        print(f"  ⚠ Sensor {sensor[0]} already exists")

# ============================================
# VERIFY TABLE STRUCTURES
# ============================================
print("\n📋 Verifying table structures...")

# Check users table
cur.execute("PRAGMA table_info(users)")
users_columns = cur.fetchall()
print(f"\n✓ users table has {len(users_columns)} columns:")
for col in users_columns:
    print(f"    - {col[1]} ({col[2]})")

# Check analysis table
cur.execute("PRAGMA table_info(analysis)")
analysis_columns = cur.fetchall()
print(f"\n✓ analysis table has {len(analysis_columns)} columns:")
for col in analysis_columns:
    print(f"    - {col[1]} ({col[2]})")

# Check sensor_readings table
cur.execute("PRAGMA table_info(sensor_readings)")
sensor_columns = cur.fetchall()
print(f"\n✓ sensor_readings table has {len(sensor_columns)} columns:")
for col in sensor_columns:
    print(f"    - {col[1]} ({col[2]})")

# Check reports table
cur.execute("PRAGMA table_info(reports)")
reports_columns = cur.fetchall()
print(f"\n✓ reports table has {len(reports_columns)} columns:")
for col in reports_columns:
    print(f"    - {col[1]} ({col[2]})")

# ============================================
# GET RECORD COUNTS
# ============================================
print("\n📊 Database Statistics:")
print("-" * 40)

cur.execute("SELECT COUNT(*) FROM users")
users_count = cur.fetchone()[0]
print(f"Total users: {users_count}")

cur.execute("SELECT COUNT(*) FROM analysis")
analysis_count = cur.fetchone()[0]
print(f"Total analysis records: {analysis_count} (will be populated by user activities)")

cur.execute("SELECT COUNT(*) FROM sensor_readings")
sensor_readings_count = cur.fetchone()[0]
print(f"Total sensor readings: {sensor_readings_count} (will be populated by ESP32 data)")

cur.execute("SELECT COUNT(*) FROM sensors")
sensors_count = cur.fetchone()[0]
print(f"Total sensors: {sensors_count}")

cur.execute("SELECT COUNT(*) FROM reports")
reports_count = cur.fetchone()[0]
print(f"Total reports: {reports_count} (will be populated when users generate reports)")

# ============================================
# COMMIT AND CLOSE
# ============================================
db.commit()
print("\n✅ Changes committed to database")
db.close()

# ============================================
# PRINT LOGIN CREDENTIALS
# ============================================
print("\n" + "=" * 60)
print("DATABASE INITIALIZED SUCCESSFULLY!")
print("=" * 60)
print("\n🔐 LOGIN CREDENTIALS:")
print("-" * 40)
print("Admin:")
print("  📧 Email: admin@aquaplast.com")
print("  🔑 Password: admin123")
print("  👤 Role: admin")
print()
print("Researcher:")
print("  📧 Email: researcher@aquaplast.com")
print("  🔑 Password: researcher123")
print("  👤 Role: researcher")
print()
print("Analyst:")
print("  📧 Email: analyst@aquaplast.com")
print("  🔑 Password: analyst123")
print("  👤 Role: analyst")
print("\n" + "=" * 60)
print("\n💡 TIP: You can now run your Flask app:")
print("   python app.py")
print("   Then visit: http://localhost:5000")
print("\n🔐 Password Reset:")
print("   - Click 'Forgot Password' on login page")
print("   - Enter your email to receive reset link")
print("   - Reset link expires in 1 hour")
print("\n📊 Data Population:")
print("   - Analysis records will be created when users perform analyses")
print("   - Sensor readings will be added automatically by ESP32")
print("   - Reports can be generated from analysis history")
print("=" * 60)