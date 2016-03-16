import os
import sqlite3
from flask import Flask, request, session, g, redirect, url_for, \
     abort, render_template, flash
import werkzeug


# configuration
DATABASE = './tmp/database.db'
DEBUG = True
SECRET_KEY = 'development key'

UPLOAD_FOLDER = './upload'
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])



# create our little application :)
app = Flask(__name__)
app.config.from_object(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.before_request
def before_request():
    g.db = connect_db()

@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


def connect_db():
    return sqlite3.connect(app.config['DATABASE'])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['GET', 'POST'])
def create():
    error = None
    if request.method == 'POST':
        if request.form['username'] == "":
            error = 'Username needed'
        elif request.form['password'] == "":
            error = 'Password needed'
        else:
            session['logged_in'] = True
            g.db.execute('insert into user (username, password) values (?, ?)',
                     [request.form['username'], request.form['password']])
            g.db.commit()

            flash('Successfully created - You can now login')
            return redirect(url_for('login'))
    return render_template('create.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cur = g.db.execute('select id from user where username = (?) and password = (?)', [username, password])
        userid = [dict(id=row[0]) for row in cur.fetchall()]

        if len(userid) == 0:
            error = 'Invalid username or password'
        else:
            session['logged_in'] = True
            session['user_id'] = userid[0].get('id')
            flash('You were logged in')
            return redirect(url_for('profile'))
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    flash('You were logged out')
    return redirect(url_for('index'))

@app.route('/add', methods=['POST'])
def add_entry():
    if not session.get('logged_in'):
        abort(401)
    g.db.execute('insert into entries (title, text) values (?, ?)',
                 [request.form['title'], request.form['text']])
    g.db.commit()
    flash('New entry was successfully posted')
    return redirect(url_for('show_entries'))


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = werkzeug.secure_filename(file.filename)

                g.db.execute('insert into images (image, user_id, filename) values (?, ?, ?)',
                             (buffer(file.read()),session['user_id'], filename))
                g.db.commit()

                flash('uploaded image: %s' % (filename))
                return redirect(url_for('profile'))
            else:
                flash('filetype not allowed')

    return render_template('upload.html')


def blob_to_image(filename, ablob):
    folder = './static/img/'
    with open(folder + filename, 'wb') as output_file:
        output_file.write(ablob)
    return filename

@app.route('/profile', methods=['GET'])
def profile():
    id = session.get('user_id')

    cur = g.db.execute('select id, image, filename from images where user_id = (?)', [id])
    images = [dict(id=row[0], image=blob_to_image(row[2],row[1])) for row in cur.fetchall()]



   # cur = g.db.execute('select id, images.image from images inner join share on images.id = share.image_id where share.to_id = (?)', [id])
    shared_images = [dict(id=row[0], image=row[1]) for row in cur.fetchall()]

    return render_template('profile.html', images=images, shared_images=shared_images)

@app.route('/share', methods=['POST','GET'])
def share():

    return render_template('share.html')


if __name__ == '__main__':
    app.run()


