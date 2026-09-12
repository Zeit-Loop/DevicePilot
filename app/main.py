from collections.abc import AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager

from ipaddress import ip_address

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app import models, schemas
from app.config import Settings
from app.database import Base, SessionLocal, engine as default_engine
from app.rate_limit import InMemoryRateLimiter
from app.services.diagnosis import (
    DiagnosisAuthenticationError,
    DiagnosisCallable,
    DiagnosisCompatibilityError,
    DiagnosisConfigurationError,
    DiagnosisInvalidResponseError,
    DiagnosisRateLimitError,
    DiagnosisUnavailableError,
    diagnose_device,
)


def create_app(
    session_factory: sessionmaker[Session] = SessionLocal,
    engine: Engine = default_engine,
    diagnosis_service: DiagnosisCallable | None = None,
    diagnosis_limiter: InMemoryRateLimiter | None = None,
    cors_origins: tuple[str, ...] | None = None,
    trust_proxy_headers: bool | None = None,
) -> FastAPI:
    settings = Settings.from_environment()
    Base.metadata.create_all(bind=engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if settings.auto_seed_demo:
            from scripts.seed_demo import seed_demo_data

            seed_demo_data(session_factory)
        yield

    app = FastAPI(
        title="DevicePilot API",
        version="0.1.0",
        docs_url=None if settings.production else "/docs",
        redoc_url=None if settings.production else "/redoc",
        openapi_url=None if settings.production else "/openapi.json",
        lifespan=lifespan,
    )
    allowed_origins = settings.cors_origins if cors_origins is None else cors_origins
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def get_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    SessionDependency = Depends(get_session)
    run_diagnosis = diagnosis_service or diagnose_device
    use_default_diagnosis = diagnosis_service is None
    limiter = diagnosis_limiter or InMemoryRateLimiter(
        limit=settings.diagnosis_rate_limit_per_minute, window_seconds=60
    )
    use_proxy_headers = (
        settings.trust_proxy_headers
        if trust_proxy_headers is None
        else trust_proxy_headers
    )

    def client_identifier(request: Request) -> str:
        if use_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
            if forwarded:
                try:
                    return str(ip_address(forwarded))
                except ValueError:
                    pass
        return request.client.host if request.client else "unknown"

    def find_device(device_id: int, db: Session) -> models.Device:
        device = db.get(models.Device, device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return device

    @app.get("/health/live")
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def readiness() -> JSONResponse:
        try:
            with session_factory() as session:
                session.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not ready"})
        return JSONResponse(content={"status": "ready"})

    @app.post("/devices", response_model=schemas.DeviceRead, status_code=status.HTTP_201_CREATED)
    def create_device(payload: schemas.DeviceCreate, db: Session = SessionDependency):
        device = models.Device(**payload.model_dump(mode="json"))
        db.add(device)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail="Serial number already exists") from exc
        db.refresh(device)
        return device

    @app.get("/devices", response_model=list[schemas.DeviceRead])
    def list_devices(db: Session = SessionDependency):
        return db.scalars(select(models.Device).order_by(models.Device.id)).all()

    @app.get("/devices/{device_id}", response_model=schemas.DeviceRead)
    def get_device(device_id: int, db: Session = SessionDependency):
        return find_device(device_id, db)

    @app.post(
        "/devices/{device_id}/diagnose", response_model=schemas.DiagnosisResult
    )
    def diagnose(
        device_id: int,
        payload: schemas.DiagnosisRequest,
        request: Request,
        db: Session = SessionDependency,
    ):
        device = find_device(device_id, db)
        if not limiter.allow(client_identifier(request)):
            raise HTTPException(
                status_code=429, detail="AI diagnosis rate limit exceeded"
            )
        try:
            if use_default_diagnosis:
                return diagnose_device(device, payload.description, db)
            return run_diagnosis(device, payload.description)
        except DiagnosisConfigurationError as exc:
            raise HTTPException(
                status_code=503, detail="AI diagnosis is not configured"
            ) from exc
        except DiagnosisAuthenticationError as exc:
            raise HTTPException(
                status_code=502, detail="AI provider authentication failed"
            ) from exc
        except DiagnosisRateLimitError as exc:
            raise HTTPException(
                status_code=503, detail="AI diagnosis capacity is temporarily unavailable"
            ) from exc
        except DiagnosisInvalidResponseError as exc:
            raise HTTPException(
                status_code=502, detail="AI provider returned an invalid response"
            ) from exc
        except DiagnosisCompatibilityError as exc:
            raise HTTPException(
                status_code=502,
                detail="Configured AI provider is not compatible with structured diagnosis",
            ) from exc
        except DiagnosisUnavailableError as exc:
            raise HTTPException(
                status_code=503, detail="AI diagnosis is temporarily unavailable"
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="AI diagnosis is temporarily unavailable"
            ) from exc

    @app.put("/devices/{device_id}", response_model=schemas.DeviceRead)
    def update_device(
        device_id: int, payload: schemas.DeviceUpdate, db: Session = SessionDependency
    ):
        device = find_device(device_id, db)
        for field, value in payload.model_dump(mode="json").items():
            setattr(device, field, value)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail="Serial number already exists") from exc
        db.refresh(device)
        return device

    @app.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_device(device_id: int, db: Session = SessionDependency) -> Response:
        device = find_device(device_id, db)
        db.delete(device)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/devices/{device_id}/faults",
        response_model=schemas.FaultRead,
        status_code=status.HTTP_201_CREATED,
    )
    def create_fault(
        device_id: int, payload: schemas.FaultCreate, db: Session = SessionDependency
    ):
        find_device(device_id, db)
        fault = models.Fault(device_id=device_id, **payload.model_dump(mode="json"))
        db.add(fault)
        db.commit()
        db.refresh(fault)
        return fault

    @app.get("/devices/{device_id}/faults", response_model=list[schemas.FaultRead])
    def list_device_faults(device_id: int, db: Session = SessionDependency):
        find_device(device_id, db)
        statement = select(models.Fault).where(models.Fault.device_id == device_id).order_by(models.Fault.id)
        return db.scalars(statement).all()

    @app.get("/faults/{fault_id}", response_model=schemas.FaultRead)
    def get_fault(fault_id: int, db: Session = SessionDependency):
        fault = db.get(models.Fault, fault_id)
        if fault is None:
            raise HTTPException(status_code=404, detail="Fault not found")
        return fault

    @app.patch("/faults/{fault_id}", response_model=schemas.FaultRead)
    def update_fault_status(
        fault_id: int, payload: schemas.FaultStatusUpdate, db: Session = SessionDependency
    ):
        fault = get_fault(fault_id, db)
        fault.status = payload.status.value
        try:
            db.commit()
            db.refresh(fault)
        except SQLAlchemyError:
            db.rollback()
            raise
        return fault

    @app.delete("/faults/{fault_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_fault(fault_id: int, db: Session = SessionDependency) -> Response:
        fault = get_fault(fault_id, db)
        try:
            db.delete(fault)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_app()
