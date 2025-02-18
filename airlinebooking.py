from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
import MySQLdb.cursors
import re
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import pandas as pd

def get_flight_recommendations(user_id):
    # Retrieve booking data from the database
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("""
        SELECT users.user_id, flights.flight_id, flights.airline, flights.source, flights.destination, bookings.status
        FROM users
        JOIN bookings ON users.user_id = bookings.user_id
        JOIN flights ON bookings.flight_id = flights.flight_id
        WHERE users.user_id = %s
    """, (user_id,))
    bookings = cursor.fetchall()
    cursor.close()

    # Create a DataFrame to process the booking data
    flight_data = pd.DataFrame(bookings)

    # Convert user-booking data to a matrix of users x flights (1 if booked, 0 if not)
    user_flight_matrix = flight_data.pivot_table(index='user_id', columns='flight_id', values='status', aggfunc=lambda x: (x == 'confirmed').sum(), fill_value=0)


    # Calculate cosine similarity between users
    cosine_sim = cosine_similarity(user_flight_matrix)

    # Get the most similar users to the current user
    user_index = user_flight_matrix.index.get_loc(user_id)
    similar_users = list(enumerate(cosine_sim[user_index]))

    # Sort the users based on similarity
    similar_users = sorted(similar_users, key=lambda x: x[1], reverse=True)

    recommended_flights = []
    for user, sim_score in similar_users[:5]:  # Top 5 similar users
        similar_user_flights = user_flight_matrix.iloc[user]
        recommended_flights += similar_user_flights[similar_user_flights == 1].index.tolist()

    # Filter out already booked flights
    user_booked_flights = set(flight_data[flight_data['user_id'] == user_id]['flight_id'].tolist())
    recommended_flights = list(set(recommended_flights) - user_booked_flights)

    return recommended_flights


app = Flask(__name__)

# Secret key for session management
app.secret_key = 'your_secret_key'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Akshat@10'
app.config['MYSQL_DB'] = 'dbms_airline'

mysql = MySQL(app)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            email = request.form.get('email', '').strip()  # Handle email correctly
            role = request.form['role'].strip().lower()

            # Validate role before inserting
            if role not in ['user', 'admin']:
                return "Invalid role! Choose 'user' or 'admin'.", 400

            # If email is provided, validate its format
            if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                return "Invalid email address", 400

            cursor = mysql.connection.cursor()
            cursor.execute('INSERT INTO users (username, password, email, role) VALUES (%s, %s, %s, %s)', 
                           (username, password, email if email else None, role))
            mysql.connection.commit()
            cursor.close()
            return redirect(url_for('login'))
        except Exception as e:
            return f"Error: {str(e)}", 500

    return render_template('register.html')

@app.route('/admin/flights')
def admin_flights():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM flights")
    flights = cursor.fetchall()
    cursor.close()

    return render_template('admin_flights.html', flights=flights)

@app.route('/admin/users_with_bookings')
def admin_users_with_bookings():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("""
        SELECT users.user_id, users.username, users.email, bookings.booking_id, flights.airline, flights.source, flights.destination
        FROM users
        JOIN bookings ON users.user_id = bookings.user_id
        JOIN flights ON bookings.flight_id = flights.flight_id
    """)
    users_with_bookings = cursor.fetchall()
    cursor.close()

    return render_template('admin_users_with_bookings.html', users_with_bookings=users_with_bookings)

