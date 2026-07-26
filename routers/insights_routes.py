from fastapi import Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from routers import templates, get_db
import auth
from services.insights_service import InsightsService


def setup_insights_routes(app):
    @app.get("/insights", response_class=HTMLResponse)
    def insights_page(request: Request, db: Session = Depends(get_db),
                      user=Depends(auth.require_permission("reports.view"))):
        svc = InsightsService(db)
        duplicates = svc.all_duplicate_alerts()
        forecast = svc.cash_flow_forecast(weeks_ahead=8)
        return templates.TemplateResponse(request, "insights.html", {
            "request": request, "page_title": "التحليلات الذكية - Insights", "active": "insights",
            "duplicates": duplicates, "forecast": forecast,
        })
