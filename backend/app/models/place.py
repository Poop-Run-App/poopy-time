from app import db


class Place(db.Model):
    """Merged bathroom (or, later, fountain) the app can display."""

    __tablename__ = 'places'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(32), nullable=False, index=True)
    # Stable identity of the winning source row, e.g. "nyc_opendata:<hash>" or "osm:node/123".
    owner_key = db.Column(db.String(512), unique=True, nullable=False)
    display_name = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    hours = db.Column(db.Text)
    notes = db.Column(db.Text)
    status = db.Column(db.String(32))
    seasonal = db.Column(db.Text)
    wheelchair = db.Column(db.String(32))
    operator = db.Column(db.Text)
    location_type = db.Column(db.Text)
    changing_table = db.Column(db.Text)
    fee = db.Column(db.Text)
    website = db.Column(db.Text)
    restroom_type = db.Column(db.Text)
    primary_source = db.Column(db.String(64), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    source_records = db.relationship('SourceRecord', back_populates='place')


class SourceRecord(db.Model):
    """One upstream row. Upsert key is (source, external_id)."""

    __tablename__ = 'source_records'
    __table_args__ = (
        db.UniqueConstraint('source', 'external_id', name='uq_source_records_source_external_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(64), nullable=False, index=True)
    external_id = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(32), nullable=False, index=True)
    place_id = db.Column(db.Integer, db.ForeignKey('places.id', ondelete='SET NULL'), index=True)
    match_distance_m = db.Column(db.Float)
    name = db.Column(db.Text)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    hours = db.Column(db.Text)
    notes = db.Column(db.Text)
    status = db.Column(db.String(32))
    seasonal = db.Column(db.Text)
    wheelchair = db.Column(db.String(32))
    operator = db.Column(db.Text)
    location_type = db.Column(db.Text)
    changing_table = db.Column(db.Text)
    fee = db.Column(db.Text)
    website = db.Column(db.Text)
    restroom_type = db.Column(db.Text)
    raw = db.Column(db.JSON)
    active = db.Column(db.Boolean, nullable=False, default=True)
    fetched_at = db.Column(db.DateTime)

    place = db.relationship('Place', back_populates='source_records')
