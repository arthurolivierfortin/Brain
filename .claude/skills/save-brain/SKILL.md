---
name: save-brain
description: Save current session context to Brain immediately (mid-session manual trigger)
---

# Save Brain

Manually trigger a brain save for the current session without ending it.

Run:
```bash
python scripts/brain_save_now.py
```

This discovers the current session transcript, summarizes the unsaved delta via Gemini Flash, and POSTs it to the Brain API. If Brain is offline, the entry is queued locally for retry.
