from flask import Flask, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
from typing import List
from functools import wraps
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
import smtplib

app = Flask(__name__)
app.config['SECRET_KEY'] = '8BYkEfBA6O6donzWlSihBXox7C0sKR6b'
login_manager = LoginManager()
login_manager.init_app(app)
ckeditor = CKEditor(app)
Bootstrap5(app)

# CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
db = SQLAlchemy()
db.init_app(app)

gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


class Users(db.Model, UserMixin):
    __tablename__ = "users"
    id: db.Mapped[int] = db.mapped_column(primary_key=True)
    posts: db.Mapped[List["BlogPost"]] = db.relationship(back_populates="author")
    comments: db.Mapped[List["Comment"]] = db.relationship(back_populates="comment_author")
    email = db.Column(db.String(250), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    name = db.Column(db.String(250), nullable=False)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


class BlogPost(db.Model, UserMixin):
    __tablename__ = "blog_posts"
    id: db.Mapped[int] = db.mapped_column(primary_key=True)
    author: db.Mapped["Users"] = db.relationship(back_populates="posts")
    author_id: db.Mapped[int] = db.mapped_column(db.ForeignKey("users.id"))
    post_comment: db.Mapped[List["Comment"]] = db.relationship(back_populates="parent_post")
    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)


class Comment(db.Model, UserMixin):
    __tablename__ = "comments"
    id: db.Mapped[int] = db.mapped_column(primary_key=True)
    comment_author: db.Mapped["Users"] = db.relationship(back_populates="comments")
    author_id: db.Mapped[int] = db.mapped_column(db.ForeignKey("users.id"))
    parent_post: db.Mapped["BlogPost"] = db.relationship(back_populates="post_comment")
    post_id: db.Mapped[int] = db.mapped_column(db.ForeignKey("blog_posts.id"))
    text = db.Column(db.String(250), nullable=False)


with app.app_context():
    db.create_all()


def admin_only(function):
    @wraps(function)
    def wrapper_function(*args, **kwargs):
        if current_user.get_id() == '1':
            return function(*args, **kwargs)
        else:
            flash("Login in as an admin to access that page", "error")
            return redirect(url_for('login'))

    return wrapper_function


@login_manager.user_loader
def load_user(user_id):
    return db.session.execute(db.select(Users).where(Users.id == user_id)).scalar()


@app.route('/register', methods=['POST', 'GET'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        password = generate_password_hash(request.form['password'], method='pbkdf2:sha256', salt_length=8)
        result = db.session.execute(db.select(Users).where(Users.email == form.email.data)).scalar()
        if not result:
            new_user = Users(
                email=form.email.data,
                password=password,
                name=form.name.data
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for('get_all_posts'))
        else:
            flash("Email already registered, Please Login", "error")
            return redirect(url_for('login'))
    return render_template("register.html", form=form)


@app.route('/login', methods=['POST', 'GET'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        result = db.session.execute(db.select(Users).where(Users.email == email))
        user = result.scalar()
        if user:
            if check_password_hash(user.password, form.password.data):
                login_user(user)
                return redirect(url_for('get_all_posts'))
            else:
                flash("Invalid Password, please try again", "error")
        else:
            flash("Invalid Email, please try again..", "error")
    return render_template("login.html", form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    posts = db.session.execute(db.select(BlogPost)).scalars().all()
    user = db.session.execute(db.select(Users)).scalar()
    user_id = current_user.get_id()
    admin = False
    if user_id == '1':
        admin = True
    return render_template("index.html", all_posts=posts, logged_in=current_user.is_authenticated, admin=admin, user=user)


@app.route("/post/<int:post_id>", methods=['POST', 'GET'])
def show_post(post_id):
    admin = False
    if current_user.get_id() == '1':
        admin = True
    requested_post = db.get_or_404(BlogPost, post_id)
    comments = db.session.execute(db.select(Comment).where(Comment.post_id == post_id)).scalars()
    form = CommentForm()
    if form.validate_on_submit():
        if current_user.get_id():
            new_comment = Comment(
                text=form.comment.data,
                comment_author=current_user,
                parent_post=requested_post
            )
            db.session.add(new_comment)
            db.session.commit()
            return redirect(url_for('show_post', post_id=post_id))
        else:
            flash("You need to login to be able comment", "error")
            return redirect(url_for('login'))

    return render_template("post.html", post=requested_post, form=form, admin=admin, logged_in=current_user.is_authenticated)


@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, logged_in=current_user.is_authenticated)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, logged_in=current_user.is_authenticated)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    comment_to_delete = db.session.execute(db.select(Comment).where(Comment.post_id == post_id)).scalars()
    db.session.delete(post_to_delete)
    for comment in comment_to_delete:
        db.session.delete(comment)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html", logged_in=current_user.is_authenticated)


@app.route("/contact")
def contact():
    return render_template("contact.html", logged_in=current_user.is_authenticated, user=current_user)


@app.route('/form', methods=['POST'])
def send_form():
    if current_user.get_id():
        my_email = "udemy.python.test.smtp@gmail.com"
        password = "qwnksdoiplfhyxzw"
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        msg = request.form['message']
        with smtplib.SMTP('smtp.gmail.com') as con:
            con.starttls()
            con.login(user=my_email, password=password)
            con.sendmail(from_addr=my_email, to_addrs="kirthickkumarkk2@gmail.com",
                         msg=f"Subject:Blog Message\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nMessage: {msg}")
        return render_template("form_success.html", name=name, email=email, phone=phone, msg=msg)
    else:
        flash("Login to continue", "error")
        return redirect(url_for('login'))


if __name__ == "__main__":
    app.run(debug=True, port=5002)
