from flask import Flask, render_template, request, session, redirect, url_for, send_file, flash
import os
import uuid
import hashlib
import pymysql.cursors
from functools import wraps
import time

app = Flask(__name__)
app.secret_key = "super secret key"
IMAGES_DIR = os.path.join(os.getcwd(), "images")

connection = pymysql.connect(host="localhost",
                             user="root",
                             password="",
                             db="finsta",
                             charset="utf8mb4",
                             port=3306,
                             cursorclass=pymysql.cursors.DictCursor,
                             autocommit=True)

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if not "username" in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return dec

@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("home"))
    return render_template("index.html")

@app.route("/home")
@login_required
def home():
    return render_template("home.html", username=session["username"])

@app.route("/upload", methods=["GET"])
@login_required
def upload():
    return render_template("upload.html")

@app.route("/images", methods=["GET"])
@login_required
def images():
    cursor = connection.cursor();
    username = session['username']

    query = "SELECT Photo.photoID, filePath, timestamp, caption, fname, lname FROM VisiblePhotos \
            NATURAL JOIN Photo JOIN Person ON Person.username = Photo.photoOwner \
            WHERE VisiblePhotos.username=%s \
            ORDER BY timestamp DESC "
    with connection.cursor() as cursor:
        cursor.execute(query, username)
    data = cursor.fetchall()
    for i in data:
        photoID = i['photoID']
        query = "SELECT fname, lname FROM Tag NATURAL JOIN Person WHERE photoID=%s AND acceptedTag=1"
        with connection.cursor() as cursor:
            cursor.execute(query, photoID)
        tagged = cursor.fetchall()
        lst =[]
        for dictionary in tagged:
            lst.append((dictionary['fname'], dictionary['lname']))
        i['tag'] = lst
        #count number of likes
        query ="SELECT COUNT(*) FROM Liked where photoID=%s"
        with connection.cursor() as cursor:
            cursor.execute(query, photoID)
        i['count'] = list(cursor.fetchone().values())[0]
         #get comments
        query="SELECT username, commentText, timestamp FROM Comment WHERE photoID=%s"
        with connection.cursor() as cursor:
            cursor.execute(query, photoID)
        i['comments'] = list(cursor.fetchall())

    return render_template("images.html", images=data)

@app.route("/image/<image_name>", methods=["GET"])
def image(image_name):
    image_location = os.path.join(IMAGES_DIR, image_name)
    if os.path.isfile(image_location):
        return send_file(image_location, mimetype="image/jpg")

@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")

@app.route("/register", methods=["GET"])
def register():
    return render_template("register.html")

@app.route("/loginAuth", methods=["POST"])
def loginAuth():
    if request.form:
        requestData = request.form
        username = requestData["username"]
        plaintextPasword = requestData["password"]
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()

        with connection.cursor() as cursor:
            query = "SELECT * FROM Person WHERE username = %s AND password = %s"
            cursor.execute(query, (username, hashedPassword))
        data = cursor.fetchone()
        if data:
            session["username"] = username
            return redirect(url_for("home"))

        error = "Incorrect username or password."
        return render_template("login.html", error=error)

    error = "An unknown error has occurred. Please try again."
    return render_template("login.html", error=error)

@app.route("/registerAuth", methods=["POST"])
def registerAuth():
    if request.form:
        requestData = request.form
        username = requestData["username"]
        plaintextPasword = requestData["password"]
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()
        firstName = requestData["fname"]
        lastName = requestData["lname"]

        try:
            with connection.cursor() as cursor:
                query = "INSERT INTO Person (username, password, fname, lname) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (username, hashedPassword, firstName, lastName))
        except pymysql.err.IntegrityError:
            error = "%s is already taken." % (username)
            return render_template('register.html', error=error)

        return redirect(url_for("login"))

    error = "An error has occurred. Please try again."
    return render_template("register.html", error=error)

@app.route("/logout", methods=["GET"])
def logout():
    session.pop("username")
    return redirect("/")

@app.route("/uploadImage", methods=["POST"])
@login_required
def upload_image():
    if request.files:
        image_file = request.files.get("imageToUpload", "")
        image_name = image_file.filename
        filepath = os.path.join(IMAGES_DIR, image_name)
        image_file.save(filepath)
        caption = request.form['Caption']
        visible = request.form['AllFollowers']
        username = session["username"]
        query = "INSERT INTO Photo (timestamp, filePath, caption, AllFollowers, photoOwner) VALUES (%s, %s, %s, %s, %s)"
        with connection.cursor() as cursor:
            cursor.execute(query, (time.strftime('%Y-%m-%d %H:%M:%S'), image_name, caption, visible, username))
        message = "Image has been successfully uploaded."
        return render_template("upload.html", message=message)
    else:
        message = "Failed to upload image."
        return render_template("upload.html", message=message)

