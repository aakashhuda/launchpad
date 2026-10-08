def enqueue_job(job_name: str, payload: dict) -> dict:
    return {"job_name": job_name, "payload": payload, "status": "queued"}
