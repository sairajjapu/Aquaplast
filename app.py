import os
import json
import time
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Email configuration (update with your email settings)
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',  # For Gmail
    'smtp_port': 587,
    'sender_email': 'sairajjapu@gmail.com',  # Replace with your email
    'sender_password': 'vuaa uewm bagh toxv',  # Use app-specific password
    'use_tls': True
}

# ============================================
# TRY TO IMPORT TENSORFLOW (OPTIONAL)
# ============================================
TENSORFLOW_AVAILABLE = False
model = None

try:
    import tensorflow as tf
    import numpy as np
    from PIL import Image
    TENSORFLOW_AVAILABLE = True
    print("✓ TensorFlow imported successfully")
except ImportError as e:
    print(f"⚠ TensorFlow not installed: {e}")
    print("⚠ Running in fallback mode - CNN detection disabled")
except Exception as e:
    print(f"⚠ Error importing TensorFlow: {e}")
    print("⚠ Running in fallback mode - CNN detection disabled")

app = Flask(__name__)

# Model parameters (for both TensorFlow and fallback)
IMG_HEIGHT = 224
IMG_WIDTH = 224
CLASS_NAMES = ['clean', 'microplastics']

# Try to load the model if TensorFlow is available
if TENSORFLOW_AVAILABLE:
    MODEL_PATH = 'models/microplastic_final_model.h5'
    try:
        if os.path.exists(MODEL_PATH):
            model = tf.keras.models.load_model(MODEL_PATH)
            print(f"✓ CNN Model loaded successfully from {MODEL_PATH}")
        else:
            print(f"⚠ Model file not found at {MODEL_PATH}")
            print("⚠ Using fallback logic")
    except Exception as e:
        print(f"⚠ Could not load model: {e}")
        print("⚠ Using fallback logic")
else:
    print("⚠ TensorFlow not available - using fallback logic")

# ============================================
# FALLBACK PREDICTION FUNCTION
# ============================================
def predict_microplastic_fallback(image_path):
    """Fallback prediction when CNN is not available"""
    try:
        from PIL import Image
        import numpy as np
        
        img = Image.open(image_path)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        img = img.resize((IMG_HEIGHT, IMG_WIDTH))
        img_array = np.array(img)
        
        # Simple simulation based on image properties
        brightness = np.mean(img_array)
        
        # Simulate detection based on brightness (just for demo)
        if brightness < 100:
            detected = "Yes"
            confidence = 85.0
            plastic_type = "Microplastic detected (analysis in progress)"
            contaminants = "Possible contamination detected"
            usage = "Further testing recommended"
        else:
            detected = "No"
            confidence = 92.0
            plastic_type = "No microplastic detected"
            contaminants = "No visible contamination"
            usage = "Safe for all purposes"
        
        return {
            'detected': detected,
            'confidence': confidence,
            'plastic_type': plastic_type,
            'contaminants': contaminants,
            'usage': usage,
            'raw_score': confidence / 100
        }
        
    except Exception as e:
        print(f"Fallback prediction error: {e}")
        return {
            'detected': 'No',
            'confidence': 50.0,
            'plastic_type': 'Analysis failed',
            'contaminants': str(e),
            'usage': 'Please try again'
        }

# ============================================
# TENSORFLOW PREDICTION FUNCTION
# ============================================
def predict_microplastic_tf(image_path):
    """TensorFlow-based prediction"""
    if model is None:
        return predict_microplastic_fallback(image_path)
    
    try:
        from PIL import Image
        import numpy as np
        
        img = Image.open(image_path)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        img = img.resize((IMG_HEIGHT, IMG_WIDTH))
        img_array = np.array(img) / 255.0
        img_array = np.expand_dims(img_array, axis=0)
        
        prediction = model.predict(img_array, verbose=0)
        confidence_score = float(prediction[0][0])
        
        if confidence_score > 0.5:
            return {
                'detected': 'Yes',
                'confidence': confidence_score * 100,
                'plastic_type': 'Microplastic detected',
                'contaminants': 'Microplastic contamination detected',
                'usage': 'Not safe for consumption - Treatment required'
            }
        else:
            return {
                'detected': 'No',
                'confidence': (1 - confidence_score) * 100,
                'plastic_type': 'No microplastic detected',
                'contaminants': 'No visible contamination',
                'usage': 'Safe for all purposes'
            }
            
    except Exception as e:
        print(f"TF Prediction error: {e}")
        return predict_microplastic_fallback(image_path)

# ============================================
# SELECT THE APPROPRIATE PREDICTION FUNCTION
# ============================================
if TENSORFLOW_AVAILABLE and model is not None:
    predict_microplastic = predict_microplastic_tf
    print("✓ Using TensorFlow CNN model for detection")
else:
    predict_microplastic = predict_microplastic_fallback
    print("⚠ Using fallback detection logic")

# ============================================
# FLASK APP CONFIGURATION
# ============================================
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'aquaplast_secret_change_in_production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ============================================
# DATABASE CONFIGURATION
# ============================================
DB = "database.db"

# Global variable to store latest sensor data
latest_sensor_data = {
    "tds": 0,
    "ph": 0,
    "turbidity": 0,
    "temperature": 0,
    "last_update": None,
    "device_id": None
}

# ============================================
# DATABASE CONNECTION FUNCTION
# ============================================
def get_db():
    try:
        db = sqlite3.connect(DB)
        db.row_factory = sqlite3.Row
        return db
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        return None

