"""
Minimal app factory used ONLY to smoke-test the new layered structure
end-to-end (DB -> repo -> service -> API router) before wiring it into
the real app/main.py. Run: uvicorn app.smoke_test_app:app --reload
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.database import Base, engine
from app.routers.api.v1 import customers
from app.core.exceptions import NotFoundError, DuplicateError, ValidationError, JournalImbalanceError

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Tourism ERP API - smoke test")
app.include_router(customers.router, prefix="/api/v1")


# ---- ONE central place mapping domain exceptions -> HTTP responses ----
# Services raise plain Python exceptions; routers never know about HTTP codes.
@app.exception_handler(NotFoundError)
def handle_not_found(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(DuplicateError)
def handle_duplicate(request: Request, exc: DuplicateError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
def handle_validation(request: Request, exc: ValidationError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(JournalImbalanceError)
def handle_imbalance(request: Request, exc: JournalImbalanceError):
    return JSONResponse(status_code=500, content={"detail": f"Ledger integrity error: {exc}"})
