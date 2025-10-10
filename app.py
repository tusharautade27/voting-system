from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
import MySQLdb.cursors
import db_config


app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this in production

# MySQL configuration
app.config['MYSQL_HOST'] = db_config.MYSQL_HOST
app.config['MYSQL_USER'] = db_config.MYSQL_USER
app.config['MYSQL_PASSWORD'] = db_config.MYSQL_PASSWORD
app.config['MYSQL_DB'] = db_config.MYSQL_DB

mysql = MySQL(app)

# ----------------- Routes -----------------

@app.route('/')
def home():
    return render_template('home.html')



@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():
    msg = ''
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM admin WHERE username = %s OR email = %s', (username, email))
        account = cursor.fetchone()

        if account:
            msg = 'Account with this username or email already exists!'
        else:
            cursor.execute(
                'INSERT INTO admin (username, email, password) VALUES (%s, %s, %s)',
                (username, email, password)
            )
            mysql.connection.commit()
            cursor.close()
            return redirect(url_for('home'))  # ✅ Redirects to login form on home page

        cursor.close()

    return render_template('signup.html', msg=msg)



@app.route('/admin_login', methods=['POST'])
def admin_login():
    username = request.form['username']
    password = request.form['password']
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)  # Use DictCursor for consistency
    cur.execute("SELECT * FROM admin WHERE username=%s AND password=%s", (username, password))
    admin = cur.fetchone()
    cur.close()
    if admin:
        session['admin_loggedin'] = True
        session['admin_id'] = admin['id']
        session['admin_username'] = admin['username']
        return redirect('/admin-panel')
    else:
        flash('Invalid login details. Please try again.')
        return redirect('/')







@app.route('/admin-panel')
def admin_panel():
    if 'admin_loggedin' not in session or 'admin_id' not in session:
        return redirect('/')


    cursor = mysql.connection.cursor()

    cursor.execute('SELECT * FROM candidates WHERE admin_id = %s', (session['admin_id'],))
    candidates = cursor.fetchall()

    cursor.execute("SELECT value FROM settings WHERE `key` = 'result_visibility'")
    result = cursor.fetchone()
    results_visible = result and result[0] == 'true'

    cursor.execute('''
        SELECT c.name, IFNULL(SUM(v.percentage), 0) 
        FROM candidates c 
        LEFT JOIN votes v ON c.id = v.candidate_id 
        WHERE c.admin_id = %s 
        GROUP BY c.id
    ''', (session['admin_id'],))
    vote_results = cursor.fetchall()

    cursor.close()
    msg = request.args.get('msg', '')
    return render_template('admin_panel.html', candidates=candidates, msg=msg,
                           results_visible=results_visible, vote_results=vote_results)


@app.route('/generate-pin', methods=['POST'])
def generate_pin():
    if 'admin_id' not in session:
        return redirect('/admin')

    pin = request.form['pin']
    cursor = mysql.connection.cursor()
    cursor.execute('UPDATE admin SET voting_pin = %s WHERE id = %s', (pin, session['admin_id']))
    mysql.connection.commit()
    cursor.close()
    return redirect('/admin-panel?msg=PIN updated successfully!')


@app.route('/add-candidate', methods=['GET', 'POST'])
def add_candidate():
    if 'admin_id' not in session:
        return redirect('/admin')

    if request.method == 'POST':
        name = request.form['name']
        cursor = mysql.connection.cursor()
        cursor.execute('INSERT INTO candidates (name, admin_id) VALUES (%s, %s)', (name, session['admin_id']))
        mysql.connection.commit()
        cursor.close()
        return redirect('/admin-panel?msg=Candidate added successfully!')

    return render_template('add_candidate.html')


@app.route('/edit-candidate/<int:candidate_id>', methods=['GET', 'POST'])
def edit_candidate(candidate_id):
    if 'admin_id' not in session:
        return redirect('/admin')

    cursor = mysql.connection.cursor()

    if request.method == 'POST':
        name = request.form['name']
        cursor.execute('UPDATE candidates SET name = %s WHERE id = %s AND admin_id = %s',
                       (name, candidate_id, session['admin_id']))
        mysql.connection.commit()
        cursor.close()
        return redirect('/admin-panel?msg=Candidate updated!')

    cursor.execute('SELECT name FROM candidates WHERE id = %s AND admin_id = %s',
                   (candidate_id, session['admin_id']))
    candidate = cursor.fetchone()
    cursor.close()

    if not candidate:
        return redirect('/admin-panel?msg=Candidate not found!')

    return render_template('edit_candidate.html', candidate_id=candidate_id, candidate_name=candidate[0])


@app.route('/delete-candidate/<int:candidate_id>')
def delete_candidate(candidate_id):
    if 'admin_id' not in session:
        return redirect('/admin')

    cursor = mysql.connection.cursor()

    try:
        cursor.execute('DELETE FROM votes WHERE candidate_id = %s', (candidate_id,))
        cursor.execute('DELETE FROM candidates WHERE id = %s AND admin_id = %s',
                       (candidate_id, session['admin_id']))
        mysql.connection.commit()
        msg = "Candidate and associated votes deleted successfully!"
    except Exception as e:
        mysql.connection.rollback()
        msg = f"Error: {str(e)}"
    finally:
        cursor.close()

    return redirect(f'/admin-panel?msg={msg}')


