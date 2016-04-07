import os
import sqlite3
import string
import random
from flask import Flask, request, session, g, redirect, url_for, \
    abort, render_template, flash
import werkzeug
import hashlib

# configuration
DATABASE = './tmp/database.db'
DEBUG = False
SECRET_KEY = 'development key'

UPLOAD_FOLDER = './upload'
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])

# create our little application :)
app = Flask(__name__)
app.config.from_object(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.jinja_env.autoescape = True


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
        elif request.form['password'] == "" or request.form['repassword'] == "":
            error = 'Password needed'
        elif request.form['password'] != request.form['repassword']:
            error = 'Password is not the same as the retyped'
        else:
            cur = g.db.execute('select username from user where username = (?)', [request.form['username']])
            u = [dict(password=row[0]) for row in cur.fetchall()]
            if len(u) == 0:
                s = os.urandom(5).encode('hex')
                sha = hashlib.sha512(s + request.form['password']).hexdigest()
                token = token_generator()
                g.db.execute('insert into user (username, password, token) values (?, ?, ?)',
                             [request.form['username'], s + ':' + sha, token])
                g.db.commit()

                flash('Successfully created - You can now login')
                return redirect(url_for('login'))
            else:
                error = 'Username is taken'
    return render_template('create.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cur = g.db.execute('select password from user where username = (?)', [username])
        pass_db = [dict(password=row[0]) for row in cur.fetchall()]
        if pass_db[0].get('password') is None:
            error = 'Invalid username or password'
            return render_template('login.html', error=error)
        p = pass_db[0].get('password').split(':')

        if p[1] == hashlib.sha512(p[0]+password).hexdigest():
            token = token_generator()
            g.db.execute('update user set token = (?) where username = (?)',
                         [token, username])
            g.db.commit()

            session['logged_in'] = True
            session['token'] = token
            flash('You were logged in')
            return redirect(url_for('profile'))
        else:
            error = 'Invalid username or password'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('token', None)
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
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = werkzeug.secure_filename(file.filename)

            user_id = get_userid_by_token(session.get('token'))

            g.db.execute('insert into images (image, user_id, filename) values (?, ?, ?)',
                         (buffer(file.read()), user_id, filename))
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
    id = get_userid_by_token(session.get('token'))

    cur = g.db.execute('select id, image, filename from images where user_id = (?)', [id])
    images = [dict(image_id=row[0], image=blob_to_image(row[2], row[1])) for row in cur.fetchall()]

    cur = g.db.execute(
        'select images.id, images.image, images.filename from images inner join share on images.id = share.image_id where share.to_id = (?)',
        [id])
    shared_images = [dict(image_id=row[0], image=blob_to_image(row[2], row[1])) for row in cur.fetchall()]

    return render_template('profile.html', images=images, shared_images=shared_images)


@app.route('/showimage/<id>/', methods=['GET'])
def show_image(id):
    user_id = get_userid_by_token(session.get('token'))
    if has_permission(id, user_id):
        cur = g.db.execute('select image, filename, user_id from images where id = (?)', [id])
        img = [dict(filename=row[1], image=blob_to_image(row[1], row[0]), user_id=row[2]) for row in cur.fetchall()]

        cur = g.db.execute('select id, username from user')
        usr = [dict(id=row[0], username=row[1]) for row in cur.fetchall()]

        cur = g.db.execute(
            'select share.id, user.username from share inner join user on user.id == share.to_id where from_id = (?) and share.image_id = (?)',
            [user_id, id])
        share = [dict(id=row[0], username=row[1]) for row in cur.fetchall()]

        cur = g.db.execute(
            'select user.username, comments.comment from user inner join comments on user.id == comments.user_id where comments.image_id = (?)',
            [id])
        comments = [dict(username=row[0], comment=row[1]) for row in cur.fetchall()]

        return render_template('image.html', imageid=id, image=img, usernames=usr, shares=share, comments=comments,
                               owner=img[0].get('user_id') == user_id)
    else:
        return redirect(url_for('no_way'))


def has_permission(img_id, user_id):
    cur = g.db.execute('select user_id from images where id = (?)', [img_id])
    img_user_id = [dict(user_id=row[0]) for row in cur.fetchall()]

    if user_id == img_user_id[0].get('user_id'):
        return True

    cur = g.db.execute(
        'select id from share where image_id = (?) and to_id = (?)',
        [img_id, user_id])
    share = [dict(id=row[0]) for row in cur.fetchall()]

    if len(share) > 0:
        return True
    return False


@app.route('/shareimage', methods=['POST'])
def share_image():
    if request.method == 'POST':
        image_id = request.form['imageid']
        to_userid = request.form['userid']

        if has_permission(image_id, get_userid_by_token(session.get('token'))):
            g.db.execute('insert into share (image_id, to_id, from_id) values (?, ?, ?)',
                         [image_id, to_userid, get_userid_by_token(session.get('token'))])
            g.db.commit()
            flash('Image shared')
            return redirect(url_for('show_image', id=image_id))


@app.route('/unshare', methods=['POST'])
def unshare():
    if request.method == 'POST':
        shared_id = request.form['shareduser']
        image_id = request.form['imageid']

        g.db.execute('delete from share where id = (?)',
                     [shared_id])
        g.db.commit()
        flash('Image unshared')
        return redirect(url_for('show_image', id=image_id))
    else:
        return redirect(url_for('no_way'))


@app.route('/no_way', methods=['GET'])
def no_way():
    return render_template('no_way.html')


@app.route('/add_comment', methods=['POST'])
def add_comment():
    if request.method == 'POST':
        # TODO: needs to check for access
        image_id = request.form['imageid']
        userid = get_userid_by_token(session.get('token'))
        comment = request.form['text']

        g.db.execute('insert into comments (user_id, image_id, comment) values (?, ?, ?)',
                     [userid, image_id, comment])
        g.db.commit()
        flash('Added comment')

        return redirect(url_for('show_image', id=image_id))


def token_generator(size=32, chars=string.ascii_uppercase + string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def get_userid_by_token(token):
    cur = g.db.execute('select id from user where token = (?)', [token])
    rows = [dict(id=row[0]) for row in cur.fetchall()]
    return rows[0].get('id')


@app.route('/test')
def test():
    return ''


if __name__ == '__main__':
    app.run(host='0.0.0.0',port=80)
