from fastapi import Request
from fastapi.responses import JSONResponse

from app import app
from enrollment_api import EnrollmentRequest, add_agent_auth_middleware, enroll

add_agent_auth_middleware(app)


@app.post("/v1/enroll")
def enroll_agent(request: Request, body: EnrollmentRequest):
    return enroll(request, body)


@app.get("/v1/enrollment/status")
def enrollment_status():
    import os
    return {"enabled": bool(os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN"))}
