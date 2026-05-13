import re
import sys

def main():
    with open('main_detector.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove axis, cams, uidai, iocl from RESTRICTED_TOKENS
    content = re.sub(r'^[ \t]*"cams",.*?\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^[ \t]*"axis",.*?\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^[ \t]*"uidai",.*?\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^[ \t]*"iocl",.*?\n', '', content, flags=re.MULTILINE)

    # Add them to EXACT_ONLY_TOKENS
    content = content.replace('"orgi",    # short\n}', '"orgi",    # short\n    "axis",\n    "cams",\n    "uidai",\n    "iocl",\n}')

    # Add rgcci to RESTRICTED_TOKENS
    content = content.replace('"myvi",    # common non-brand word\n}', '"myvi",    # common non-brand word\n    "rgcci",\n}')

    # Add words to COMMON_WORDS
    content = content.replace('"marathi",\n}', '"marathi",\n    "liquid", "praxis", "taxis", "maxis", "araxis", "webcam", "dashcam",\n}')

    with open('main_detector.py', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    main()
