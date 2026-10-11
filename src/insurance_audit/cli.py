"""Project CLI; register operational commands only when implemented."""

import argparse
import json
from pathlib import Path

from insurance_audit import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="insurance-audit",
        description="Local insurance audit corpus tooling.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")
    doctor = commands.add_parser("doctor", help="Probe real text/vision models; incurs API usage")
    doctor.add_argument("--report", type=Path, default=Path("reports/model-doctor.json"))
    audit = commands.add_parser("audit-text", help="Audit text through the shared service")
    audit.add_argument("text")
    audit.add_argument("--context", default="{}")
    pipeline = commands.add_parser("pipeline", help="Run or watch the complete P0 ingestion loop")
    pipeline.add_argument("action", choices=("run", "watch", "start", "stop", "status", "seal"))
    pipeline.add_argument("--root", type=Path, default=Path.cwd())
    pipeline.add_argument("--interval", type=float, default=5.0)
    pipeline.add_argument("--retry", action="store_true", help="Retry failed versions explicitly")
    pipeline.add_argument("--ruleset", help="Reviewed candidate for seal")
    for name in ("ingest", "validate-corpus", "publish-corpus"):
        command = commands.add_parser(name)
        command.add_argument("--ruleset", required=True)
        command.add_argument("--root", type=Path, default=Path.cwd())
        if name == "ingest":
            command.add_argument("--source-manifest", type=Path)
        if name == "validate-corpus":
            command.add_argument(
                "--candidate",
                action="store_true",
                help="Check integrity while reporting unresolved review gates",
            )
            command.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.command == "doctor":
        import asyncio

        from insurance_audit.config import Settings
        from insurance_audit.corpus.validate import write_report
        from insurance_audit.doctor import probe

        print("正在执行真实模型探测，可能产生 API 费用；不会输出密钥。")
        result = asyncio.run(probe(Settings()))
        write_report(result, args.report)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "audit-text":
        import asyncio

        from insurance_audit.config import Settings
        from insurance_audit.models.bailian import Bailian
        from insurance_audit.models.mock import MockProvider
        from insurance_audit.retrieval import Corpus
        from insurance_audit.schemas import AuditContext, AuditRequest
        from insurance_audit.service import AuditService

        async def run():
            settings = Settings()
            provider = MockProvider() if settings.audit_mock else Bailian(settings)
            try:
                return await AuditService(settings, Corpus(settings), provider).review(
                    AuditRequest(
                        text=args.text, context=AuditContext.model_validate_json(args.context)
                    )
                )
            finally:
                await provider.close()

        print(asyncio.run(run()).model_dump_json(indent=2))
    elif args.command == "pipeline":
        from insurance_audit.corpus import pipeline as flow

        root = args.root.resolve()
        if args.action == "run":
            result = flow.run_once(root, retry=args.retry)
        elif args.action == "watch":
            flow.watch(root, interval=args.interval)
            return
        elif args.action == "start":
            result = flow.start(root, interval=args.interval)
        elif args.action == "stop":
            stop = root / "data/runtime/pipeline.stop"
            stop.parent.mkdir(parents=True, exist_ok=True)
            stop.touch()
            result = {"status": "stop_requested"}
        elif args.action == "seal":
            if not args.ruleset:
                parser.error("pipeline seal requires --ruleset")
            result = flow.seal_review(root, args.ruleset)
        else:
            result = {
                "health": flow.read(root / "data/runtime/pipeline-health.json", {}),
                "pipeline": flow.read(root / flow.REGISTRY, {}).get("pipeline", {}),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "ingest":
        from insurance_audit.corpus.ingest import build_candidate

        result = build_candidate(
            args.root.resolve(),
            args.source_manifest or args.root / "data/extracted/official-source-manifest.json",
            args.ruleset,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        refresh_registry(args.root)
    elif args.command == "validate-corpus":
        from insurance_audit.corpus.validate import validate_corpus, write_report

        result = validate_corpus(args.root.resolve(), args.ruleset)
        if args.report:
            write_report(result, args.report)
        print(json.dumps({k: v for k, v in result.items() if k != "issues"}, indent=2))
        raise SystemExit(
            0 if (result["structural_valid"] if args.candidate else result["release_ready"]) else 1
        )
    elif args.command == "publish-corpus":
        from insurance_audit.corpus.review import publish_snapshot

        result = publish_snapshot(args.root.resolve(), args.ruleset)
        refresh_registry(args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


def refresh_registry(root: Path) -> None:
    from insurance_audit.corpus.pipeline import lock
    from insurance_audit.corpus.registry import rebuild

    with lock(root):
        rebuild(root)


if __name__ == "__main__":
    main()
