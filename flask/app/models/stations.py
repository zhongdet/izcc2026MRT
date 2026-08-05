from typing import Optional

from . import db

class Stations(db.Model):
    __tablename__ = "stations"
    
    id = db.Column(db.Integer, primary_key=True)
    
    name = db.Column(db.String(64), unique=True, nullable=False)
    is_special = db.Column(db.Boolean, nullable=False)
    hidden = db.Column(db.Boolean, default=False)
    owner_team = db.Column(db.String(32), nullable=True)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    
    def __init__(self, name: str, is_special: bool, hidden: bool=False, owner_team: Optional[str]=None) -> None:
        self.name: str = name
        self.hidden: bool = hidden
        self.is_special: bool = is_special
        self.owner_team: Optional[str] = owner_team
    
    def __repr__(self):
        return f"<Station {self.name}, Special: {self.is_special}, Hidden: {self.hidden}, Owner: {self.owner_team}>"
