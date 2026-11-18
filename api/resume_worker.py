"""Parse in a disposable process; suppress library diagnostics and private text logs."""
import base64
import json
import os
import sys


def main():
    if sys.platform != "win32":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    from api.resume_parser import ResumeParseError, extract, suggestions
    sys.stderr = open(os.devnull, "w")
    try:
        payload = json.loads(sys.stdin.read(710000))
        text = extract(payload["kind"], base64.b64decode(payload["content"], validate=True))
        result = {"text": text, **suggestions(text)}
    except ValueError as exc:
        result = {"error": str(exc) if isinstance(exc, ResumeParseError) else "This file could not be read. Export a text résumé instead."}
    except Exception:
        result = {"error": "This file could not be read. Export a text résumé instead."}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