@app.route('/admin/edit_flight/<int:flight_id>', methods=['GET', 'POST'])
def edit_flight(flight_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM flights WHERE flight_id = %s", (flight_id,))
    flight = cursor.fetchone()

    if request.method == 'POST':
        airline = request.form['airline']
        source = request.form['source']
        destination = request.form['destination']
        departure_time = request.form['departure_time']
        arrival_time = request.form['arrival_time']
        price = request.form['price']
        seats_available = request.form['seats_available']

        # Update flight details in the database
        cursor.execute("""
            UPDATE flights
            SET airline = %s, source = %s, destination = %s, departure_time = %s, arrival_time = %s, price = %s, seats_available = %s
            WHERE flight_id = %s
        """, (airline, source, destination, departure_time, arrival_time, price, seats_available, flight_id))
        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('admin_flights'))

    return render_template('edit_flight.html', flight=flight)

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        role = request.form['role']

        # Validate role before updating
        if role not in ['user', 'admin']:
            return "Invalid role! Choose 'user' or 'admin'.", 400

        # Update user details in the database
        cursor.execute("""
            UPDATE users
            SET username = %s, email = %s, role = %s
            WHERE user_id = %s
        """, (username, email, role, user_id))
        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('admin_users_with_bookings'))

    return render_template('edit_user.html', user=user)

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    return render_template('admin_dashboard.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT user_id, username, password, role FROM users WHERE username = %s AND password = %s', (username, password))
        account = cursor.fetchone()

        if account:
            session['loggedin'] = True
            session['username'] = account['username']
            session['role'] = account['role']
            session['user_id'] = account['user_id']  # Update to use 'user_id'
            return redirect(url_for('dashboard'))
        else:
            return 'Invalid credentials, please try again!'
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'loggedin' in session:
        return render_template('dashboard.html', username=session['username'], role=session['role'])
    return redirect(url_for('login'))


@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('username', None)
    session.pop('role', None)
    session.pop('user_id', None)
    session.clear()
    return redirect(url_for('login'))


@app.route('/booking', methods=['GET', 'POST'])
def booking():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Fetch unique sources and destinations
    cursor.execute("SELECT DISTINCT source FROM flights")
    sources = [row['source'] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT destination FROM flights")
    destinations = [row['destination'] for row in cursor.fetchall()]

    # Get user-selected filters
    source_filter = request.args.get('from')
    destination_filter = request.args.get('to')

    # Base query
    query = "SELECT * FROM flights"
    params = []

    # Apply filters if selected
    if source_filter and destination_filter:
        query += " WHERE source = %s AND destination = %s"
        params.extend([source_filter, destination_filter])
    elif source_filter:
        query += " WHERE source = %s"
        params.append(source_filter)
    elif destination_filter:
        query += " WHERE destination = %s"
        params.append(destination_filter)

    cursor.execute(query, params)
    flights = cursor.fetchall()
    cursor.close()

    return render_template('booking.html', flights=flights, sources=sources, destinations=destinations)



@app.route('/book_flight/<int:flight_id>', methods=['GET', 'POST'])
def book_flight(flight_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    # Fetch flight details from the database
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM flights WHERE flight_id = %s", (flight_id,))
    flight = cursor.fetchone()

    if not flight:
        return "Flight not found!", 404  # Handle invalid flight_id

    if request.method == 'POST':
        # Insert booking into database
        cursor.execute("INSERT INTO bookings (user_id, flight_id, status) VALUES (%s, %s, %s)", (user_id, flight_id, 'pending'))
        mysql.connection.commit()

        # Redirect to the payment page
        return redirect(url_for('payment', flight_id=flight_id))

    return render_template('book_flight.html', flight=flight)

@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Delete the booking from the database
    cursor.execute("DELETE FROM bookings WHERE booking_id = %s AND user_id = %s", (booking_id, user_id))
    mysql.connection.commit()
    cursor.close()

    return redirect(url_for('my_bookings'))



@app.route('/payment/<int:flight_id>', methods=['GET', 'POST'])
def payment(flight_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    # Fetch flight details
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM flights WHERE flight_id = %s", (flight_id,))
    flight = cursor.fetchone()

    if not flight:
        return "Flight not found!", 404

    if request.method == 'POST':
        # Mark booking as "confirmed"
        cursor.execute("UPDATE bookings SET status = 'confirmed' WHERE user_id = %s AND flight_id = %s", (user_id, flight_id))
        mysql.connection.commit()

        return redirect(url_for('my_bookings'))

    return render_template('payment.html', flight=flight)



@app.route('/my_bookings')
def my_bookings():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("""
        SELECT 
            bookings.booking_id, 
            flights.airline, 
            flights.source, 
            flights.destination, 
            flights.departure_time, 
            flights.arrival_time, 
            flights.price, 
            bookings.status
        FROM 
            bookings 
        JOIN 
            flights ON bookings.flight_id = flights.flight_id 
        WHERE 
            bookings.user_id = %s
    """, (user_id,))
    bookings = cursor.fetchall()

    return render_template('my_bookings.html', bookings=bookings)



if __name__ == '__main__':
    app.run(debug=True)
