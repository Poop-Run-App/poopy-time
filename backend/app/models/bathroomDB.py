from app import db


class Bathroom(db.Model):
    __tablename__ = 'bathrooms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(255))
    latitude = db.Column(db.Float, nullable=False, index=True)
    longitude = db.Column(db.Float, nullable=False, index=True)
    # Hours of the day (0-24, 17.5 = 5:30pm). Both null means open 24 hours,
    # unless hours_note is set (hours we couldn't turn into a simple range).
    open_hour = db.Column(db.Float)
    close_hour = db.Column(db.Float)
    hours_note = db.Column(db.String(255))
    is_accessible = db.Column(db.Boolean, default=False, nullable=False)
    # 'unisex', 'separate' (men's and women's rooms), 'men' or 'women'; null if unknown
    gender = db.Column(db.String(20))
    notes = db.Column(db.Text)
    # 'open', 'closed' or 'limited' when a source reports it; null if unknown
    status = db.Column(db.String(20))
    status_reason = db.Column(db.String(100))
    # 'user' for bathrooms added in the app, 'osm' for OpenStreetMap imports,
    # 'seattle_parks' for Seattle Parks restrooms that OSM doesn't have,
    # 'sheet' for bathrooms that came from a team tracking sheet
    source = db.Column(db.String(20), nullable=False, default='user', server_default='user')
    osm_id = db.Column(db.String(40), unique=True)  # e.g. "node/123", used to update on re-import
    # Seattle Parks asset ID (e.g. "RESTROOM-SCCS"), set on any bathroom matched to the city's data
    city_id = db.Column(db.String(40), unique=True)
    # Edited by the team in a tracking sheet; the OSM and Seattle Parks
    # imports then leave its details alone
    curated = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())
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
            'gender': self.gender,
            'notes': self.notes,
            'status': self.status,
            'status_reason': self.status_reason,
            'source': self.source,
        }
