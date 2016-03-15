import sqlite3
from flask import Flask, request, session, g, redirect, url_for, \
     abort, render_template, flash

# configuration
DATABASE = './tmp/database.db'
DEBUG = True
SECRET_KEY = 'development key'


# create our little application :)
app = Flask(__name__)
app.config.from_object(__name__)

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
def show_entries():
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
            return redirect(url_for('show_entries'))
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    flash('You were logged out')
    return redirect(url_for('show_entries'))

@app.route('/add', methods=['POST'])
def add_entry():
    if not session.get('logged_in'):
        abort(401)
    g.db.execute('insert into entries (title, text) values (?, ?)',
                 [request.form['title'], request.form['text']])
    g.db.commit()
    flash('New entry was successfully posted')
    return redirect(url_for('show_entries'))


if __name__ == '__main__':
    app.run()


