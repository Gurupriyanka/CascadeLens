from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel

class Layer(str, Enum):
    INGESTION = "ingestion"
    CURATION = "curation"
    SEMANTIC = "semantic"

class RunStatus(str, Enum):
    SUCCESS = "Succeeded"
    FAILED = "Failed"
    OTHER = "other"     # running, cancelled, skipped

class LogRecord(BaseModel):
    layer: Layer
    run_id: str
    pipeline_name: str
    unit_name: str                       # activity or script name
    status: RunStatus
    error_message: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None  # NULL on some failures
    rows_written: Optional[int] = None
    attempt: int = 1
    source_type: Optional[str] = None
    source_name: Optional[str] = None
    reference_source_name: Optional[str] = None
    target_type: Optional[str] = None
    target_delta_table: Optional[str] = None