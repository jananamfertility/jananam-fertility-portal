from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import StaffUser, get_current_staff
from .config import get_settings
from .routers import appointments, marketing, patients, providers, reports, staff, webhooks

settings = get_settings()

app = FastAPI(
    title="Jananam Fertility Centre — Booking API",
    version="1.0.0",
    description=(
        "Appointment booking API backed by Supabase. Front-office staff "
        "authenticate via Supabase Auth on the React app; this API verifies "
        "their session and manages patients/providers/appointments. "
        "/api/webhooks/whatsapp is a phase-2 stub, wired but inactive until "
        "WhatsApp credentials are configured."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients.router)
app.include_router(providers.router)
app.include_router(appointments.router)
app.include_router(webhooks.router)
app.include_router(staff.router)
app.include_router(reports.router)
app.include_router(marketing.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/api/me", response_model=StaffUser, tags=["auth"])
def me(staff: StaffUser = Depends(get_current_staff)):
    """Lets the frontend know who's logged in and whether they're an admin."""
    return staff
