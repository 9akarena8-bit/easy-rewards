"""Offline signing CLI for the owner. The launcher only needs the public key."""
from __future__ import annotations

import argparse
import base64
from contextlib import closing
from getpass import getpass
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .offline_license import INSTALLATION_ID, canonical_payload, verify_license

PAYMENT_METHODS = ("bank_transfer", "steam_items")
METHODS = (*PAYMENT_METHODS, "friend", "owner")
REFERENCE = re.compile(r"[A-Za-z0-9_.:-]{4,128}")
PUBLIC_KEY_NAME = "license-public.pem"
PRIVATE_KEY_NAME = "private-key.pem"


def initialize_keys(directory: Path, password: bytes) -> Path:
    if len(password) < 12:
        raise ValueError("Пароль ключа должен содержать не менее 12 байт UTF-8.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    private_path, public_path = directory / PRIVATE_KEY_NAME, directory / PUBLIC_KEY_NAME
    if private_path.exists() or public_path.exists():
        raise ValueError("Ключи уже существуют. Повторный выпуск пары отменён.")
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with private_path.open("xb") as stream:
        stream.write(private_pem)
    with public_path.open("xb") as stream:
        stream.write(public_pem)
    return public_path


def issue_license(directory: Path, installation_id: str, days: int | None, method: str,
                  reference: str, *, password: bytes | None, reconciled: bool = False,
                  now: int | None = None) -> dict:
    """Sign after owner approval. One reference can issue at most one license."""
    if (not isinstance(installation_id, str) or not INSTALLATION_ID.fullmatch(installation_id)
            or not (days is None or type(days) is int and 1 <= days <= 365) or method not in METHODS
            or not isinstance(reference, str) or not REFERENCE.fullmatch(reference.strip())):
        raise ValueError("Проверьте ID установки, срок, способ и идентификатор операции.")
    if method == "owner" and days is not None:
        raise ValueError("Лицензия владельца всегда бессрочная.")
    if method in PAYMENT_METHODS:
        if days not in (1, 3, 7):
            raise ValueError("Платные тарифы действуют 1, 3 или 7 дней.")
        if reconciled is not True:
            raise ValueError("Сначала вручную сверьте поступление или завершённый трейд.")
    directory = Path(directory)
    key = serialization.load_pem_private_key(
        (directory / PRIVATE_KEY_NAME).read_bytes(), password=password,
    )
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Требуется приватный ключ Ed25519.")
    public_pem = (directory / PUBLIC_KEY_NAME).read_bytes()
    expected_public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if public_pem != expected_public:
        raise ValueError("Публичный ключ владельца не соответствует приватному ключу.")
    current = int(time.time()) if now is None else now
    reference = reference.strip()
    with closing(sqlite3.connect(directory / "issued-licenses.sqlite3", timeout=10)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS issued (
            reference TEXT PRIMARY KEY, installation_id TEXT NOT NULL, days INTEGER NOT NULL,
            method TEXT NOT NULL, expires_at INTEGER NOT NULL, document TEXT NOT NULL)""")
        prior = db.execute("SELECT installation_id,days,method,document FROM issued WHERE reference=?",
                           (reference,)).fetchone()
        if prior:
            if prior[:3] != (installation_id, days or 0, method):
                raise ValueError("Идентификатор операции уже использован для другой лицензии.")
            document = json.loads(prior[3])
            # Validate old records at their issue time so re-export after expiry works.
            verify_license(document, public_pem, installation_id, now=document["payload"]["issued_at"])
            return document
        previous_expiry = db.execute("SELECT MAX(expires_at) FROM issued WHERE installation_id=?",
                                     (installation_id,)).fetchone()[0] or 0
        perpetual = days is None
        payload = {
            "version": 2 if perpetual else 1, "license_id": secrets.token_hex(16).upper(),
            "installation_id": installation_id, "issued_at": current,
            "expires_at": None if perpetual else max(current, previous_expiry) + days * 86400,
            "access": method if method in ("friend", "owner") else "paid",
        }
        signature = key.sign(canonical_payload(payload))
        document = {"payload": payload, "signature": base64.b64encode(signature).decode("ascii")}
        db.execute("INSERT INTO issued VALUES(?,?,?,?,?,?)",
                   (reference, installation_id, days or 0, method, payload["expires_at"] or 0, json.dumps(document)))
        return document


def save_license(path: Path, document: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except FileExistsError:
        if json.loads(path.read_text(encoding="utf-8")) != document:
            raise ValueError("Файл уже существует. Укажите другой путь для лицензии.") from None


def main():
    parser = argparse.ArgumentParser(description="Выпуск офлайн-лицензий владельцем")
    parser.add_argument("--owner-dir", type=Path, required=True,
                        help="Приватная папка владельца вне приложения и репозитория")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Один раз создать защищённую паролем пару ключей")
    issue = sub.add_parser("issue", help="Выдать лицензию для конкретной установки")
    issue.add_argument("--installation", required=True)
    issue.add_argument("--days", type=int, help="1/3/7 для покупателя; опустите для бессрочного доступа владельца или друга")
    issue.add_argument("--method", choices=METHODS, required=True)
    issue.add_argument("--reference", required=True)
    issue.add_argument("--output", type=Path, required=True)
    issue.add_argument("--confirm-reconciled", action="store_true",
                       help="Подтвердить личную сверку уже завершённой операции")
    issue.add_argument("--legacy-unencrypted-key", action="store_true",
                       help="Использовать ранее созданный приватный ключ без пароля")
    args = parser.parse_args()
    try:
        owner_dir = args.owner_dir.resolve()
        repo = Path(__file__).resolve().parents[1]
        if owner_dir.is_relative_to(repo) or repo.is_relative_to(owner_dir):
            raise ValueError("Выберите отдельную приватную папку вне дерева репозитория.")
        if args.command == "init":
            password = getpass("Новый пароль приватного ключа: ")
            if password != getpass("Повторите пароль: "):
                raise ValueError("Пароли не совпали.")
            print("Публичный ключ для сборки:", initialize_keys(owner_dir, password.encode()))
        else:
            if args.method in PAYMENT_METHODS and not args.confirm_reconciled:
                raise ValueError("Платный выпуск требует --confirm-reconciled после ручной сверки.")
            password = None if args.legacy_unencrypted_key else getpass("Пароль приватного ключа: ").encode()
            document = issue_license(owner_dir, args.installation, args.days, args.method, args.reference,
                                     password=password, reconciled=args.confirm_reconciled)
            save_license(args.output, document)
            print("Лицензия сохранена:", args.output)
            print("Срок:", "бессрочно" if document["payload"]["expires_at"] is None
                  else str(document["payload"]["expires_at"]) + " (Unix UTC)")
    except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
        parser.exit(1, f"Ошибка выпуска лицензии: {exc}\n")


if __name__ == "__main__":
    main()
