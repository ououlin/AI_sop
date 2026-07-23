from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from db_models import SOPDefinitionDB


class SOPRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[SOPDefinitionDB]:
        return self.db.query(SOPDefinitionDB).order_by(SOPDefinitionDB.created_at.desc()).all()

    def get_by_name(self, name: str) -> Optional[SOPDefinitionDB]:
        return self.db.query(SOPDefinitionDB).filter(SOPDefinitionDB.name == name).first()

    def get_by_id(self, sop_id: int) -> Optional[SOPDefinitionDB]:
        return self.db.query(SOPDefinitionDB).filter(SOPDefinitionDB.id == sop_id).first()

    def create(self, name: str, steps_json: str, version: str = "1.0") -> SOPDefinitionDB:
        existing = self.get_by_name(name)
        if existing:
            existing.steps_json = steps_json
            existing.version = version
            existing.updated_at = datetime.now()
            self.db.commit()
            self.db.refresh(existing)
            return existing

        sop = SOPDefinitionDB(
            name=name,
            steps_json=steps_json,
            version=version,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.db.add(sop)
        self.db.commit()
        self.db.refresh(sop)
        return sop

    def delete(self, sop_id: int) -> bool:
        sop = self.get_by_id(sop_id)
        if sop:
            self.db.delete(sop)
            self.db.commit()
            return True
        return False