"""State Machine Transition routes for Reservations."""

from urllib.parse import quote
from fastapi import Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from models import Reservation, StateLog
from . import templates, get_db
import auth
from state_machine import apply_transition, allowed_transitions, STATES, STATE_LABELS_AR, STATE_LABELS_EN, STATE_COLORS


def setup_transition_routes(app):
    @app.post("/reservations/{reservation_id}/transition/{to_state}")
    def reservation_transition(reservation_id: int, to_state: str, request: Request,
                               reason: str = Form(""),
                               db: Session = Depends(get_db),
                               user=Depends(auth.require_permission("reservations.edit"))):
        r = db.query(Reservation).get(reservation_id)
        if not r:
            return RedirectResponse("/reservations", status_code=303)

        # Check if the specific transition requires a different permission
        from state_machine import TRANSITIONS
        required_perm = "reservations.edit"
        for t in TRANSITIONS:
            if t.from_state == r.status and t.to_state == to_state:
                required_perm = t.permission
                break
        if not auth.has_permission(user, required_perm):
            return templates.TemplateResponse(request, "403.html", {"request": request}, status_code=403)

        ok, msg = apply_transition(r, to_state, db, user, reason=reason)
        if not ok:
            return RedirectResponse(f"/reservations/{reservation_id}/edit?error={quote(msg)}", status_code=303)
        return RedirectResponse(f"/reservations/{reservation_id}/edit?success={quote(msg or 'ok')}", status_code=303)

    @app.get("/reservations/{reservation_id}/transitions", response_class=HTMLResponse)
    def reservation_transitions_json(reservation_id: int, request: Request,
                                     db: Session = Depends(get_db),
                                     user=Depends(auth.require_permission("reservations.view"))):
        """Return allowed transitions as HTML snippet for embedding."""
        r = db.query(Reservation).get(reservation_id)
        if not r:
            return ""
        transitions = allowed_transitions(r)
        if not transitions:
            return ""
        html = '<div class="transition-bar">'
        for t in transitions:
            label = t.label_ar if request.cookies.get("lang", "en") == "ar" else t.label_en
            cls = "primary" if t.to_state in ("confirmed", "completed") else ("danger" if t.to_state == "cancelled" else "ghost")
            html += f'<form method="post" action="/reservations/{reservation_id}/transition/{t.to_state}" style="display:inline">'
            if t.require_reason:
                html += f'<input name="reason" placeholder="السبب / Reason" required style="display:none" class="reason-input-{t.to_state}">'
            html += f'<button type="submit" class="btn btn-{cls}" onclick="return confirmTransition(\'{t.to_state}\', {str(t.require_reason).lower()})">{label}</button>'
            html += '</form>'
        html += '</div>'
        return HTMLResponse(html)

    @app.get("/reservations/{reservation_id}/timeline", response_class=HTMLResponse)
    def reservation_timeline(reservation_id: int, request: Request,
                             db: Session = Depends(get_db),
                             user=Depends(auth.require_permission("reservations.view"))):
        """Return timeline HTML snippet."""
        logs = db.query(StateLog).filter(
            StateLog.reservation_id == reservation_id
        ).order_by(StateLog.timestamp.desc()).all()
        lang = "ar" if request.cookies.get("lang", "en") == "ar" else "en"
        if not logs:
            return HTMLResponse('<div class="tl-empty">' +
                                ('لا توجد أحداث بعد' if lang == 'ar' else 'No events yet') +
                                '</div>')

        html = '<div class="tl-list">'
        for log in logs:
            ts = log.timestamp.strftime("%Y-%m-%d %H:%M") if log.timestamp else ""
            from_lbl = STATE_LABELS_AR.get(log.from_state, log.from_state) if lang == "ar" else STATE_LABELS_EN.get(log.from_state, log.from_state)
            to_lbl = STATE_LABELS_AR.get(log.to_state, log.to_state) if lang == "ar" else STATE_LABELS_EN.get(log.to_state, log.to_state)
            arrow = " → " if lang == "en" else " ← "
            html += f'<div class="tl-item">'
            html += f'<div class="tl-marker" style="background:{STATE_COLORS.get(log.to_state, "neutral")}"></div>'
            html += f'<div class="tl-body">'
            html += f'<div class="tl-head"><strong>{from_lbl}</strong>{arrow}<strong>{to_lbl}</strong> <span class="tl-trans">{log.transition}</span></div>'
            html += f'<div class="tl-meta">{ts} — {log.username or "?"}'
            if log.reason:
                html += f' <span class="tl-reason">({log.reason})</span>'
            html += f'</div>'
            html += f'</div></div>'
        html += '</div>'
        return HTMLResponse(html)
