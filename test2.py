from flask import Flask, request, render_template, redirect, url_for, session, abort, flash
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from bson import ObjectId

app = Flask(__name__)

# Secret key for session management
app.secret_key = 'your_secret_key_here'

# MongoDB client setup
try:
    client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
    db = client.website_db
    users_collection = db.users
    photos_collection = db.photos
    messages_collection = db.messages
    # Test the connection
    client.server_info()
    print("Connected to MongoDB")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    users_collection = None
    photos_collection = None
    messages_collection = None

# File upload setup
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static/uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    if users_collection is not None:
        users = users_collection.find()
    else:
        users = []

    keyword = request.args.get('keyword')
    if photos_collection is not None:
        if keyword:
            photos = photos_collection.find({"keywords": {"$regex": keyword, "$options": "i"}})
        else:
            photos = photos_collection.find()
    else:
        photos = []

    return render_template('home.html', users=users, photos=photos)

# Sign up page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        if users_collection is None:
            return "Database connection error!"

        try:
            username = request.form['username']
            password = request.form['password']
        except KeyError as e:
            print(f"Missing form field: {e}")
            return "Missing form field!"

        if users_collection.find_one({"username": username}):
            return "User already exists!"

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        users_collection.insert_one({'username': username, 'password': hashed_password})
        return redirect(url_for('login'))

    return render_template('signup.html')

# Sign in page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if users_collection is None:
            return "Database connection error!"

        try:
            username = request.form['username']
            password = request.form['password']
        except KeyError as e:
            print(f"Missing form field: {e}")
            return "Missing form field!"

        user = users_collection.find_one({"username": username})

        if user and check_password_hash(user['password'], password):
            session['username'] = username
            return redirect(url_for('home'))
        return "Invalid username or password!"

    return render_template('login.html')

# Sign out page
@app.route('/signout')
def signout():
    session.pop('username', None)
    return redirect(url_for('home'))

# Upload photo page
@app.route('/upload_photo', methods=['GET', 'POST'])
def upload_photo():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        if photos_collection is None:
            return "Database connection error!"

        try:
            description = request.form['description']
            keywords = request.form['keywords']
            file = request.files['file']
        except KeyError as e:
            print(f"Missing form field: {e}")
            return "Missing form field!"
        except Exception as e:
            print(f"Error receiving form fields: {e}")
            flash("Error receiving form fields")
            return redirect(url_for('upload_photo'))

        if file and allowed_file(file.filename):
            try:
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                print(f"File saved to: {file_path}")
                photo_url = url_for('static', filename='uploads/' + filename)

                # 디버그 메시지 추가
                print("Inserting photo data into MongoDB:", {
                    'username': session['username'],
                    'description': description,
                    'keywords': keywords,
                    'photo_url': photo_url
                })

                photos_collection.insert_one({
                    'username': session['username'],
                    'description': description,
                    'keywords': keywords.split(','),  # 키워드를 리스트로 저장
                    'photo_url': photo_url
                })
                print("Photo inserted into MongoDB")
                return redirect(url_for('profile'))
            except Exception as e:
                print(f"Error saving file: {e}")
                flash("Error saving file")
                return redirect(url_for('upload_photo'))

    return render_template('upload_photo.html')

# Edit photo page
@app.route('/edit_photo/<photo_id>', methods=['GET', 'POST'])
def edit_photo(photo_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    photo = photos_collection.find_one({'_id': ObjectId(photo_id)})

    if photo is None or photo['username'] != session['username']:
        return abort(403)  # Forbidden

    if request.method == 'POST':
        description = request.form['description']
        keywords = request.form['keywords'].split(',')

        update_data = {
            'description': description,
            'keywords': keywords
        }

        # If a new file is uploaded, handle the file upload
        if 'file' in request.files:
            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                update_data['photo_url'] = url_for('static', filename='uploads/' + filename)

        photos_collection.update_one(
            {'_id': ObjectId(photo_id)},
            {'$set': update_data}
        )
        return redirect(url_for('profile'))

    return render_template('edit_photo.html', photo=photo)

# Direct messages
@app.route('/messages', methods=['GET', 'POST'])
def messages():
    if 'username' not in session:
        return redirect(url_for('login'))
    else:
        recipient_id = request.args.get('recipient_id')
        
        if users_collection is not None:
            users = users_collection.find({'username': {'$ne':session['username']}})
        else:
            users = []
         
        if request.method == 'POST':
            if messages_collection is None:
                return "Database connection error!"

            try:
                recipient = request.form['recipient']
                message = request.form['message']
            except KeyError as e:
                print(f"Missing form field: {e}")
                return "Missing form field!"

            messages_collection.insert_one({'sender': session['username'], 'recipient': recipient, 'message': message})
            return redirect(url_for('messages', recipient_id=recipient_id))


        if messages_collection is not None:
            user_messages = list(messages_collection.find({
            '$or': [
                {'sender': session['username'], 'recipient':recipient_id},
                {'recipient': session['username'], 'sender': recipient_id}
            ]
        }))
        else:
            user_messages = []
        return render_template('messages.html', recipient_id = recipient_id, me = session['username'], users=users, messages=user_messages)

@app.route('/profile')
def profile():
    if 'username' not in session:
        return redirect(url_for('login'))

    try:
        if photos_collection is not None:
            user_photos = list(photos_collection.find({'username': session['username']}))
            # 가져온 데이터를 콘솔에 출력
            print("User photos:", user_photos)
        else:
            user_photos = []

        return render_template('profile.html', photos=user_photos)
    except Exception as e:
        print(f"Error loading profile: {e}")
        return "Error loading profile"

@app.route('/search', methods=['GET', 'POST'])
def search():
    if 'username' not in session:
        return redirect(url_for('login'))

    keyword = request.args.get('keyword')
    if photos_collection is not None:
        photos = photos_collection.find({"keywords": {"$regex": keyword, "$options": "i"}}) if keyword else photos_collection.find()
    else:
        photos = []

    return render_template('search.html', photos=photos)

# Delete message
@app.route('/delete_message', methods=["POST"] )
def delete_message():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    delete_msg = request.args.get('message_id')
    recipient_id = request.args.get('recipient_id')
    
    if not delete_msg or not recipient_id:
        return abort(400)  # Bad Request
    
    try:
        message = messages_collection.find_one({'_id': ObjectId(delete_msg)})
    except Exception as e:
        print(f"Error: {e}")
        return abort(400)  # Bad Request

    if message is None or message['sender'] != session['username']:
        return abort(403)  # Forbidden

    messages_collection.delete_one({'_id': ObjectId(delete_msg)})
    return redirect(url_for('messages', recipient_id=recipient_id))

if __name__ == '__main__':
    app.run(debug=True)
