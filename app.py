from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3


app = Flask(__name__)
app.secret_key = "maxfiy_kalit"

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def init_db():
    ulanish = sqlite3.connect('auksion.db')
    kursor = ulanish.cursor()

    kursor.execute('''
        CREATE TABLE IF NOT EXISTS foydalanuvchilar (
            foydalanuvchi_id INTEGER PRIMARY KEY AUTOINCREMENT,
            foydalanuvchi_nomi TEXT NOT NULL,
            parol TEXT NOT NULL
        )
    ''')

    kursor.execute('''
        CREATE TABLE IF NOT EXISTS mahsulotlar (
            mahsulot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomi TEXT,
            tavsifi TEXT,
            boshlangich_narx REAL,
            hozirgi_narx REAL,
            sotish_muddati DATETIME,
            sotuvchi_id INTEGER,
            rasm_url TEXT
        )
    ''')

    kursor.execute('''
        CREATE TABLE IF NOT EXISTS takliflar (
            taklif_id INTEGER PRIMARY KEY AUTOINCREMENT,
            mahsulot_id INTEGER,
            foydalanuvchi_id INTEGER,
            narx REAL,
            vaqt DATETIME
        )
    ''')

    ulanish.commit()
    ulanish.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def bosh_sahifa():
    if "foydalanuvchi" in session:
        ulanish = sqlite3.connect('auksion.db')
        kursor = ulanish.cursor()
        kursor.execute("SELECT * FROM mahsulotlar")
        mahsulotlar = kursor.fetchall()
        ulanish.close()
        return render_template("index.html", mahsulotlar=mahsulotlar)
    return redirect(url_for("login"))

@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == 'POST':
        foydalanuvchi_nomi = request.form['foydalanuvchi_nomi']
        parol = request.form['parol']
        ulanish = sqlite3.connect('auksion.db')
        kursor = ulanish.cursor()
        kursor.execute("SELECT * FROM foydalanuvchilar WHERE foydalanuvchi_nomi = ?", (foydalanuvchi_nomi,))
        mavjud = kursor.fetchone()
        if mavjud:
            ulanish.close()
            return render_template('register.html', xabar="Bu foydalanuvchi nomi allaqachon mavjud")
        kursor.execute('INSERT INTO foydalanuvchilar (foydalanuvchi_nomi, parol) VALUES (?, ?)', 
                       (foydalanuvchi_nomi, parol))
        ulanish.commit()
        ulanish.close()
        session['foydalanuvchi'] = foydalanuvchi_nomi
        return redirect(url_for('bosh_sahifa'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        foydalanuvchi_nomi = request.form['foydalanuvchi_nomi']
        parol = request.form['parol']
        ulanish = sqlite3.connect('auksion.db')
        kursor = ulanish.cursor()
        kursor.execute("SELECT * FROM foydalanuvchilar WHERE foydalanuvchi_nomi = ? AND parol = ?", 
                       (foydalanuvchi_nomi, parol))
        foydalanuvchi = kursor.fetchone()
        ulanish.close()
        if foydalanuvchi:
            session['foydalanuvchi'] = foydalanuvchi_nomi
            return redirect(url_for('bosh_sahifa'))
        return render_template('login.html', xabar='Foydalanuvchi nomi yoki parol xato')
    return render_template('login.html')


@app.route('/mahsulot_qoshish', methods=['GET', 'POST'])
def mahsulot_qoshish():
    if request.method == 'POST':
        mahsulot_nomi = request.form['mahsulot_nomi']
        tavsifi = request.form['tavsifi']
        boshlangich_narx = float(request.form['boshlangich_narx'])
        sotish_vaqti = request.form['sotish_vaqti']

        rasm_url = None
        if 'mashina_rasmi' in request.files:
            file = request.files['mashina_rasmi']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                rasm_url = '/' + file_path.replace('\\', '/')

        ulanish = sqlite3.connect('auksion.db')
        kursor = ulanish.cursor()
        kursor.execute("SELECT foydalanuvchi_id FROM foydalanuvchilar WHERE foydalanuvchi_nomi = ?", (session['foydalanuvchi'],))
        sotuvchi_id = kursor.fetchone()
        kursor.execute("""INSERT INTO mahsulotlar (nomi, tavsifi, boshlangich_narx, hozirgi_narx, sotish_muddati, rasm_url, sotuvchi_id)
                          VALUES (?, ?, ?, ?, ?, ?, ?)""",
                       (mahsulot_nomi, tavsifi, boshlangich_narx, boshlangich_narx, sotish_vaqti, rasm_url, sotuvchi_id[0]))
        ulanish.commit()
        ulanish.close()
        return redirect(url_for('bosh_sahifa'))
    return render_template('mahsulot_qoshish.html')


@app.route("/mahsulot/<int:id>", methods=["GET", "POST"])
def mahsulot_detail(id):
    ulanish = sqlite3.connect("auksion.db")
    kursor = ulanish.cursor()

    if request.method == 'POST':
        taklif_narx = float(request.form["taklif_narx"])
        foydalanuvchi_nomi = session["foydalanuvchi"]
        kursor.execute("SELECT foydalanuvchi_id FROM foydalanuvchilar WHERE foydalanuvchi_nomi = ?", (foydalanuvchi_nomi,))
        foydalanuvchi_id = kursor.fetchone()[0]

        kursor.execute("INSERT INTO takliflar (mahsulot_id, foydalanuvchi_id, narx, vaqt) VALUES (?, ?, ?, ?)",
                       (id, foydalanuvchi_id, taklif_narx, datetime.now()))

        # narxni yangilash
        kursor.execute("UPDATE mahsulotlar SET hozirgi_narx = ? WHERE mahsulot_id = ? AND (hozirgi_narx IS NULL OR hozirgi_narx < ?)",
                       (taklif_narx, id, taklif_narx))

    kursor.execute("SELECT * FROM mahsulotlar WHERE mahsulot_id = ?", (id,))
    mahsulot = kursor.fetchone()
    kursor.execute("SELECT * FROM takliflar WHERE mahsulot_id = ? ORDER BY narx DESC", (id,))
    takliflar = kursor.fetchall()

    ulanish.commit()
    ulanish.close()
    return render_template('mahsulot.html', mahsulot=mahsulot, takliflar=takliflar)


@app.route('/logout')
def logout():
    session.pop('foydalanuvchi', None)
    return redirect(url_for('login'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
