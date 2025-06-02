from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import logging

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "maxfiy_kalit")  # Use environment variable
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit file size to 16MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Create a database connection with context manager."""
    conn = sqlite3.connect('auksion.db')
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS foydalanuvchilar (
                foydalanuvchi_id INTEGER PRIMARY KEY AUTOINCREMENT,
                foydalanuvchi_nomi TEXT NOT NULL UNIQUE,
                parol TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mahsulotlar (
                mahsulot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                nomi TEXT,
                tavsifi TEXT,
                boshlangich_narx REAL,
                hozirgi_narx REAL,
                sotish_muddati DATETIME,
                sotuvchi_id INTEGER,
                rasm_url TEXT,
                FOREIGN KEY (sotuvchi_id) REFERENCES foydalanuvchilar(foydalanuvchi_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS takliflar (
                taklif_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mahsulot_id INTEGER,
                foydalanuvchi_id INTEGER,
                narx REAL,
                vaqt DATETIME,
                FOREIGN KEY (mahsulot_id) REFERENCES mahsulotlar(mahsulot_id),
                FOREIGN KEY (foydalanuvchi_id) REFERENCES foydalanuvchilar(foydalanuvchi_id)
            )
        ''')
        conn.commit()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def bosh_sahifa():
    if "foydalanuvchi" not in session:
        return redirect(url_for("login"))
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM mahsulotlar LIMIT 4")
            mahsulotlar = cursor.fetchall()
        return render_template("index.html", mahsulotlar=mahsulotlar)
    except sqlite3.Error as e:
        logger.error(f"Database error in bosh_sahifa: {e}")
        return render_template("error.html", message="Ma'lumotlar bazasida xatolik yuz berdi"), 500

@app.route('/cars')
def cars():
    if "foydalanuvchi" not in session:
        return redirect(url_for("login"))
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM mahsulotlar")
            mahsulotlar = cursor.fetchall()
        return render_template("cars.html", mahsulotlar=mahsulotlar)
    except sqlite3.Error as e:
        logger.error(f"Database error in cars: {e}")
        return render_template("error.html", message="Ma'lumotlar bazasida xatolik yuz berdi"), 500

@app.route('/mahsulot_qoshish', methods=['GET', 'POST'])
def mahsulot_qoshish():
    if "foydalanuvchi" not in session:
        return redirect(url_for("login"))
    
    if request.method == 'POST':
        try:
            mahsulot_nomi = request.form['mahsulot_nomi']
            tavsifi = request.form['tavsifi']
            boshlangich_narx = float(request.form['boshlangich_narx'])
            sotish_vaqti = request.form['sotish_vaqti']
            
            # Validate datetime format
            try:
                sotish_muddati = datetime.strptime(sotish_vaqti, '%Y-%m-%dT%H:%M')
            except ValueError:
                return render_template('mahsulot_qoshish.html', xabar="Noto'g'ri sana formati")

            rasm_url = None
            if 'mashina_rasmi' in request.files:
                file = request.files['mashina_rasmi']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    rasm_url = '/' + file_path.replace('\\', '/')

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO mahsulotlar (nomi, tavsifi, boshlangich_narx, hozirgi_narx, sotish_muddati, rasm_url, sotuvchi_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (mahsulot_nomi, tavsifi, boshlangich_narx, boshlangich_narx, sotish_muddati, rasm_url, session['foydalanuvchi_id'])
                )
                conn.commit()
            return redirect(url_for('bosh_sahifa'))
        except (ValueError, sqlite3.Error) as e:
            logger.error(f"Error in mahsulot_qoshish: {e}")
            return render_template('mahsulot_qoshish.html', xabar="Ma'lumotlarni kiritishda xatolik"), 400

    return render_template('mahsulot_qoshish.html')

@app.route('/mahsulot/<int:id>', methods=['GET', 'POST'])
def mahsulot_detail(id):
    if "foydalanuvchi" not in session:
        return redirect(url_for("login"))
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM mahsulotlar WHERE mahsulot_id = ?", (id,))
            mahsulot = cursor.fetchone()
            if not mahsulot:
                return render_template("error.html", message="Mahsulot topilmadi"), 404

            # Check if auction is still active
            sotish_muddati = datetime.strptime(mahsulot['sotish_muddati'], '%Y-%m-%d %H:%M:%S')
            if sotish_muddati < datetime.now():
                return render_template('mahsulot.html', mahsulot=mahsulot, takliflar=[], xabar="Auksion muddati tugagan")

            if request.method == 'POST':
                try:
                    taklif_narx = float(request.form["taklif_narx"])
                    if taklif_narx <= mahsulot['hozirgi_narx']:
                        return render_template('mahsulot.html', mahsulot=mahsulot, takliflar=[], xabar="Taklif narxi joriy narxdan yuqori bo'lishi kerak")
                    
                    cursor.execute(
                        "INSERT INTO takliflar (mahsulot_id, foydalanuvchi_id, narx, vaqt) VALUES (?, ?, ?, ?)",
                        (id, session['foydalanuvchi_id'], taklif_narx, datetime.now())
                    )
                    cursor.execute(
                        "UPDATE mahsulotlar SET hozirgi_narx = ? WHERE mahsulot_id = ?",
                        (taklif_narx, id)
                    )
                    conn.commit()
                except ValueError:
                    return render_template('mahsulot.html', mahsulot=mahsulot, takliflar=[], xabar="Noto'g'ri narx kiritildi")

            cursor.execute("SELECT * FROM takliflar WHERE mahsulot_id = ? ORDER BY narx DESC", (id,))
            takliflar = cursor.fetchall()
            return render_template('mahsulot.html', mahsulot=mahsulot, takliflar=takliflar)
    except sqlite3.Error as e:
        logger.error(f"Database error in mahsulot_detail: {e}")
        return render_template("error.html", message="Ma'lumotlar bazasida xatolik yuz berdi"), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            foydalanuvchi_nomi = request.form['foydalanuvchi_nomi']
            parol = request.form['parol']

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM foydalanuvchilar WHERE foydalanuvchi_nomi = ?", (foydalanuvchi_nomi,))
                if cursor.fetchone():
                    return render_template('log.html', xabar="Bu foydalanuvchi nomi allaqachon mavjud", form_type="register")

                cursor.execute('INSERT INTO foydalanuvchilar (foydalanuvchi_nomi, parol) VALUES (?, ?)', 
                              (foydalanuvchi_nomi, parol))
                conn.commit()
                cursor.execute("SELECT foydalanuvchi_id FROM foydalanuvchilar WHERE foydalanuvchi_nomi = ?", (foydalanuvchi_nomi,))
                foydalanuvchi_id = cursor.fetchone()['foydalanuvchi_id']
                
                session['foydalanuvchi'] = foydalanuvchi_nomi
                session['foydalanuvchi_id'] = foydalanuvchi_id
                return redirect(url_for('bosh_sahifa'))
        except sqlite3.Error as e:
            logger.error(f"Database error in register: {e}")
            return render_template('log.html', xabar="Ro'yxatdan o'tishda xatolik yuz berdi", form_type="register"), 500

    return render_template('register.html', form_type="register")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            foydalanuvchi_nomi = request.form['foydalanuvchi_nomi']
            parol = request.form['parol']

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM foydalanuvchilar WHERE foydalanuvchi_nomi = ?", (foydalanuvchi_nomi,))
                foydalanuvchi = cursor.fetchone()

                if foydalanuvchi and foydalanuvchi['parol'] == parol:
                    session['foydalanuvchi'] = foydalanuvchi_nomi
                    session['foydalanuvchi_id'] = foydalanuvchi['foydalanuvchi_id']
                    return redirect(url_for('bosh_sahifa'))
                else:
                    return render_template('log.html', xabar='Foydalanuvchi nomi yoki parol xato', form_type="login")
        except sqlite3.Error as e:
            logger.error(f"Database error in login: {e}")
            return render_template('log.html', xabar="Kirishda xatolik yuz berdi", form_type="login"), 500

    return render_template('register.html', form_type="login")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('bosh_sahifa'))

if __name__ == '__main__':
    init_db()
    app.run(debug=False)  