# ============================================
# LOGIN REQUIRED DECORATOR
# ============================================
def login_required(roles=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user" not in session:
                flash("Please login to continue", "warning")
                return redirect(url_for("index"))

            if roles and session.get("role") not in roles:
                flash("Unauthorized access. You don't have permission to view this page.", "error")
                return redirect(url_for("index"))

            return f(*args, **kwargs)
        return wrapped
    return decorator

# ============================================
# PREDICTION FUNCTIONS
# ============================================
def predict_microplastic(image_path):
    """
    Predict if an image contains microplastics using trained CNN model
    Returns: dict with detection results
    """
    if model is None:
        return {
            'detected': 'No',
            'confidence': 50.0,
            'plastic_type': 'Model not loaded',
            'contaminants': 'Unable to analyze',
            'usage': 'Please check model file'
        }
    
    try:
        from PIL import Image
        import numpy as np
        
        img = Image.open(image_path)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        img = img.resize((IMG_HEIGHT, IMG_WIDTH))
        img_array = np.array(img) / 255.0
        img_array = np.expand_dims(img_array, axis=0)
        
        prediction = model.predict(img_array, verbose=0)
        confidence_score = float(prediction[0][0])
        
        if confidence_score > 0.5:
            detected = "Yes"
            confidence = confidence_score * 100
            plastic_type = "Microplastic detected"
            contaminants = "Microplastic contamination detected"
            usage = "Not safe for consumption - Treatment required"
        else:
            detected = "No"
            confidence = (1 - confidence_score) * 100
            plastic_type = "No microplastic detected"
            contaminants = "No visible contamination"
            usage = "Safe for all purposes"
        
        return {
            'detected': detected,
            'confidence': confidence,
            'plastic_type': plastic_type,
            'contaminants': contaminants,
            'usage': usage,
            'raw_score': confidence_score
        }
        
    except Exception as e:
        print(f"Prediction error: {e}")
        return {
            'detected': 'Error',
            'confidence': 0,
            'plastic_type': 'Analysis failed',
            'contaminants': str(e),
            'usage': 'Please try again'
        }

def predict_multiple_images(image_paths):
    """Predict on multiple images and return aggregated results"""
    results = []
    for path in image_paths:
        result = predict_microplastic(path)
        results.append(result)
    
    if results:
        has_microplastic = any(r['detected'] == 'Yes' for r in results)
        microplastic_confidences = [r['confidence'] for r in results if r['detected'] == 'Yes']
        clean_confidences = [r['confidence'] for r in results if r['detected'] == 'No']
        
        if has_microplastic:
            best_confidence = max(microplastic_confidences) if microplastic_confidences else 0
            return {
                'detected': 'Yes',
                'confidence': best_confidence,
                'plastic_type': 'Microplastic detected in sample',
                'contaminants': 'Microplastic contamination found in one or more images',
                'usage': 'Not safe for consumption - Treatment required'
            }
        else:
            best_confidence = max(clean_confidences) if clean_confidences else 100
            return {
                'detected': 'No',
                'confidence': best_confidence,
                'plastic_type': 'No microplastic detected',
                'contaminants': 'No visible contamination in sample',
                'usage': 'Safe for all purposes'
            }
    
    return {
        'detected': 'No',
        'confidence': 0,
        'plastic_type': 'No images analyzed',
        'contaminants': 'No data',
        'usage': 'Unable to analyze'
    }

# ============================================
# ROUTES
# ============================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/user_manual")
def user_manual():
    return render_template("user_manual.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required", "error")
            return redirect(url_for("index"))

        try:
            db = get_db()
            if not db:
                flash("Database connection error", "error")
                return redirect(url_for("index"))
            
            cur = db.cursor()
            cur.execute(
                "SELECT id, name, email, password, role, status FROM users WHERE email=?",
                (email,)
            )
            user = cur.fetchone()
            db.close()

            if not user:
                flash("Account not found. Please request access if you don't have an account.", "error")
            elif user['status'] == "pending":
                flash("Your account is pending admin approval. You'll be notified once approved.", "warning")
            elif user['status'] == "inactive":
                flash("Your account has been deactivated. Please contact administrator.", "error")
            elif not check_password_hash(user['password'], password):
                flash("Incorrect password. Please try again.", "error")
            else:
                session.permanent = True
                session["user"] = user['name']
                session["user_id"] = user['id']
                session["role"] = user['role']
                session["email"] = user['email']

                flash(f"Welcome back, {user['name']}!", "success")

                if user['role'] == "admin":
                    return redirect(url_for("admin_dashboard"))
                else:
                    return redirect(url_for("detect"))

        except sqlite3.Error as e:
            flash(f"Database error: {str(e)}", "error")
            return redirect(url_for("index"))

    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been successfully logged out.", "success")
    return redirect("/")


def send_reset_email(to_email, reset_link):
    """Send password reset email"""
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "AquaPlast - Password Reset Request"
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = to_email
        
        # Create HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .header {{
                    background: linear-gradient(135deg, #0077b6, #00b4d8);
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 10px 10px 0 0;
                }}
                .content {{
                    background: white;
                    padding: 30px;
                    border-radius: 0 0 10px 10px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background: #0077b6;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px;
                    font-size: 12px;
                    color: #777;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🔐 AquaPlast Password Reset</h2>
                </div>
                <div class="content">
                    <p>Hello,</p>
                    <p>We received a request to reset your password for your AquaPlast account.</p>
                    <p>Click the button below to reset your password:</p>
                    <div style="text-align: center;">
                        <a href="{reset_link}" class="button">Reset Password</a>
                    </div>
                    <p>Or copy and paste this link in your browser:</p>
                    <p style="word-break: break-all; background: #f0f0f0; padding: 10px; border-radius: 5px;">
                        {reset_link}
                    </p>
                    <p>This link will expire in 1 hour.</p>
                    <p>If you didn't request a password reset, please ignore this email or contact support.</p>
                    <hr>
                    <p style="font-size: 12px; color: #777;">
                        This is an automated message, please do not reply to this email.
                    </p>
                </div>
                <div class="footer">
                    &copy; 2024 AquaPlast - Water Quality Analysis System
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create plain text version
        text_content = f"""
        AquaPlast - Password Reset Request
        
        Hello,
        
        We received a request to reset your password for your AquaPlast account.
        
        To reset your password, click the link below or copy it to your browser:
        {reset_link}
        
        This link will expire in 1 hour.
        
        If you didn't request a password reset, please ignore this email.
        
        ---
        AquaPlast Water Quality Analysis System
        """
        
        # Attach both versions
        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        if EMAIL_CONFIG['use_tls']:
            server.starttls()
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Forgot password page"""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        
        if not email:
            flash("Please enter your email address", "error")
            return redirect(url_for("forgot_password"))
        
        try:
            db = get_db()
            if not db:
                flash("Database connection error", "error")
                return redirect(url_for("forgot_password"))
            
            cur = db.cursor()
            cur.execute("SELECT id, name FROM users WHERE email = ?", (email,))
            user = cur.fetchone()
            
            if user:
                # Generate reset token
                reset_token = secrets.token_urlsafe(32)
                reset_expiry = datetime.now() + timedelta(hours=1)
                
                # Save token to database
                cur.execute("""
                    UPDATE users 
                    SET reset_token = ?, reset_expiry = ?
                    WHERE id = ?
                """, (reset_token, reset_expiry, user['id']))
                db.commit()
                
                # Create reset link
                reset_link = url_for('reset_password', token=reset_token, _external=True)
                
                # Send email
                if send_reset_email(email, reset_link):
                    flash("Password reset link has been sent to your email. Please check your inbox.", "success")
                else:
                    # If email fails, show the link for testing
                    flash(f"Email sending failed. For testing, use this link: {reset_link}", "warning")
            else:
                # Don't reveal if email exists for security
                flash("If an account exists with that email, you will receive a password reset link.", "info")
            
            db.close()
            return redirect(url_for("login"))
            
        except Exception as e:
            print(f"Forgot password error: {e}")
            flash("An error occurred. Please try again.", "error")
            return redirect(url_for("forgot_password"))
    
    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Reset password page"""
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return redirect(url_for("login"))
        
        cur = db.cursor()
        
        # Find user with this token
        cur.execute("""
            SELECT id, name, email FROM users 
            WHERE reset_token = ? AND reset_expiry > datetime('now')
        """, (token,))
        
        user = cur.fetchone()
        
        if not user:
            flash("Invalid or expired password reset link. Please request a new one.", "error")
            db.close()
            return redirect(url_for("forgot_password"))
        
        if request.method == "POST":
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            
            if not password or not confirm_password:
                flash("Please fill in all fields", "error")
                return redirect(url_for("reset_password", token=token))
            
            if password != confirm_password:
                flash("Passwords do not match", "error")
                return redirect(url_for("reset_password", token=token))
            
            if len(password) < 6:
                flash("Password must be at least 6 characters long", "error")
                return redirect(url_for("reset_password", token=token))
            
            # Update password
            hashed_password = generate_password_hash(password)
            cur.execute("""
                UPDATE users 
                SET password = ?, reset_token = NULL, reset_expiry = NULL
                WHERE id = ?
            """, (hashed_password, user['id']))
            db.commit()
            db.close()
            
            flash("Your password has been reset successfully. Please login with your new password.", "success")
            return redirect(url_for("login"))
        
        db.close()
        return render_template("reset_password.html", token=token, email=user['email'])
        
    except Exception as e:
        print(f"Reset password error: {e}")
        flash("An error occurred. Please try again.", "error")
        return redirect(url_for("login"))

# ==============================================
# USER ACCOUNT REQUEST ROUTE
# =============================================
@app.route("/request-account", methods=["POST"])
def request_account():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("req_password", "")
    confirm_password = request.form.get("req_confirm_password", "")

    if not name or not email or not password:
        flash("All fields are required", "error")
        return redirect(url_for("index"))

    if password != confirm_password:
        flash("Passwords do not match", "error")
        return redirect(url_for("index"))

    if len(password) < 6:
        flash("Password must be at least 6 characters long", "error")
        return redirect(url_for("index"))

    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return redirect(url_for("index"))

        cur = db.cursor()
        cur.execute("SELECT id FROM users WHERE email=?", (email,))
        if cur.fetchone():
            db.close()
            flash("Email already registered. Please use a different email or login.", "error")
            return redirect(url_for("index"))

        hashed_password = generate_password_hash(password)
        cur.execute("""
            INSERT INTO users (name, email, password, role, status)
            VALUES (?, ?, ?, 'analyst', 'pending')
        """, (name, email, hashed_password))

        db.commit()
        db.close()
        flash("Account request submitted successfully. Await admin approval. You'll be notified once approved.", "success")

    except sqlite3.IntegrityError:
        flash("Email already registered", "error")
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
    finally:
        if 'db' in locals() and db:
            db.close()

    return redirect(url_for("index"))

@app.route("/detect", methods=["GET"])
@login_required(roles=["researcher", "analyst", "admin"])
def detect():
    now = datetime.now()
    return render_template(
        "detect.html", 
        user_name=session.get("user"),
        user_role=session.get("role"),
        current_date=now.strftime('%Y-%m-%d'),
        current_time=now.strftime('%H:%M')
    )

@app.route("/detect", methods=["POST"])
@login_required(roles=["researcher", "analyst", "admin"])
def handle_detection():
    """Handle the form submission with CNN model prediction"""
    try:
        print("\n🔍 Starting detection process...")
        analysis_mode = request.form.get("analysis_mode", "both")
        
        tds_value = request.form.get("tds", "").strip()
        turbidity_value = request.form.get("turbidity", "").strip()
        temperature_value = request.form.get("temperature", "").strip()
        ph_value = request.form.get("ph", "").strip()
        
        # Optional data fields
        water_source = request.form.get("water_source", "")
        collection_date = request.form.get("collection_date", "")
        collection_time = request.form.get("collection_time", "")
        notes = request.form.get("notes", "")
        
        conditions = []
        if request.form.get("condition_turbid"):
            conditions.append("turbid")
        if request.form.get("condition_clear"):
            conditions.append("clear")
        if request.form.get("condition_odorous"):
            conditions.append("odorous")
        if request.form.get("condition_colored"):
            conditions.append("colored")
        
        conditions_str = ", ".join(conditions) if conditions else "Not specified"
        
        # Handle file uploads
        uploaded_files = request.files.getlist("images")
        
        # Mode-specific validation
        if analysis_mode == "image_only":
            if not uploaded_files or uploaded_files[0].filename == '':
                flash("Please upload at least one image for analysis", "error")
                return redirect(url_for("detect"))
            tds_value = tds_value or "0"
            turbidity_value = turbidity_value or "0"
            temperature_value = temperature_value or "25"
            ph_value = ph_value or "7.0"

        elif analysis_mode == "sensor_only":
            if not tds_value or not ph_value or not turbidity_value or not temperature_value:
                flash("All sensor values (TDS, pH, Turbidity, Temperature) are required", "error")
                return redirect(url_for("detect"))
            uploaded_files = []
            
        else:  # both mode
            if not uploaded_files or uploaded_files[0].filename == '':
                flash("Please upload at least one image for analysis", "error")
                return redirect(url_for("detect"))
            if not tds_value or not ph_value or not turbidity_value or not temperature_value:
                flash("All sensor values (TDS, pH, Turbidity, Temperature) are required", "error")
                return redirect(url_for("detect"))
        
        # Convert to float
        try:
            tds_float = float(tds_value) if tds_value else 0
            ph_float = float(ph_value) if ph_value else 7
            turbidity_float = float(turbidity_value) if turbidity_value else 0
            temperature_float = float(temperature_value) if temperature_value else 25
        except ValueError:
            flash("Invalid numeric values provided", "error")
            return redirect(url_for("detect"))
        
        # Save uploaded files and get predictions from CNN
        uploaded_images_list = []
        image_paths = []
        cnn_results = None
        
        if uploaded_files:
            for file in uploaded_files:
                if file and file.filename:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = secure_filename(f"{timestamp}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    uploaded_images_list.append(filename)
                    image_paths.append(filepath)
            
            cnn_results = predict_multiple_images(image_paths)
        
        # Prepare results dictionary
        results_data = {
            'analysis_mode': analysis_mode,
            'user_name': session.get('user'),
            'user_role': session.get('role'),
            'water_source': water_source,
            'collection_date': collection_date,
            'collection_time': collection_time,
            'notes': notes,
            'conditions': conditions_str,
            'tds': tds_float,
            'ph': ph_float,
            'turbidity': turbidity_float,
            'temperature': temperature_float,
            'uploaded_images': uploaded_images_list,
            'uploaded_images_str': ", ".join(uploaded_images_list) if uploaded_images_list else ""
        }
        
        # Determine final results based on mode
        if analysis_mode == "image_only":
            if cnn_results:
                results_data.update({
                    'detected': cnn_results['detected'],
                    'confidence': cnn_results['confidence'],
                    'plastic_type': cnn_results['plastic_type'],
                    'contaminants': cnn_results['contaminants'],
                    'usage': cnn_results['usage']
                })
            else:
                flash("Error analyzing images", "error")
                return redirect(url_for("detect"))
                
        elif analysis_mode == "sensor_only":
            if tds_float > 300 or ph_float < 6.5 or ph_float > 8.5 or turbidity_float > 5:
                results_data.update({
                    'detected': 'Yes',
                    'confidence': 85.0,
                    'plastic_type': 'Microplastics likely present based on water quality',
                    'contaminants': 'High TDS and turbidity indicate possible contamination',
                    'usage': 'Not safe for drinking - Treatment required'
                })
            else:
                results_data.update({
                    'detected': 'No',
                    'confidence': 96.0,
                    'plastic_type': 'No microplastics indicated by sensor data',
                    'contaminants': 'Water quality parameters within normal range',
                    'usage': 'Safe for all purposes based on sensor data'
                })
                
        else:  # both mode
            sensor_detected = (tds_float > 300 or ph_float < 6.5 or ph_float > 8.5 or turbidity_float > 5)
            cnn_detected = cnn_results['detected'] == 'Yes' if cnn_results else False
            
            if cnn_detected or sensor_detected:
                confidence = 0
                if cnn_results:
                    confidence += cnn_results['confidence'] * 0.6
                if sensor_detected:
                    confidence += 85 * 0.4
                confidence = min(confidence, 99)
                
                results_data.update({
                    'detected': 'Yes',
                    'confidence': confidence,
                    'plastic_type': 'Microplastic contamination detected',
                    'contaminants': 'Multiple indicators suggest contamination',
                    'usage': 'Not safe for consumption - Treatment required'
                })
            else:
                results_data.update({
                    'detected': 'No',
                    'confidence': cnn_results['confidence'] if cnn_results else 97.0,
                    'plastic_type': 'No contamination detected',
                    'contaminants': 'Clean water sample',
                    'usage': 'Safe for all purposes'
                })
        
        # Store the results in session
        session['temp_results'] = results_data
        
        flash(f"Analysis completed successfully! Mode: {analysis_mode}", "success")
        return redirect(url_for("show_results"))
            
    except Exception as e:
        print(f"Error in detection: {e}")
        flash(f"Error processing request: {str(e)}", "error")
        return redirect(url_for("detect"))

@app.route("/show-results")
@login_required(roles=["researcher", "analyst", "admin"])
def show_results():
    """Display analysis results directly from session"""
    try:
        results_data = session.pop('temp_results', None)
        
        if not results_data:
            flash("No analysis results found. Please perform a new analysis.", "warning")
            return redirect(url_for("detect"))
        
        # Save results to database
        try:
            db = get_db()
            if db:
                cur = db.cursor()
                cur.execute("""
                    INSERT INTO analysis 
                    (user, analysis_mode, tds, water_source, collection_date, collection_time, notes, 
                     conditions, detected, confidence, plastic_type, ph, turbidity, 
                     temperature, contaminants, usage, uploaded_images, result, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    session.get("user"),
                    results_data.get('analysis_mode', 'both'),
                    results_data.get('tds', 0),
                    results_data.get('water_source', ''),
                    results_data.get('collection_date', ''),
                    results_data.get('collection_time', ''),
                    results_data.get('notes', ''),
                    results_data.get('conditions', 'Not specified'),
                    results_data.get('detected', 'No'),
                    results_data.get('confidence', 95),
                    results_data.get('plastic_type', 'None detected'),
                    results_data.get('ph', 7.2),
                    results_data.get('turbidity', 2.5),
                    results_data.get('temperature', 25.0),
                    results_data.get('contaminants', 'None'),
                    results_data.get('usage', 'Safe for all purposes'),
                    results_data.get('uploaded_images_str', ''),
                    "Completed"
                ))
                db.commit()
                db.close()
        except sqlite3.Error as e:
            print(f"Database error while saving: {e}")
        
        # Prepare data for template
        template_data = {
            'detected': results_data.get('detected', 'No'),
            'confidence': float(results_data.get('confidence', 95)),
            'plastic_type': results_data.get('plastic_type', 'None detected'),
            'contaminants': results_data.get('contaminants', 'None'),
            'usage': results_data.get('usage', 'Safe for all purposes'),
            'tds': float(results_data.get('tds', 250)),
            'ph': float(results_data.get('ph', 7.2)),
            'turbidity': float(results_data.get('turbidity', 2.5)),
            'temperature': float(results_data.get('temperature', 25.0)),
            'water_source': results_data.get('water_source', ''),
            'collection_date': results_data.get('collection_date', ''),
            'collection_time': results_data.get('collection_time', ''),
            'notes': results_data.get('notes', ''),
            'conditions': results_data.get('conditions', ''),
            'uploaded_images': results_data.get('uploaded_images_str', ''),
            'user_name': results_data.get('user_name', session.get('user')),
            'user_role': results_data.get('user_role', session.get('role')),
            'analysis_mode': results_data.get('analysis_mode', 'both'),
            'analysis_date': datetime.now().strftime('%B %d, %Y'),
            'analysis_time': datetime.now().strftime('%I:%M %p')
        }
        
        return render_template("results.html", **template_data)
        
    except Exception as e:
        print(f"Error showing results: {e}")
        flash(f"Error displaying results: {str(e)}", "error")
        return redirect(url_for("detect"))

@app.route("/history")
@login_required(roles=["researcher", "analyst", "admin"])
def history():
    """Display user's analysis history"""
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return render_template("history.html", records=[])
        
        cur = db.cursor()
        
        # Get all analyses for the current user
        cur.execute("""
            SELECT id, analysis_mode, detected, confidence, tds, ph, turbidity, 
                   temperature, plastic_type, contaminants, usage, created_at,
                   uploaded_images, water_source
            FROM analysis 
            WHERE user = ? 
            ORDER BY id DESC
        """, (session.get("user"),))
        
        analyses = cur.fetchall()
        db.close()
        
        # Convert to list of dictionaries with the structure expected by history.html
        records = []
        for row in analyses:
            records.append({
                'id': row['id'],
                'image_name': row['uploaded_images'] or f"Analysis_{row['id']}",
                'tds': row['tds'],
                'microplastic_result': row['detected'],
                'confidence': row['confidence'],
                'location': row['water_source'] or 'Not specified',
                'analyzed_at': row['created_at'],
                'ph': row['ph'],
                'turbidity': row['turbidity'],
                'temperature': row['temperature'],
                'plastic_type': row['plastic_type'],
                'contaminants': row['contaminants'],
                'usage': row['usage'],
                'detected': row['detected'],
                'uploaded_images': row['uploaded_images'],
                'water_source': row['water_source'],
                'created_at': row['created_at']
            })
        
        return render_template("history.html", records=records)
        
    except Exception as e:
        print(f"Error loading history: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error loading history: {str(e)}", "error")
        return render_template("history.html", records=[])

@app.route("/profile")
@login_required(roles=["researcher", "analyst", "admin"])
def profile():
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return redirect(url_for("detect"))
        
        cur = db.cursor()
        cur.execute(
            "SELECT name, email, role, status FROM users WHERE id=?",
            (session["user_id"],)
        )
        user_data = cur.fetchone()
        
        if not user_data:
            flash("User not found", "error")
            return redirect(url_for("logout"))
        
        # Get analysis count
        cur.execute(
            "SELECT COUNT(*) FROM analysis WHERE user=?",
            (session.get("user"),)
        )
        analysis_count = cur.fetchone()[0]
        db.close()
        
        stats = {"analysis_count": analysis_count or 0}
        
        return render_template("profile.html", user=user_data, stats=stats)
        
    except Exception as e:
        flash(f"Error loading profile: {str(e)}", "error")
        return redirect(url_for("detect"))

@app.route('/edit-profile', methods=['POST'])
@login_required()
def edit_profile():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not name or not email:
        flash("Name and email are required", "error")
        return redirect(url_for('profile'))

    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return redirect(url_for('profile'))

        cursor = db.cursor()

        if new_password:
            cursor.execute("SELECT password FROM users WHERE id=?", (session['user_id'],))
            result = cursor.fetchone()
            
            if not result or not check_password_hash(result[0], current_password):
                db.close()
                flash("Current password is incorrect", "error")
                return redirect(url_for('profile'))

            if new_password != confirm_password:
                db.close()
                flash("New passwords do not match", "error")
                return redirect(url_for('profile'))

            if len(new_password) < 6:
                db.close()
                flash("New password must be at least 6 characters long", "error")
                return redirect(url_for('profile'))

            hashed = generate_password_hash(new_password)
            cursor.execute("""
                UPDATE users SET name=?, email=?, password=?
                WHERE id=?
            """, (name, email, hashed, session['user_id']))
            
            flash("Profile and password updated successfully", "success")
        else:
            cursor.execute("""
                UPDATE users SET name=?, email=?
                WHERE id=?
            """, (name, email, session['user_id']))
            
            flash("Profile updated successfully", "success")

        db.commit()
        session['user'] = name
        session['email'] = email

    except sqlite3.IntegrityError:
        flash("Email already in use by another account", "error")
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
    finally:
        if db:
            db.close()

    return redirect(url_for('profile'))

# ============================================
# SENSOR API ROUTES
# ============================================

@app.route("/api/sensor-data", methods=["POST"])
def receive_sensor_data():
    global latest_sensor_data
    
    if request.is_json:
        data = request.get_json()
        api_key = data.get('api_key')
    else:
        data = request.form
        api_key = data.get('api_key')
    
    if api_key != "AquaPlast_ESP32_2026":
        return jsonify({"error": "Unauthorized - Invalid API key"}), 401
    
    try:
        tds = float(data.get('tds', 0))
        ph = float(data.get('ph', 0))
        turbidity = float(data.get('turbidity', 0))
        temperature = float(data.get('temperature', 0))
        device_id = data.get('device_id', 'unknown')
        
        if ph < 0 or ph > 14:
            return jsonify({"error": "Invalid pH value (0-14)"}), 400
        
        if tds < 0 or tds > 5000:
            return jsonify({"error": "Invalid TDS value (0-5000 ppm)"}), 400
        
        if turbidity < 0 or turbidity > 100:
            return jsonify({"error": "Invalid turbidity value (0-100 NTU)"}), 400
        
        if temperature < -10 or temperature > 100:
            return jsonify({"error": "Invalid temperature value (-10 to 100°C)"}), 400
        
        latest_sensor_data = {
            "tds": tds,
            "ph": ph,
            "turbidity": turbidity,
            "temperature": temperature,
            "last_update": datetime.now().isoformat(),
            "device_id": device_id
        }
        
        # Store in database
        try:
            db = get_db()
            if db:
                cur = db.cursor()
                cur.execute("""
                    INSERT INTO sensor_readings 
                    (tds, ph, turbidity, temperature, device_id, created_at) 
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                """, (tds, ph, turbidity, temperature, device_id))
                db.commit()
                db.close()
                print(f"✓ Sensor data stored: TDS={tds}, pH={ph}, Turbidity={turbidity}, Temp={temperature}")
        except Exception as e:
            print(f"Database storage error: {e}")
        
        return jsonify({
            "status": "success",
            "message": "Data received successfully",
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except ValueError as e:
        return jsonify({"error": f"Invalid numeric value: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/sensor-stream")
def sensor_stream():
    """Server-Sent Events for real-time sensor updates"""
    def generate():
        last_update = None
        while True:
            global latest_sensor_data
            if latest_sensor_data["last_update"] != last_update:
                last_update = latest_sensor_data["last_update"]
                if last_update:
                    data = {
                        "tds": latest_sensor_data["tds"],
                        "ph": latest_sensor_data["ph"],
                        "turbidity": latest_sensor_data["turbidity"],
                        "temperature": latest_sensor_data["temperature"],
                        "last_update": latest_sensor_data["last_update"],
                        "device_id": latest_sensor_data["device_id"]
                    }
                    yield f"data: {json.dumps(data)}\n\n"
            time.sleep(1)
    
    return Response(generate(), mimetype="text/event-stream")

@app.route("/api/latest-sensor-data", methods=["GET"])
def get_latest_sensor_data():
    global latest_sensor_data
    
    if latest_sensor_data["last_update"]:
        try:
            last_update = datetime.fromisoformat(latest_sensor_data["last_update"])
            time_diff = (datetime.now() - last_update).total_seconds()
            
            return jsonify({
                **latest_sensor_data,
                "is_recent": time_diff < 30,
                "age_seconds": time_diff
            })
        except:
            return jsonify(latest_sensor_data)
    else:
        return jsonify({"error": "No data available", "connected": False}), 404

@app.route("/api/check-esp32-connection", methods=["GET"])
def check_esp32_connection():
    global latest_sensor_data
    
    if latest_sensor_data["last_update"]:
        try:
            last_update = datetime.fromisoformat(latest_sensor_data["last_update"])
            time_diff = (datetime.now() - last_update).total_seconds()
            
            if time_diff < 30:
                return jsonify({
                    "connected": True,
                    "device_id": latest_sensor_data["device_id"],
                    "last_seen": latest_sensor_data["last_update"],
                    "age_seconds": time_diff,
                    "tds": latest_sensor_data["tds"],
                    "ph": latest_sensor_data["ph"],
                    "turbidity": latest_sensor_data["turbidity"],
                    "temperature": latest_sensor_data["temperature"]
                })
        except:
            pass
    
    return jsonify({"connected": False, "message": "No recent data from ESP32"})

@app.route("/api/sensor-history", methods=["GET"])
def get_sensor_history():
    limit = request.args.get('limit', 100, type=int)
    
    try:
        db = get_db()
        if not db:
            return jsonify({"error": "Database connection error"}), 500
        
        cur = db.cursor()
        cur.execute("""
            SELECT * FROM sensor_readings 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        
        readings = cur.fetchall()
        db.close()
        
        readings_list = [dict(row) for row in readings]
        
        return jsonify({
            "status": "success",
            "count": len(readings_list),
            "readings": readings_list
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# ADMIN ROUTES
# ============================================

@app.route("/admin/dashboard")
@login_required(roles=["admin"])
def admin_dashboard():
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return render_template("admin_dashboard.html", stats={}, users=[], analyses=[], recent_users=[], recent_analyses=[], week_days=[])
        
        cur = db.cursor()

        today = datetime.now().date()
        week_ago = today - timedelta(days=7)

        stats = {
            "total_users": cur.execute("SELECT COUNT(*) FROM users").fetchone()[0] or 0,
            "active_users": cur.execute("SELECT COUNT(*) FROM users WHERE status='active'").fetchone()[0] or 0,
            "pending_requests": cur.execute("SELECT COUNT(*) FROM users WHERE status='pending'").fetchone()[0] or 0,
            "total_analyses": cur.execute("SELECT COUNT(*) FROM analysis").fetchone()[0] or 0,
            "total_sensor_readings": cur.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0] or 0,
            "new_users_today": cur.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE(?)", (today,)).fetchone()[0] or 0,
            "today_analyses": cur.execute("SELECT COUNT(*) FROM analysis WHERE DATE(created_at) = DATE(?)", (today,)).fetchone()[0] or 0,
            "avg_daily_analyses": round((cur.execute("SELECT COUNT(*) FROM analysis WHERE created_at >= ?", (week_ago,)).fetchone()[0] or 0) / 7, 1)
        }

        recent_users = cur.execute(
            "SELECT id, name, email, role, status, created_at FROM users ORDER BY id DESC LIMIT 5"
        ).fetchall()

        recent_analyses = cur.execute("""
            SELECT a.*, u.name as user_name 
            FROM analysis a 
            LEFT JOIN users u ON a.user = u.name 
            ORDER BY a.id DESC LIMIT 5
        """).fetchall()

        week_days = []
        for i in range(7):
            day = week_ago + timedelta(days=i)
            count = cur.execute(
                "SELECT COUNT(*) FROM analysis WHERE DATE(created_at) = DATE(?)", 
                (day,)
            ).fetchone()[0] or 0
            week_days.append({
                'label': day.strftime('%a'),
                'value': count
            })

        last_login = datetime.now().strftime('%b %d, %Y %H:%M')
        
        db.close()

        return render_template("admin_dashboard.html", 
                             stats=stats, 
                             users=recent_users,
                             analyses=recent_analyses,
                             recent_users=recent_users,
                             recent_analyses=recent_analyses,
                             week_days=week_days,
                             last_login=last_login)

    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}", "error")
        return render_template("admin_dashboard.html", 
                             stats={
                                 "total_users": 0,
                                 "active_users": 0,
                                 "pending_requests": 0,
                                 "total_analyses": 0,
                                 "total_sensor_readings": 0,
                                 "new_users_today": 0,
                                 "today_analyses": 0,
                                 "avg_daily_analyses": 0
                             }, 
                             users=[], 
                             analyses=[],
                             recent_users=[],
                             recent_analyses=[],
                             week_days=[{'label': d, 'value': 0} for d in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']],
                             last_login=datetime.now().strftime('%b %d, %Y %H:%M'))

@app.route("/admin/users")
@login_required(roles=["admin"])
def admin_users():
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return render_template("admin_users.html", users=[])
        
        cur = db.cursor()
        users = cur.execute(
            "SELECT id, name, email, role, status FROM users ORDER BY id DESC"
        ).fetchall()
        db.close()
        
        return render_template("admin_users.html", users=users or [])
    except Exception as e:
        flash(f"Error loading users: {str(e)}", "error")
        return render_template("admin_users.html", users=[])

@app.route("/admin/analysis")
@login_required(roles=["admin"])
def admin_analysis():
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return render_template("admin_analysis.html", analyses=[])
        
        cur = db.cursor()
        analyses = cur.execute("""
            SELECT a.*, u.name as user_name 
            FROM analysis a 
            LEFT JOIN users u ON a.user = u.name 
            ORDER BY a.id DESC
        """).fetchall()
        db.close()
        
        return render_template("admin_analysis.html", analyses=analyses or [])
    except Exception as e:
        flash(f"Error loading analyses: {str(e)}", "error")
        return render_template("admin_analysis.html", analyses=[])

@app.route("/admin/sensors")
@login_required(roles=["admin"])
def admin_sensors():
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return render_template("admin_sensors.html", readings=[])
        
        cur = db.cursor()
        readings = cur.execute("""
            SELECT * FROM sensor_readings 
            ORDER BY created_at DESC LIMIT 100
        """).fetchall()
        db.close()
        
        return render_template("admin_sensors.html", readings=readings or [])
    except Exception as e:
        flash(f"Error loading sensor data: {str(e)}", "error")
        return render_template("admin_sensors.html", readings=[])

@app.route("/admin/requests")
@login_required(roles=["admin"])
def admin_requests():
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return render_template("admin_requests.html", requests=[])
        
        cur = db.cursor()
        pending_requests = cur.execute(
            "SELECT id, name, email FROM users WHERE status='pending' ORDER BY id DESC"
        ).fetchall()
        db.close()
        
        return render_template("admin_requests.html", requests=pending_requests or [])
    except Exception as e:
        flash(f"Error loading requests: {str(e)}", "error")
        return render_template("admin_requests.html", requests=[])
    
@app.route("/admin/approve/<int:user_id>")
@login_required(roles=["admin"])
def approve_user(user_id):
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return redirect(url_for("admin_requests"))
        
        cur = db.cursor()
        cur.execute(
            "UPDATE users SET status='active' WHERE id=?",
            (user_id,)
        )
        db.commit()
        db.close()
        
        flash(f"User has been approved successfully", "success")

    except Exception as e:
        flash(f"Error approving user: {str(e)}", "error")

    return redirect(url_for("admin_requests"))

@app.route("/admin/deactivate/<int:user_id>")
@login_required(roles=["admin"])
def deactivate_user(user_id):
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return redirect(url_for("admin_users"))
        
        cur = db.cursor()
        cur.execute(
            "UPDATE users SET status='inactive' WHERE id=?",
            (user_id,)
        )
        db.commit()
        db.close()
        
        flash(f"User has been deactivated", "success")

    except Exception as e:
        flash(f"Error deactivating user: {str(e)}", "error")

    return redirect(url_for("admin_users"))

@app.route("/admin/activate/<int:user_id>")
@login_required(roles=["admin"])
def activate_user(user_id):
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return redirect(url_for("admin_users"))
        
        cur = db.cursor()
        cur.execute(
            "UPDATE users SET status='active' WHERE id=?",
            (user_id,)
        )
        db.commit()
        db.close()
        
        flash(f"User has been activated", "success")

    except Exception as e:
        flash(f"Error activating user: {str(e)}", "error")

    return redirect(url_for("admin_users"))

# -- Admin reports management routes
@app.route("/admin/reports")
@login_required(roles=["admin"])
def admin_reports():
    """Display all reports for admin"""
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return render_template("admin_reports.html", reports=[])
        
        cur = db.cursor()
        
        # Get all reports with analysis and user information
        cur.execute("""
            SELECT 
                r.id,
                r.user,
                r.analysis_id,
                r.report_name,
                r.report_data,
                r.created_at as report_created_at,
                a.detected,
                a.confidence,
                a.tds,
                a.ph,
                a.turbidity,
                a.temperature,
                a.created_at as analysis_created_at
            FROM reports r
            LEFT JOIN analysis a ON r.analysis_id = a.id
            ORDER BY r.id DESC
        """)
        
        reports = cur.fetchall()
        db.close()
        
        # Convert to list of dictionaries
        reports_list = []
        for row in reports:
            reports_list.append({
                'id': row['id'],
                'user': row['user'],
                'analysis_id': row['analysis_id'],
                'report_name': row['report_name'] or f"Analysis {row['analysis_id']}",
                'report_data': row['report_data'],
                'created_at': row['report_created_at'],
                'detected': row['detected'],
                'confidence': row['confidence'],
                'tds': row['tds'],
                'ph': row['ph'],
                'turbidity': row['turbidity'],
                'temperature': row['temperature'],
                'analysis_date': row['analysis_created_at']
            })
        
        return render_template("admin_reports.html", reports=reports_list)
        
    except Exception as e:
        print(f"Error loading admin reports: {e}")
        flash(f"Error loading reports: {str(e)}", "error")
        return render_template("admin_reports.html", reports=[])

@app.route("/admin/report/<int:report_id>")
@login_required(roles=["admin"])
def admin_view_report(report_id):
    """View a specific report"""
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return redirect(url_for("admin_reports"))
        
        cur = db.cursor()
        cur.execute("""
            SELECT 
                r.*,
                a.user as analysis_user,
                a.detected,
                a.confidence,
                a.plastic_type,
                a.contaminants,
                a.usage,
                a.tds,
                a.ph,
                a.turbidity,
                a.temperature,
                a.created_at as analysis_date
            FROM reports r
            LEFT JOIN analysis a ON r.analysis_id = a.id
            WHERE r.id = ?
        """, (report_id,))
        
        report = cur.fetchone()
        db.close()
        
        if not report:
            flash("Report not found", "error")
            return redirect(url_for("admin_reports"))
        
        return render_template("admin_report_detail.html", report=report)
        
    except Exception as e:
        print(f"Error viewing report: {e}")
        flash(f"Error viewing report: {str(e)}", "error")
        return redirect(url_for("admin_reports"))

@app.route("/admin/report/delete/<int:report_id>")
@login_required(roles=["admin"])
def admin_delete_report(report_id):
    """Delete a report"""
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return redirect(url_for("admin_reports"))
        
        cur = db.cursor()
        cur.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        db.commit()
        db.close()
        
        flash("Report deleted successfully", "success")
        
    except Exception as e:
        print(f"Error deleting report: {e}")
        flash(f"Error deleting report: {str(e)}", "error")
    
    return redirect(url_for("admin_reports"))

# Also add the missing reports route for regular users
@app.route("/reports")
@login_required(roles=["researcher", "analyst", "admin"])
def reports():
    """Display user's reports"""
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return render_template("reports.html", reports=[])
        
        cur = db.cursor()
        
        # Get reports for current user
        cur.execute("""
            SELECT 
                r.id,
                r.analysis_id,
                r.report_name,
                r.report_data,
                r.created_at,
                a.detected,
                a.confidence,
                a.tds,
                a.ph,
                a.turbidity,
                a.temperature
            FROM reports r
            LEFT JOIN analysis a ON r.analysis_id = a.id
            WHERE r.user = ?
            ORDER BY r.id DESC
        """, (session.get("user"),))
        
        reports = cur.fetchall()
        db.close()
        
        # Convert to list of dictionaries
        reports_list = []
        for row in reports:
            reports_list.append({
                'id': row['id'],
                'analysis_id': row['analysis_id'],
                'report_name': row['report_name'] or f"Analysis {row['analysis_id']}",
                'report_data': row['report_data'],
                'created_at': row['created_at'],
                'detected': row['detected'],
                'confidence': row['confidence'],
                'tds': row['tds'],
                'ph': row['ph'],
                'turbidity': row['turbidity'],
                'temperature': row['temperature']
            })
        
        return render_template("reports.html", reports=reports_list)
        
    except Exception as e:
        print(f"Error loading reports: {e}")
        flash(f"Error loading reports: {str(e)}", "error")
        return render_template("reports.html", reports=[])

@app.route("/report/generate/<int:analysis_id>")
@login_required(roles=["researcher", "analyst", "admin"])
def generate_report(analysis_id):
    """Generate a report from analysis data"""
    try:
        db = get_db()
        if not db:
            flash("Database connection error", "error")
            return redirect(url_for("history"))
        
        cur = db.cursor()
        
        # Get analysis data
        cur.execute("""
            SELECT * FROM analysis 
            WHERE id = ? AND user = ?
        """, (analysis_id, session.get("user")))
        
        analysis = cur.fetchone()
        
        if not analysis:
            flash("Analysis not found", "error")
            return redirect(url_for("history"))
        
        # Check if report already exists
        cur.execute("SELECT id FROM reports WHERE analysis_id = ? AND user = ?", 
                   (analysis_id, session.get("user")))
        existing = cur.fetchone()
        
        if existing:
            flash("Report already exists for this analysis", "warning")
            return redirect(url_for("reports"))
        
        # Create report data
        report_data = {
            "analysis_id": analysis_id,
            "user": session.get("user"),
            "generated_at": datetime.now().isoformat(),
            "analysis_data": dict(analysis)
        }
        
        # Insert report
        cur.execute("""
            INSERT INTO reports (analysis_id, user, report_name, report_data, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (analysis_id, session.get("user"), f"Report_{analysis_id}", json.dumps(report_data)))
        
        db.commit()
        db.close()
        
        flash("Report generated successfully!", "success")
        return redirect(url_for("reports"))
        
    except Exception as e:
        print(f"Error generating report: {e}")
        flash(f"Error generating report: {str(e)}", "error")
        return redirect(url_for("history"))

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500

# ============================================
# RUN APP
# ============================================
if __name__ == "__main__":
    print("\n=========================================")
    print("AquaPlast Flask Server Starting...")
    print("=========================================")
    print(f"Server URL: http://0.0.0.0:5000")
    print(f"ESP32 API: http://0.0.0.0:5000/api/sensor-data")
    print(f"Real-time Stream: http://0.0.0.0:5000/api/sensor-stream")
    print("=========================================\n")
    app.run(debug=True, host='0.0.0.0', port=5000)