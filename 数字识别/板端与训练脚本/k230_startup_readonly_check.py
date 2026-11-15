"""Read-only inspection of camera-related names in WonderMK startup files."""

import os
import sys

PATHS = ("/sdcard/main.py", "/sdcard/hiwonder/main.py")
TERMS = ("sensor", "snapshot", "mediamanager", "camera", "pipeline")


def main():
    print("[CHECK] STARTUP_FILES")
    print("[INFO] Python", sys.version)
    for path in PATHS:
        try:
            info = os.stat(path)
            print("[FILE] {} size={}".format(path, info[6]))
            count = 0
            with open(path, "r") as source:
                for number, line in enumerate(source, 1):
                    text = line.strip()
                    lower = text.lower()
                    if any(term in lower for term in TERMS):
                        # Avoid printing configuration values or unrelated data.
                        print("[MATCH] line={} keyword={}".format(
                            number, next(term for term in TERMS if term in lower)))
                        count += 1
            print("[MATCHES] {}".format(count))
        except Exception as error:
            print("[ERROR] {} {}".format(path, error))
    print("[CHECK] DONE")


if __name__ == "__main__":
    main()
