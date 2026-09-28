import argparse
import hashlib
import re


CARD_TOKEN_LEN = 8
CARD_TOKEN_SALT = bytes.fromhex(
    "b77fc02a89369be05d1425c32b30617a"
    "a3505fd432d385a5d5b9d5b26243bf56"
)
STICKER_PREFIX = "ACR67:CARD:"
CARD_ID_PATTERN = re.compile(r"ACR-\d+")


def sticker_text(card_id):
    normalized = str(card_id).strip().upper()
    if CARD_ID_PATTERN.fullmatch(normalized) is None:
        raise ValueError("card ID must use the form ACR-26")

    token = hashlib.sha256(
        CARD_TOKEN_SALT + normalized.encode("ascii")
    ).digest()[:CARD_TOKEN_LEN]
    return STICKER_PREFIX + token.hex().upper()


def main():
    parser = argparse.ArgumentParser(
        description="Generate the NFC sticker text for an ACR card."
    )
    parser.add_argument("card_id", help="ACR card ID, for example ACR-32")
    args = parser.parse_args()

    try:
        print(sticker_text(args.card_id))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
