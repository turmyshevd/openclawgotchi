"""
Simple Cron Scheduler — Lightweight task scheduling for Pi.
Uses APScheduler-style API but minimal implementation.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional, Any
from dataclasses import dataclass, field, asdict

from config import PROJECT_DIR

log = logging.getLogger(__name__)

# Jobs file
JOBS_FILE = PROJECT_DIR / "data" / "cron_jobs.json"


@dataclass
class CronJob:
    """A scheduled job."""
    id: str
    name: str
    
    # Schedule (one of these)
    interval_minutes: int = 0       # Run every N minutes
    cron_expression: str = ""       # Cron expression (not implemented yet)
    run_at: str = ""                # One-shot: ISO timestamp
    
    # What to do
    message: str = ""               # Message to send to LLM
    system_event: str = ""          # System event text
    
    # Options
    enabled: bool = True
    session: str = "main"           # "main" or "isolated"
    delete_after_run: bool = False   # For one-shot jobs
    target_chat_id: int = 0         # Send reminder to this chat (0 = use admin_id)
    
    # State
    last_run: str = ""
    next_run: str = ""
    run_count: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "CronJob":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class CronScheduler:
    """Simple cron scheduler."""
    
    def __init__(self):
        self.jobs: dict[str, CronJob] = {}
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._callbacks: dict[str, Callable] = {}
        self._load_jobs()
    
    def _load_jobs(self):
        """Load jobs from file."""
        if not JOBS_FILE.exists():
            return
        
        try:
            data = json.loads(JOBS_FILE.read_text())
            for job_data in data.get("jobs", []):
                job = CronJob.from_dict(job_data)
                self.jobs[job.id] = job
            log.info(f"Loaded {len(self.jobs)} cron jobs")
        except Exception as e:
            log.error(f"Failed to load cron jobs: {e}")
    
    def _save_jobs(self):
        """Save jobs to file."""
        JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            data = {"jobs": [job.to_dict() for job in self.jobs.values()]}
            JOBS_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.error(f"Failed to save cron jobs: {e}")
    
    def add_job(self, job: CronJob) -> CronJob:
        """Add a new job."""
        now = datetime.now()
        # Calculate next run
        if job.interval_minutes > 0:
            job.next_run = (now + timedelta(minutes=job.interval_minutes)).isoformat()
        elif job.run_at:
            job.next_run = job.run_at
        
        self.jobs[job.id] = job
        self._save_jobs()
        log.info(f"Added cron job: {job.name} ({job.id})")
        if job.delete_after_run and job.next_run:
            log.info(f"One-shot scheduled: next_run={job.next_run!r} (now={now.isoformat()!r})")
        return job
    
    def remove_job(self, job_id_or_name: str) -> bool:
        """Remove a job by id or by name."""
        if job_id_or_name in self.jobs:
            del self.jobs[job_id_or_name]
            self._save_jobs()
            log.info(f"Removed cron job: {job_id_or_name}")
            return True
        for jid, job in list(self.jobs.items()):
            if job.name == job_id_or_name:
                del self.jobs[jid]
                self._save_jobs()
                log.info(f"Removed cron job by name: {job.name} ({jid})")
                return True
        return False
    
    def get_job(self, job_id: str) -> Optional[CronJob]:
        """Get a job by ID."""
        return self.jobs.get(job_id)
    
    def list_jobs(self) -> list[CronJob]:
        """List all jobs."""
        return list(self.jobs.values())
    
    def on_job_run(self, callback: Callable[[CronJob], Any]):
        """Register callback for when a job runs."""
        self._callbacks["job_run"] = callback
    
    async def _check_jobs(self):
        """Check and run due jobs."""
        now = datetime.now()
        
        for job in list(self.jobs.values()):
            if not job.enabled:
                continue
            
            if not job.next_run:
                continue
            
            try:
                next_run = datetime.fromisoformat(job.next_run)
            except (ValueError, TypeError) as e:
                log.warning(f"Cron job {job.name} ({job.id}): invalid next_run {job.next_run!r}: {e}")
                continue
            
            if now >= next_run:
                # Job is due
                log.info(f"Running cron job: {job.name}")
                
                # Run callback
                callback = self._callbacks.get("job_run")
                if callback:
                    try:
                        result = callback(job)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        log.error(f"Cron job error ({job.name}): {e}")
                
                # Update state
                job.last_run = now.isoformat()
                job.run_count += 1
                
                # Calculate next run
                if job.delete_after_run:
                    self.remove_job(job.id)
                elif job.interval_minutes > 0:
                    job.next_run = (now + timedelta(minutes=job.interval_minutes)).isoformat()
                else:
                    job.enabled = False  # One-shot, disable
                
                self._save_jobs()
    
    async def _run_loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_jobs()
            except Exception as e:
                log.error(f"Scheduler error: {e}")
            
            # Check every 30s so one-shot reminders run within ~30s of due time
            await asyncio.sleep(30)
    
    def start(self):
        """Start the scheduler."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        log.info("Cron scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        log.info("Cron scheduler stopped")


# Global scheduler instance
_scheduler: Optional[CronScheduler] = None


def get_scheduler() -> CronScheduler:
    """Get or create the global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler


# ============================================================
# CLI-like functions
# ============================================================

def add_cron_job(
    name: str,
    message: str = "",
    interval_minutes: int = 0,
    run_at: str = "",
    delete_after_run: bool = False,
    target_chat_id: int = 0
) -> CronJob:
    """
    Add a cron job.
    
    Examples:
        # Every 30 minutes
        add_cron_job("Check email", message="Check inbox", interval_minutes=30)
        
        # One-shot in 20 minutes
        add_cron_job("Reminder", message="Call back", run_at="20m", delete_after_run=True)
    """
    import uuid
    
    # Parse run_at shortcuts (e.g. "15s", "2m", "0.25m", "1h")
    if run_at:
        now = datetime.now()
        if run_at.endswith("s"):
            sec = int(run_at[:-1])
            run_at = (now + timedelta(seconds=sec)).isoformat()
        elif run_at.endswith("m"):
            minutes = float(run_at[:-1])
            run_at = (now + timedelta(minutes=minutes)).isoformat()
        elif run_at.endswith("h"):
            hours = float(run_at[:-1])
            run_at = (now + timedelta(hours=hours)).isoformat()
    
    job = CronJob(
        id=str(uuid.uuid4())[:8],
        name=name,
        message=message,
        interval_minutes=interval_minutes,
        run_at=run_at,
        delete_after_run=delete_after_run,
        target_chat_id=target_chat_id,
    )
    
    return get_scheduler().add_job(job)


def list_cron_jobs() -> list[CronJob]:
    """List all cron jobs."""
    return get_scheduler().list_jobs()


def remove_cron_job(job_id: str) -> bool:
    """Remove a cron job."""
    return get_scheduler().remove_job(job_id)
