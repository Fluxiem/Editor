#!/usr/bin/env python3
"""Build a status patch for a Cutting Room Inbox job card.

Usage: job_status.py JOB_JSON STATUS PROGRESS "STEP TEXT" [OUT.json]
  JOB_JSON  the job doc as last read (ArtifactData get/query with out_dir); its log is kept
Writes OUT.json (default: <JOB_JSON dir>/patch.json) to send with ArtifactData `update`,
and updates JOB_JSON's log in place so the next patch appends to it.

Statuses the page knows: queued, downloading, cutting, captions, rendering, qa, done,
needs-input, failed.
"""
import datetime, json, pathlib, sys

STATUSES = {"queued", "downloading", "cutting", "captions", "rendering", "qa", "done", "needs-input", "failed"}

src, status, progress, step = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
out = pathlib.Path(sys.argv[5]) if len(sys.argv) > 5 else pathlib.Path(src).with_name("patch.json")
if status not in STATUSES:
    sys.exit(f"unknown status {status!r}")

doc = json.loads(pathlib.Path(src).read_text())
data = doc.get("data", doc)  # out_dir files wrap the document
now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
log = (data.get("log") or [])[-19:] + [{"at": now, "status": status, "msg": step}]
patch = {"status": status, "progress": round(progress), "step": step, "updatedAt": now, "log": log}
data["log"] = log
pathlib.Path(src).write_text(json.dumps(doc))
out.write_text(json.dumps(patch))
print(out)
