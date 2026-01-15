from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    course_history = db.Column(db.Text, default="[]") # JSON string of taken courses
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    chats = db.relationship('Chat', backref='user', lazy=True)

    def set_history(self, history_list):
        self.course_history = json.dumps(history_list)

    def get_history(self):
        try:
            return json.loads(self.course_history)
        except:
            return []

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), default="New Chat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = db.relationship('Message', backref='chat', cascade="all, delete", lazy=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'user' or 'ai'
    content = db.Column(db.Text, nullable=False)
    meta_data = db.Column(db.Text, nullable=True) # JSON for schedule data
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def get_meta(self):
        if self.meta_data:
            try:
                return json.loads(self.meta_data)
            except:
                return None
        return None