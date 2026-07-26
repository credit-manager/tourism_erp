from fastapi import Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from models import Reservation
from . import templates, get_db
from services.reconciliation_service import ReconciliationService
import auth


def setup_reconciliation_routes(app):
    @app.get("/reconciliation/report", response_class=HTMLResponse)
    def reconciliation_report(request: Request, db: Session = Depends(get_db),
                              user=Depends(auth.require_permission("reports.view"))):
        svc = ReconciliationService(db)
        discrepancies = svc.all_discrepancies()
        supplier_report = svc.supplier_balance_report()
        fixed_ids = []

        if request.query_params.get("fix") == "all":
            for d in discrepancies:
                r = db.query(Reservation).get(d["reservation_id"])
                if r:
                    svc.fix(r)
                    fixed_ids.append(d["reservation_id"])
            db.commit()
            discrepancies = svc.all_discrepancies()

        return templates.TemplateResponse(request, "reconciliation_report.html", {
            "discrepancies": discrepancies,
            "supplier_report": supplier_report,
            "count": len(discrepancies),
            "supplier_diff_count": len(supplier_report),
            "fixed_count": len(fixed_ids),
            "active": "reconciliation",
        })
