from __future__ import annotations

import argparse
import os
from pathlib import Path

from saas_service import ServiceConfig, TranscriptSaaSService
from saas_store import SQLiteStore


def build_service() -> TranscriptSaaSService:
    db_path = Path(os.getenv("GHOST_DB_PATH", "ghost_saas.db"))
    store = SQLiteStore(db_path)
    store.init_db()
    return TranscriptSaaSService(
        store,
        ServiceConfig(auto_process=False),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Administra API keys del SaaS local.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Crea una nueva API key.")
    create_parser.add_argument("name", help="Nombre del cliente o integrador.")
    create_parser.add_argument(
        "--key",
        help="Valor explícito para la API key. Si no se indica, se genera automáticamente.",
    )

    subparsers.add_parser("list", help="Lista API keys registradas.")

    deactivate_parser = subparsers.add_parser(
        "deactivate", help="Desactiva una API key existente."
    )
    deactivate_parser.add_argument("key", help="API key a desactivar.")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    service = build_service()

    if args.command == "create":
        record = service.create_api_key(args.name, key=args.key)
        print(record["key"])
        return 0

    if args.command == "list":
        for record in service.list_api_keys():
            state = "active" if record["active"] else "inactive"
            print(f'{record["name"]}\t{state}\t{record["key"]}')
        return 0

    if args.command == "deactivate":
        if not service.deactivate_api_key(args.key):
            print("API key no encontrada")
            return 1
        print("API key desactivada")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