@app.route("/follow", methods=["GET", "POST"])
@login_required
def follow():
    error = None
    if request.method == "POST":
        if request.form:
            username = request.form["username"]
            if username == session["username"]:
                error = "You can't follow yourself"
            else:
                query = "INSERT INTO Follow VALUES (%s, %s, FALSE)"
                with connection.cursor() as cursor:
                    if (username == session['username']):
                        error = "You cannot follow yourself"
                    elif userExists(username):
                        try: 
                            cursor.execute(query, (session["username"], username))
                        except pymysql.err.IntegrityError:
                            error="Either the request is already sent or you are following the person"
                    else:
                        error = "User does not exist"
        else:
            error = "An unknown error has occurred. Please try again."
    return render_template('follow.html', error=error)

@app.route("/unfollow", methods=["GET", "POST"])
@login_required
def unfollow():
    error = None
    if request.method == "POST":
        if request.form:
            username = request.form["username"]
            if username == session["username"]:
                error = "You can't unfollow yourself"
            elif not userExists(username):
                error = "User doesn't exist"
            elif not isFollowing(session["username"], username):
                error = "You are not following this person"
            else:
                queries = ["DELETE FROM Follow WHERE followerUsername=%s AND followeeUsername=%s AND acceptedFollow"
                          ,"DELETE FROM Tag WHERE username=%s AND photoID IN (SELECT photoID FROM Photo WHERE photoOwner=%s)"
                          ,"DELETE FROM Liked WHERE username=%s AND photoID IN (SELECT photoID FROM Photo WHERE photoOwner=%s)"
                          ]
                # query = "DELETE FROM Follow WHERE followerUsername=%s AND followeeUsername=%s AND acceptedFollow"
                with connection.cursor() as cursor:
                    for query in queries:
                        cursor.execute(query, (session["username"], username))
        else:
            error = "An unknown error has occurred. Please try again."
    return render_template('unfollow.html', error=error)

@app.route("/followRequests", methods=["GET", "POST"])
@login_required
def followRequests():
    error = None
    if request.method == "POST":
        if request.form:
            username = request.form["username"]
            accept = request.form["accept"] == "true"
            if accept:
                query = "UPDATE Follow SET acceptedFollow=TRUE WHERE followerUsername=%s AND followeeUsername=%s"
            else:
                query = "DELETE FROM Follow WHERE followerUsername=%s AND followeeUsername=%s"
            with connection.cursor() as cursor:
                cursor.execute(query, (username, session["username"]))
        else:
            error = "An unknown error has occurred. Please try again."
    with connection.cursor() as cursor:
        query = "SELECT followerUsername FROM Follow WHERE followeeUsername=%s AND NOT acceptedFollow"
        with connection.cursor() as cursor:
            cursor.execute(query, session["username"])
            potentialFollowers = [row["followerUsername"] for row in cursor.fetchall()]
    return render_template('followRequests.html', potentialFollowers=potentialFollowers, error=error)

@app.route("/tagRequests", methods=["GET", "POST"])
@login_required
def tagRequests():
    error = None
    if request.method == "POST":
        if request.form:
            photoID = request.form["photoID"]
            accept = request.form["accept"] == "true"
            if accept:
                query = "UPDATE Tag SET acceptedTag=TRUE WHERE username=%s AND photoID=%s"
            else:
                query = "DELETE FROM Tag WHERE username=%s AND photoID=%s"
            with connection.cursor() as cursor:
                cursor.execute(query, (session["username"], photoID))
        else:
            error = "An unknown error has occurred. Please try again."
    query = "SELECT photoID, filePath FROM Tag NATURAL JOIN Photo WHERE username=%s AND NOT acceptedTag"
    with connection.cursor() as cursor:
        cursor.execute(query, session["username"])
        tags = cursor.fetchall()
    return render_template('tagRequests.html', tags=tags, error=error)

@app.route("/tagPhoto", methods=["GET", "POST"])
@login_required
def tagPhoto():
    username= session["username"]
    error = None
    if request.method == "POST":
        if request.form:
            tagee = request.form["tagee"]
            photoID = request.form["photoID"]
            if userExists(tagee):
                if tagee == username:
                    query = "INSERT INTO Tag VALUES (%s, %s, TRUE)"
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute(query, (tagee, photoID))
                    except pymysql.err.IntegrityError:
                        error="you already tagged yourself"
                elif isPhotoVisible(photoID, tagee):
                    query = "INSERT INTO Tag VALUES (%s, %s, FALSE)"
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute(query, (tagee, photoID))
                    except pymysql.err.IntegrityError:
                        error='You already tagged that person to this photo'
                else:
                    error = "Photo is not visible to the person you are tagging!"
            else:
                error = "User you are trying to tag doesn't exist"
        else:
            error = "An unknown error has occurred. Please try again."
    query = "SELECT photoID, filePath FROM VisiblePhotos NATURAL JOIN Photo WHERE username=%s"
    with connection.cursor() as cursor:
        cursor.execute(query, username)
        visiblePhotos = cursor.fetchall()
    return render_template('tagPhoto.html', visiblePhotos=visiblePhotos, error=error)

