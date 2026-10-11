"""Read-only PPA GIS queries.

PostgreSQL + PostGIS: indexed ST_DWithin distance filtering in metres.
SQLite (local tests): bounding-box approximation, with Python geodesic
filtering on returned results. No geolocation is taken automatically.
"""
from math import asin, cos, radians, sin, sqrt, isfinite
from sqlalchemy import text, or_

from app.extensions import db
from app.models.ppa import PPA, PPA_SECTORS
from app.models.platoon import NYSC_STATES


def valid_near(lat, lng, radius_km):
    return (
        lat is not None and lng is not None and radius_km is not None
        and all(isfinite(v) for v in (lat, lng, radius_km))
        and -90 <= lat <= 90 and -180 <= lng <= 180
        and 1 <= radius_km <= 100
    )


def haversine_km(lat1, lon1, lat2, lon2):
    a = (sin(radians(lat2 - lat1) / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2))
         * sin(radians(lon2 - lon1) / 2) ** 2)
    return 12742.0 * asin(min(1.0, sqrt(a)))


def lookup_query(q="", state="", sector="", lat=None, lng=None, radius_km=None):
    query = PPA.query.filter_by(status="verified")
    if q:
        # Limit user input to bound SQL work. SQLAlchemy binds all user text.
        term = "%" + q[:80].strip() + "%"
        query = query.filter(or_(PPA.name.ilike(term), PPA.lga.ilike(term),
                                 PPA.town.ilike(term)))
    if state in NYSC_STATES:
        query = query.filter(PPA.state == state)
    if sector in dict(PPA_SECTORS):
        query = query.filter(PPA.sector == sector)

    near = valid_near(lat, lng, radius_km)
    if near:
        if db.engine.dialect.name == "postgresql":
            # Explicitly limit the query to reviewed institutional pins.
            query = query.filter(PPA.latitude.isnot(None), PPA.longitude.isnot(None))
            query = query.filter(text(
                "ST_DWithin("
                "ST_SetSRID(ST_MakePoint(ppas.longitude, ppas.latitude),4326)::geography,"
                "ST_SetSRID(ST_MakePoint(:near_lon, :near_lat),4326)::geography,"
                ":near_metres)"
            )).params(near_lon=lng, near_lat=lat, near_metres=radius_km * 1000)
        else:
            # SQLite is only used for local tests. Bounding box first,
            # exact spherical distance checked by filter_local_near().
            degrees_lat = radius_km / 110.5
            longitude_scale = max(abs(cos(radians(lat))), 0.02)
            degrees_lon = radius_km / (111.32 * longitude_scale)
            query = query.filter(
                PPA.latitude.between(lat - degrees_lat, lat + degrees_lat),
                PPA.longitude.between(lng - degrees_lon, lng + degrees_lon),
            )
    return query


def filter_local_near(rows, lat, lng, radius_km):
    if not valid_near(lat, lng, radius_km):
        return rows
    if db.engine.dialect.name == "postgresql":
        return rows
    return [row for row in rows if row.has_location and
            haversine_km(lat, lng, row.latitude, row.longitude) <= radius_km]


def public_feature(ppa):
    """Only reviewed PPAs with workplace coordinates appear on the map."""
    if ppa.status != "verified" or not ppa.has_location:
        return None
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [ppa.longitude, ppa.latitude]},
        "properties": {
            "id": ppa.id,
            "name": ppa.name,
            "state": ppa.state,
            "lga": ppa.lga,
            "sector": ppa.sector_label,
        },
    }
