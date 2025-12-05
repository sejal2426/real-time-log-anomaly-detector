# parser.py
import re

LOG_RE = re.compile(
    r'(?P<timestamp>[\d\-:T\.]+)\s+file=(?P<file>[^:]+):(?P<line>\d+)\s+resp=(?P<resp>[\d\.]+)'
)

def parse_line(line: str):
    match = LOG_RE.search(line)
    if not match:
        return None
    
    return {
        "timestamp": match.group("timestamp"),
        "source_file": match.group("file"),
        "line_number": int(match.group("line")),
        "features": {"resp": float(match.group("resp"))},
        "raw": line.strip()
    }
