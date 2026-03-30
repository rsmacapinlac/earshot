"""Local persistence: SQLite + recording directory layout."""

from earshot.storage.db import (
    connect,
    init_schema,
    insert_recording_pending,
    list_recordings_needing_processing,
    list_uploads_pending,
    log_event,
    mark_processing_complete,
    mark_processing_failed,
    mark_processing_started,
    reset_stale_processing,
    update_upload_states,
)
from earshot.storage.disk import disk_usage_percent, is_over_disk_threshold
from earshot.storage.paths import (
    database_path,
    new_recording_stamp,
    recording_directory,
    recordings_root,
    tmp_dir,
)

__all__ = [
    "connect",
    "database_path",
    "disk_usage_percent",
    "init_schema",
    "insert_recording_pending",
    "is_over_disk_threshold",
    "list_recordings_needing_processing",
    "list_uploads_pending",
    "log_event",
    "mark_processing_complete",
    "mark_processing_failed",
    "mark_processing_started",
    "new_recording_stamp",
    "recording_directory",
    "recordings_root",
    "reset_stale_processing",
    "tmp_dir",
    "update_upload_states",
]
