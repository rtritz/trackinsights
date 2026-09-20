"""Writing the precomputed JSON the site serves.

One function, used by every job that produces a file under static/data/, so the
three things that matter about these files are decided once.

COMPACT, NOT INDENTED
---------------------
The routes send these files to the browser *verbatim* -- the file is the
response -- so the bytes on disk are the bytes on the wire. Indented, the
largest was 1093KB; compact it is 635KB. That is 42% off every one of those
responses, off the repository, and off the deploy.

The cost is that the files stop being line-diffable. They are machine artifacts,
rebuilt whole on every run, and a 600KB JSON diff was never going to be read by
a human anyway. `python -m json.tool <file>` prints one readably when needed.

VALIDATED WHILE IT IS CHEAP
---------------------------
`allow_nan=False` makes the dump fail rather than emit `NaN` or `Infinity`,
which json.dumps will happily write and no JSON parser will accept. Payloads
here come from pandas and SQL aggregates, which produce NaN whenever a mean is
taken over nothing at all -- so this is a real failure mode, not a theoretical
one. Catching it here stops a build; catching it in the browser means a page
that silently shows nothing.

WRITTEN ATOMICALLY
------------------
Serialize fully, write a temporary file beside the target, then os.replace it
into place -- which is atomic, so a reader either sees the whole old file or the
whole new one. A job interrupted halfway can no longer leave a truncated file
behind, which matters now that the routes forward the bytes without parsing them
and would otherwise forward the truncation.
"""
import json
import os


def write_json_artifact(path, payload):
    """Write `payload` to `path` as compact JSON. Returns the path.

    Raises ValueError if the payload contains NaN or Infinity, before anything
    is written -- a failed build is the point.
    """
    # Fully serialized before the target is touched, so a serialization error
    # leaves the previous build in place.
    text = json.dumps(payload, separators=(',', ':'), allow_nan=False, default=str)

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    tmp_path = '%s.tmp' % path
    # newline='' so the bytes are exactly what was serialized; without it Python
    # rewrites every \n as \r\n on Windows, which is how these files came to be
    # 3% larger on one developer's machine than another's.
    with open(tmp_path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(tmp_path, path)
    return path
