import argparse
import asyncio
import json
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.core.database import engine, session_factory
from app.core.exceptions import AppError
from app.modules.learning.registry import MODULES, activate, metadata, train
from app.modules.learning.service import scan_anomalies


async def run(args: argparse.Namespace) -> None:
    try:
        async with session_factory() as db:
            if args.command == "train":
                for module in MODULES:
                    if args.module in (module, "all"):
                        model = await train(db, module, args.mode)
                        await db.commit()
                        print(json.dumps(jsonable_encoder(metadata(model)), ensure_ascii=True))
            elif args.command == "activate":
                model = await activate(db, args.version)
                await db.commit()
                print(json.dumps(jsonable_encoder(metadata(model)), ensure_ascii=True))
            else:
                print(json.dumps(await scan_anomalies(db), ensure_ascii=True))
                await db.commit()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrenamiento y evaluación por lotes de SIRLOD")
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train")
    training.add_argument("--mode", required=True, choices=("real", "demo"))
    training.add_argument("--module", default="all", choices=(*MODULES, "all"))
    activation = commands.add_parser("activate")
    activation.add_argument("version", type=UUID)
    commands.add_parser("scan-anomalies")
    try:
        asyncio.run(run(parser.parse_args()))
    except AppError as exc:
        parser.exit(1, f"{exc.message}\n")


if __name__ == "__main__":
    main()