@app.route("/addFriend", methods=["GET", "POST"])
@login_required
def addFriend():
    groupowner = session["username"]
    error = None
    if request.method == "POST":
        if request.form:
            groupname = request.form['groupName']
            friendname = request.form['friendName']
            friendExists = userExists(friendname)
            if friendExists:
                if alreadyInGroup(friendname, groupname):
                    error = "User is already in your group."
                else:
                    query = "INSERT INTO Belong VALUES (%s, %s, %s)"
                    with connection.cursor() as cursor:
                        cursor.execute(query, (groupname, groupowner, friendname))
            else:
                error = "Friend you are trying to add doesn't exist"
        else:
            error = "An unknown error has occurred. Please try again."
    query = "SELECT DISTINCT groupName FROM Belong WHERE groupOwner=%s"
    with connection.cursor() as cursor:
        cursor.execute(query, groupowner)
        groups = [tup["groupName"] for tup in cursor.fetchall()]
    return render_template('addFriend.html', groups=groups, error=error)
  
@app.route("/AssignPhotoToGroup", methods=["POST", "GET"])
@login_required
def assign():
    msg = None
    if request.method == "POST":
        groupName = request.form['groupName']
        groupOwner = request.form['groupOwner']
        exists = closefriendgroupExists(groupName, groupOwner)
        msg = "Either that closefriendgroup does not exist or that is not the group owner"
        if (exists):
            username = session["username"]
            photoid = request.form['photoID']
            belong = belongToGroup(groupName, groupOwner, username)
            msg = "you do not belong in this group"
            #print(belong, file=sys.stderr)
            if (belong):
                exist = DoesPhotoBelongTo(username, photoid)
                msg = "Either this photo does not belong to you or you entered an invalid photo ID"
                if (exist):
                    visible = isPhotoVisibleToAll(photoid)
                    #print(visible, file=sys.stderr)
                    msg = "Either photo is already visible to all followers or it does not exist"
                    if (not visible):
                        photobelongstouser = DoesPhotoBelongTo(username, photoid)
                        msg = "this photo does not belong to you"
                        if(photobelongstouser):
                            try:
                                query = "INSERT INTO share (groupName, groupOwner, photoID) values (%s, %s, %s)"
                                with connection.cursor() as cursor:
                                    cursor.execute(query, (groupName, groupOwner, photoid))
                                msg = "sucessfully allowed members in " + groupName +" to view "
                            except pymysql.err.IntegrityError:
                                msg="Photo is already shared in group"
                            
    return render_template("AssignPhotoToGroup.html", msg=msg)

@app.route("/likePhoto", methods=["POST"])
@login_required
def likePhoto():
    like = request.form['likebutton'] == 'like'
    username = session["username"]
    photoID = request.form['photoID']
    likedPhoto = likedAlready(username, photoID)
    if (like):
        if (not likedPhoto): #haven't liked yet
            query = "INSERT INTO Liked(username, PhotoID, timestamp) values (%s, %s, %s)"
            with connection.cursor() as cursor:
                cursor.execute(query, (username, photoID, time.strftime('%Y-%m-%d %H:%M:%S')))
    else: #dislike
        if (likedPhoto):
            query = "DELETE FROM Liked WHERE username=%s AND photoID=%s"
            with connection.cursor() as cursor:
                cursor.execute(query, (username, photoID))
    return redirect("images")

@app.route("/searchByTag", methods=["GET", "POST"])
@login_required
def searchByTag():
    error = None
    photos = None
    if request.method == "POST":
        if request.form:
            tag = request.form["tag"]
            query = ("SELECT photoID, filePath "
                     "FROM (SELECT photoID FROM VisiblePhotos WHERE username=%s) AS v "
                     "NATURAL JOIN Tag NATURAL JOIN Photo "
                     "WHERE acceptedTag AND username=%s"
                    )
            with connection.cursor() as cursor:
                cursor.execute(query, (session['username'], tag))
                photos = cursor.fetchall()
                if (len(photos) == 0):
                    error = "There are no photos to view"
        else:
            error = "An unknown error has occurred. Please try again."
    return render_template("searchByTag.html", photos=photos, error=error)

