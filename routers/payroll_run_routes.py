import datetime, io
from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from currency_utils import D, DECIMAL_ZERO
from fpdf import FPDF

from models import (
    PayrollRun, PayrollRunItem, Employee, CommissionEntry,
)
from services.payroll_service import PayrollService
from . import templates, get_db
import auth


def setup_payroll_run_routes(app):
    @app.get("/payroll-runs", response_class=HTMLResponse)
    def payroll_runs_page(request: Request, db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("payroll.view"))):
        runs = db.query(PayrollRun).order_by(PayrollRun.id.desc()).all()
        return templates.TemplateResponse(request, "payroll_runs.html", {
            "request": request, "page_title": "شهرية الرواتب", "active": "payroll_runs",
            "runs": runs,
        })

    @app.get("/payroll-runs/add", response_class=HTMLResponse)
    def add_payroll_run_page(request: Request, db: Session = Depends(get_db),
                             user=Depends(auth.require_permission("payroll.view"))):
        return templates.TemplateResponse(request, "payroll_run_form.html", {
            "request": request, "page_title": "إنشاء شهرية جديدة", "active": "payroll_runs",
            "run": None,
        })

    @app.post("/payroll-runs/add")
    def add_payroll_run(
        name: str = Form(...),
        period_start: str = Form(...),
        period_end: str = Form(...),
        notes: str = Form(""),
        db: Session = Depends(get_db),
        user=Depends(auth.require_permission("payroll.view")),
    ):
        ps = datetime.datetime.strptime(period_start, "%Y-%m-%d").date()
        pe = datetime.datetime.strptime(period_end, "%Y-%m-%d").date()
        svc = PayrollService(db, user)
        try:
            run = svc.create_run(name, ps, pe, notes)
            db.commit()
        except ValueError as e:
            return RedirectResponse(f"/payroll-runs?error={e}", status_code=303)
        return RedirectResponse(f"/payroll-runs/{run.id}", status_code=303)

    @app.get("/payroll-runs/{run_id}", response_class=HTMLResponse)
    def payroll_run_detail(run_id: int, request: Request, db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("payroll.view"))):
        run = db.query(PayrollRun).get(run_id)
        if not run:
            return RedirectResponse("/payroll-runs?error=not_found", status_code=303)
        items = db.query(PayrollRunItem).filter(
            PayrollRunItem.payroll_run_id == run_id
        ).order_by(PayrollRunItem.id).all()
        return templates.TemplateResponse(request, "payroll_run_detail.html", {
            "request": request, "page_title": run.name, "active": "payroll_runs",
            "run": run, "items": items,
        })

    @app.get("/payroll-runs/{run_id}/status")
    def redirect_status_get(run_id: int):
        return RedirectResponse(f"/payroll-runs/{run_id}", status_code=303)

    @app.post("/payroll-runs/{run_id}/status")
    def update_run_status(run_id: int, status: str = Form(...),
                          db: Session = Depends(get_db),
                          user=Depends(auth.require_permission("payroll.view"))):
        svc = PayrollService(db, user)
        try:
            svc.update_status(run_id, status)
            db.commit()
        except Exception as e:
            db.rollback()
            return RedirectResponse(f"/payroll-runs/{run_id}?error={e}", status_code=303)
        return RedirectResponse(f"/payroll-runs/{run_id}", status_code=303)

    @app.get("/payroll-runs/{run_id}/pdf/{item_id}")
    def payslip_pdf(run_id: int, item_id: int, db: Session = Depends(get_db),
                    user=Depends(auth.require_permission("payroll.view"))):
        item = db.query(PayrollRunItem).get(item_id)
        if not item or item.payroll_run_id != run_id:
            return RedirectResponse(f"/payroll-runs/{run_id}?error=not_found", status_code=303)
        run = item.run
        emp = item.employee
        pdf = FPDF(orientation="P", unit="mm", format="A5")
        font_dir = r"C:\Users\MG\AppData\Local\Programs\Python\Python311\Lib\site-packages\matplotlib\mpl-data\fonts\ttf"
        pdf.add_font("DejaVu", "", f"{font_dir}\\DejaVuSans.ttf")
        pdf.add_font("DejaVu", "B", f"{font_dir}\\DejaVuSans-Bold.ttf")
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()
        pdf.set_text_shaping(True)
        pw = pdf.w - 2 * pdf.l_margin

        def section_header(text, fill):
            pdf.set_fill_color(*fill)
            pdf.set_font("DejaVu", "B", 10)
            pdf.cell(pw, 7, text=text, align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

        def data_row(label, value):
            pdf.set_font("DejaVu", "", 10)
            x1 = pdf.l_margin
            x2 = pdf.l_margin + pw * 0.5
            w1 = pw * 0.5
            w2 = pw * 0.5
            pdf.set_xy(x1, pdf.get_y())
            pdf.cell(w1, 6, text=label, align="R")
            pdf.set_xy(x2, pdf.get_y())
            pdf.set_font("DejaVu", "B", 10)
            pdf.cell(w2, 6, text=value, align="L")
            pdf.ln(6)

        def total_row(label, value, color):
            pdf.set_font("DejaVu", "B", 10)
            pdf.set_text_color(*color)
            x1 = pdf.l_margin
            x2 = pdf.l_margin + pw * 0.5
            w1 = pw * 0.5
            w2 = pw * 0.5
            pdf.set_xy(x1, pdf.get_y())
            pdf.cell(w1, 6, text=label, align="R")
            pdf.set_xy(x2, pdf.get_y())
            pdf.cell(w2, 6, text=value, align="L")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(6)

        def dashed_line(y, color):
            pdf.set_draw_color(*color)
            pdf.set_line_width(0.4)
            y = pdf.get_y() if y is None else y
            pdf.line(pdf.l_margin, y, pdf.l_margin + pw, y)
            pdf.set_line_width(0.2)
            pdf.ln(1)

        pdf.set_fill_color(17, 136, 90)
        pdf.rect(0, 0, pdf.w, 22, style="F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 14)
        pdf.set_xy(0, 4)
        pdf.cell(pdf.w, 8, text="قسيمة راتب", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", "", 9)
        pdf.set_xy(0, 13)
        pdf.cell(pdf.w, 5, text=run.name, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_xy(0, 18)
        pdf.ln(22)
        pdf.set_text_color(0, 0, 0)

        pdf.set_font("DejaVu", "", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(pw, 5, text=f"الموظف: {emp.name}    |    الفترة: {run.period_start} → {run.period_end}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
        pdf.set_text_color(0, 0, 0)

        section_header("الاستحقاقات", (230, 247, 236))
        data_row("الراتب الأساسي", f"{item.basic_salary:.2f}")
        data_row("بدل سكن", f"{item.housing_allowance:.2f}")
        data_row("بدل مواصلات", f"{item.transport_allowance:.2f}")
        data_row("بدلات أخرى", f"{item.other_allowances:.2f}")
        data_row("الإضافي", f"{item.overtime_amount:.2f}")
        data_row("العمولات", f"{item.commission_amount:.2f}")
        dashed_line(None, (17, 136, 90))
        total_row("إجمالي الاستحقاق", f"{item.gross_pay:.2f}", (17, 136, 90))
        dashed_line(None, (17, 136, 90))
        pdf.ln(2)

        section_header("الخصومات", (255, 235, 238))
        data_row("خصم غياب", f"{item.absence_deduction:.2f}")
        data_row("خصم تأخير", f"{item.late_deduction:.2f}")
        data_row("سلف", f"{item.advances_deduction:.2f}")
        data_row("تأمينات", f"{item.social_insurance:.2f}")
        data_row("خصومات أخرى", f"{item.other_deductions:.2f}")
        dashed_line(None, (199, 56, 76))
        total_row("إجمالي الخصم", f"{item.total_deductions:.2f}", (199, 56, 76))
        dashed_line(None, (199, 56, 76))
        pdf.ln(3)

        pdf.set_fill_color(17, 136, 90)
        pdf.rect(pdf.l_margin, pdf.get_y(), pw, 10, style="F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_xy(pdf.l_margin, pdf.get_y())
        pdf.cell(pw, 10, text=f"صافي الراتب: {item.net_pay:.2f}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(6)

        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(pw, 4, text=f"تم الإنشاء: {datetime.date.today()}    |    نظام إدارة السياحة", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

        buf = bytes(pdf.output())
        return Response(content=buf, media_type="application/pdf",
                        headers={"Content-Disposition": f"attachment;filename=payslip_{emp.id}.pdf"})

    @app.post("/payroll-runs/{run_id}/delete")
    def delete_payroll_run(run_id: int, db: Session = Depends(get_db),
                           user=Depends(auth.require_permission("payroll.view"))):
        run = db.query(PayrollRun).get(run_id)
        if run:
            db.delete(run)
            db.commit()
        return RedirectResponse("/payroll-runs", status_code=303)



