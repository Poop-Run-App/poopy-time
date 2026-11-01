from app import db


class Bathroom(db.Model):
    __tablename__ = 'bathrooms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(255))
    latitude = db.Column(db.Float, nullable=False, index=True)
    longitude = db.Column(db.Float, nullable=False, index=True)
    # Hours of the day (0-24). Both null means open 24 hours, unless
    # hours_note is set (hours we couldn't turn into a simple range).
    open_hour = db.Column(db.Integer)
    close_hour = db.Column(db.Integer)
    hours_note = db.Column(db.String(255))
    is_accessible = db.Column(db.Boolean, default=False, nullable=False)
    notes = db.Column(db.Text)
    # 'user' for bathrooms added in the app, 'osm' for OpenStreetMap imports
    source = db.Column(db.String(20), nullable=False, default='user', server_default='user')
    osm_id = db.Column(db.String(40), unique=True)  # e.g. "node/123", used to update on re-import
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'open_hour': self.open_hour,
            'close_hour': self.close_hour,
            'hours_note': self.hours_note,
            'is_accessible': self.is_accessible,
            'notes': self.notes,
            'source': self.source,
        }
