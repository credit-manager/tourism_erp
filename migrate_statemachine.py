"""Migration: Create state_logs table and migrate existing reservation statuses."""
from models import SessionLocal, Base, StateLog, Reservation
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, text
from state_machine import migrate_status

db = SessionLocal()

# Create state_logs table
try:
    StateLog.__table__.create(db.get_bind())
    print("Created state_logs table")
except Exception as e:
    print(f"state_logs table may already exist: {e}")

# Migrate existing reservations: map old statuses to new state machine states
reservations = db.query(Reservation).all()
migrated = 0
for r in reservations:
    new_status = migrate_status(r.status)
    if new_status != r.status:
        print(f"  R{r.id}: {r.status} -> {new_status}")
        r.status = new_status
        migrated += 1
        # Log the migration
        db.add(StateLog(
            reservation_id=r.id,
            from_state=r.status,
            to_state=new_status,
            transition="ترحيل / Migration",
            username="system",
            reason="ترحيل آلي للحالات / Automatic status migration",
        ))

db.commit()
print(f"Migrated {migrated} reservations")
db.close()