@app.route('/announce-result', methods=['POST'])
def announce_result():
    cursor = mysql.connection.cursor()
    cursor.execute("UPDATE settings SET value = 'true' WHERE `key` = 'result_visibility'")
    mysql.connection.commit()
    cursor.close()
    return redirect('/admin-panel')


@app.route('/toggle-results', methods=['POST'])
def toggle_results():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT value FROM settings WHERE `key` = 'result_visibility'")
    current = cursor.fetchone()[0]
    new_value = 'false' if current == 'true' else 'true'
    cursor.execute("UPDATE settings SET value = %s WHERE `key` = 'result_visibility'", (new_value,))
    mysql.connection.commit()
    cursor.close()
    return redirect('/admin-panel')




@app.route('/voter', methods=['GET', 'POST'])
def voter_pin_entry():
    msg = ''
    if request.method == 'POST':
        pin = request.form['voting_pin']
        email = request.form.get('email', '').strip()
        mobile = request.form.get('mobile', '').strip()

        if not email and not mobile:
            msg = 'Please enter either email or mobile number to proceed.'
            return render_template('vote_entry.html', msg=msg)

        cursor = mysql.connection.cursor()
        cursor.execute('SELECT id FROM admin WHERE voting_pin = %s', (pin,))
        admin = cursor.fetchone()
        cursor.close()

        if admin:
            session['voter_email'] = email
            session['voter_mobile'] = mobile
            return redirect(f'/vote/{admin[0]}')
        else:
            msg = 'Invalid voting PIN.'
    return render_template('vote_entry.html', msg=msg)

@app.route('/vote/<int:admin_id>', methods=['GET', 'POST'])
def vote(admin_id):
    msg = ''
    cursor = mysql.connection.cursor()

    cursor.execute('SELECT required_fields FROM admin WHERE id = %s', (admin_id,))
    fields_row = cursor.fetchone()
    required_fields = fields_row[0].split(',') if fields_row and fields_row[0] else []

    cursor.execute('SELECT * FROM candidates WHERE admin_id = %s', (admin_id,))
    candidates = cursor.fetchall()

    if request.method == 'POST':
        name = request.form.get('name', '').strip() if 'name' in required_fields else ''
        email = session.get('voter_email', '').strip()
        mobile = session.get('voter_mobile', '').strip()

        if not email and not mobile:
            msg = 'You must enter either email or mobile number to vote.'
        else:
            query = 'SELECT * FROM votes WHERE admin_id = %s'
            params = [admin_id]

            if email:
                query += ' AND user_email = %s'
                params.append(email)
            elif mobile:
                query += ' AND mobile = %s'
                params.append(mobile)

            cursor.execute(query, tuple(params))
            if cursor.fetchone():
                msg = 'You have already voted!'
            else:
                total_percent = 0
                votes = []

                for candidate in candidates:
                    cid = str(candidate[0])
                    try:
                        percent = int(request.form.get(f'percentage_{cid}', 0))
                    except ValueError:
                        percent = 0
                    total_percent += percent
                    votes.append((email, name, mobile, cid, percent))

                if total_percent != 100:
                    msg = 'Total percentage must be exactly 100%.'
                else:
                    for vote in votes:
                        cursor.execute(
                            'INSERT INTO votes (user_email, name, mobile, candidate_id, percentage, admin_id) VALUES (%s, %s, %s, %s, %s, %s)',
                            (*vote, admin_id)
                        )
                    mysql.connection.commit()
                    session.pop('voter_email', None)
                    session.pop('voter_mobile', None)
                    
                    return redirect('/voter')
    cursor.close()
    return render_template('vote.html', candidates=candidates, msg=msg, required_fields=required_fields)




@app.route('/verify-pin', methods=['POST'])
def verify_pin():
    entered_pin = request.form['pin']

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id FROM admin WHERE voting_pin = %s", (entered_pin,))
    result = cursor.fetchone()
    cursor.close()

    if result:
        admin_id = result[0]
       
        return redirect(url_for('voter_results', admin_id=admin_id))   
    else:
        return render_template('check_pin.html', msg="Invalid PIN")






@app.route('/voter-results/<int:admin_id>')
def voter_results(admin_id):
    cursor = mysql.connection.cursor()

    cursor.execute("SELECT value FROM settings WHERE `key` = 'result_visibility'")
    result = cursor.fetchone()
    announced = result and result[0] == 'true'

    vote_results = []

    if announced:
        cursor.execute('''
            SELECT c.name, IFNULL(SUM(v.percentage), 0)
            FROM candidates c
            LEFT JOIN votes v ON c.id = v.candidate_id
            WHERE c.admin_id = %s
            GROUP BY c.id
        ''', (admin_id,))
        vote_results = cursor.fetchall()

    cursor.close()

    labels = [row[0] for row in vote_results]
    data = [row[1] for row in vote_results]

    return render_template('voter_results.html',
                           vote_results=vote_results,
                           announced=announced,
                           labels=labels,
                           data=data)


@app.route('/check-pin')
def check_pin():
    return render_template('check_pin.html')



# ----------------- Run App -----------------

if __name__ == '__main__':
    app.run(debug=True, port=5001)