@app.route("/searchByPoster", methods=["GET", "POST"])
@login_required
def searchByPoster():
    username = session["username"]
    error = None
    photos = None
    if request.method == "POST":
        if request.form:
            poster = request.form["poster"]
            query = ("SELECT photoID, filePath "
                     "FROM (SELECT photoID FROM VisiblePhotos WHERE username=%s) AS v "
                     "NATURAL JOIN Photo WHERE photoOwner=%s"
                    )
            with connection.cursor() as cursor:
                cursor.execute(query, (username, poster))
                photos = cursor.fetchall()
                print("Photos:", photos)
                if (len(photos) == 0):
                    error = "There are no photos to view"
        else:
            error = "An unknown error has occurred. Please try again."
    return render_template("searchByPoster.html", photos=photos, error=error)
  
@app.route("/suggestedGroups", methods=["GET"])
@login_required
def suggestedGroups():
    username = session["username"]
    error = None
    groups = None
    query = ("SELECT groupName FROM Belong WHERE username IN ("
             "SELECT DISTINCT(username) FROM Belong WHERE username!=%s AND groupName IN ("
             "SELECT DISTINCT(groupName) FROM Belong WHERE username=%s)) AND groupName NOT IN ("
             "SELECT groupName FROM Belong AS b2 WHERE username=%s)"
            )
    with connection.cursor() as cursor:
        cursor.execute(query, (username, username, username))
        groups = [tup["groupName"] for tup in cursor.fetchall()]
    return render_template("suggestedGroups.html", groups=groups)

@app.route("/submitComment", methods=["POST"])
@login_required
def comment():
    comment = request.form['comment']
    user = session['username']
    photoID = request.form['photoID']
    query = "INSERT INTO Comment(username, photoID, commentText, timestamp) VALUES (%s, %s, %s, %s)"
    #insert photo
    with connection.cursor() as cursor:
        cursor.execute(query, (user, photoID, comment, time.strftime('%Y-%m-%d %H:%M:%S')))

    return redirect('images')

def likedAlready(username, photoID):
    query = "SELECT EXISTS(SELECT * FROM Liked WHERE photoID=%s AND username=%s) "
    with connection.cursor() as cursor:
        cursor.execute(query, (photoID, username))
    exists = list(cursor.fetchone().values())[0]
    return exists

def isFollowing(follower, followee):
    query = "SELECT (%s, %s, TRUE) IN (SELECT * FROM Follow)"
    with connection.cursor() as cursor:
        cursor.execute(query, (follower, followee))
        result = list(cursor.fetchone().values())[0]
    return result

def isPhotoVisibleToAll(photoID):
    query = "SELECT allFollowers FROM Photo WHERE photoID=%s"
    with connection.cursor() as cursor:
        cursor.execute(query, photoID)
        result = list(cursor.fetchone().values())[0]
    return bool(result)

def isPhotoVisible(photoID, username):
    query = "SELECT (%s, %s) IN (SELECT * FROM VisiblePhotos)"
    with connection.cursor() as cursor:
        cursor.execute(query, (username, photoID))
        result = list(cursor.fetchone().values())[0]
    return bool(result)

def userExists(username):
    query = "SELECT %s IN (SELECT username FROM Person)"
    with connection.cursor() as cursor:
        cursor.execute(query, username)
        result = list(cursor.fetchone().values())[0]
    return result

def closefriendgroupExists(groupName, groupOwner):
    query = "SELECT EXISTS(SELECT * FROM CloseFriendGroup WHERE groupName =%s AND groupOwner=%s)" #check if belong to this closefriends's group
    with connection.cursor() as cursor:
        cursor.execute(query, (groupName, groupOwner))
    exists = list(cursor.fetchone().values())[0]
    return exists

def alreadyInGroup(username, groupName):
    query = "SELECT EXISTS(SELECT * FROM Belong WHERE username=%s AND groupName=%s)"
    with connection.cursor() as cursor:
        cursor.execute(query, (groupName, groupOwner))
    exists = list(cursor.fetchone().values())[0]
    return exists

def DoesPhotoBelongTo(name, PhotoID):
    query = "SELECT EXISTS(SELECT * FROM Photo WHERE photoID=%s AND photoOwner=%s) "
    with connection.cursor() as cursor:
        cursor.execute(query, (PhotoID, name))
    exists = list(cursor.fetchone().values())[0]
    return exists
  
def belongToGroup(groupName, groupOwner, username):
    query = "SELECT EXISTS(SELECT * FROM Belong WHERE username=%s AND groupName=%s AND groupOwner=%s)"
    with connection.cursor() as cursor:
        cursor.execute(query, (username, groupName, groupOwner))
    exists = list(cursor.fetchone().values())[0]
    return exists

if __name__ == "__main__":
    if not os.path.isdir("images"):
        os.mkdir(IMAGES_DIR)
    app.run()
