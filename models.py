from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Offer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    price = db.Column(db.Float, nullable=False)
    olx_link = db.Column(db.String(500), nullable=False)
    emag_price = db.Column(db.Float)
    emag_link = db.Column(db.String(500))
    discount_percentage = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(100))
    location = db.Column(db.String(200))
    image_url = db.Column(db.String(500))

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'price': self.price,
            'olx_link': self.olx_link,
            'emag_price': self.emag_price,
            'emag_link': self.emag_link,
            'discount_percentage': self.discount_percentage,
            'created_at': self.created_at.isoformat(),
            'category': self.category,
            'location': self.location,
            'image_url': self.image_url
        } 