from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from db_models import SOPDefinitionDB
from tenancy.context import get_tenant_id


class SOPRepository:
    """SOP 访问层。

    SOP 名称在租户内唯一：不同租户可以各自拥有同名工序。
    """

    def __init__(self, db: Session, tenant_id: Optional[int] = None):
        self.db = db
        self.tenant_id = int(tenant_id) if tenant_id is not None else get_tenant_id()

    def _scoped(self):
        return self.db.query(SOPDefinitionDB).filter(
            SOPDefinitionDB.tenant_id == self.tenant_id
        )

    def get_all(self) -> List[SOPDefinitionDB]:
        return self._scoped().order_by(SOPDefinitionDB.created_at.desc()).all()

    def get_by_name(self, name: str) -> Optional[SOPDefinitionDB]:
        return self._scoped().filter(SOPDefinitionDB.name == name).first()

    def get_by_id(self, sop_id: int) -> Optional[SOPDefinitionDB]:
        return self._scoped().filter(SOPDefinitionDB.id == sop_id).first()

    def create(
        self,
        name: str,
        steps_json: str,
        version: str = "1.0",
        standard_cycle_sec=None,
    ) -> SOPDefinitionDB:
        existing = self.get_by_name(name)
        if existing:
            existing.steps_json = steps_json
            existing.version = version
            existing.standard_cycle_sec = standard_cycle_sec
            existing.updated_at = datetime.now()
            self.db.commit()
            self.db.refresh(existing)
            return existing

        sop = SOPDefinitionDB(
            tenant_id=self.tenant_id,
            name=name,
            steps_json=steps_json,
            version=version,
            standard_cycle_sec=standard_cycle_sec,
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
