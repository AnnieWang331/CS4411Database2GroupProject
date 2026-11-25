"""Upload the web client to the deployed stack's bucket and point it at the deployed APIs.

Usage: python scripts/deploy_web.py [--stack NAME] [--dry-run]

Reads the stack's outputs (``ApiUrl``, ``WebSocketUrl``, ``WebBucketName``,
``WebDistributionId``), uploads every file in ``web/`` except ``config.js``, uploads a
``config.js`` with the stack's URLs in its place, deletes files from the bucket that are no longer
in ``web/``, and asks CloudFront to drop its cached copies. Uses the usual AWS settings
(``AWS_PROFILE``, ``AWS_REGION``); the region defaults to samconfig.toml's.
"""

import argparse
import json
import mimetypes
import sys
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
CONFIG = "config.js"
DEFAULT_STACK = "brainstorm-board"
DEFAULT_REGION = "ca-central-1"
OUTPUTS = ("ApiUrl", "WebSocketUrl", "WebBucketName", "WebDistributionId", "WebUrl")


def config_js(api_url: str, ws_url: str) -> str:
    """The deployed copy of web/config.js."""
    return (
        "// Written by scripts/deploy_web.py from the stack's outputs.\n"
        f"export const API_URL = {json.dumps(api_url.rstrip('/'))};\n"
        f"export const WS_URL = {json.dumps(ws_url.rstrip('/'))};\n"
    )


# Local tooling that can end up in web/ (e.g. a Playwright install) and must never be public.
SKIP_DIRS = {"node_modules"}
SKIP_FILES = {CONFIG, "package.json", "package-lock.json"}


def web_files(root: Path = WEB) -> dict[str, Path]:
    """Bucket key -> local file, for the site's files in web/ (config.js is written separately)."""
    files = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or rel.as_posix() in SKIP_FILES:
            continue
        if any(part.startswith(".") or part in SKIP_DIRS for part in rel.parts):
            continue
        files[rel.as_posix()] = path
    return files


def content_type(key: str) -> str:
    if key.endswith(".js"):
        return "text/javascript; charset=utf-8"  # some systems map .js to text/plain
    guessed, _ = mimetypes.guess_type(key)
    if guessed and guessed.startswith("text/"):
        return f"{guessed}; charset=utf-8"
    return guessed or "application/octet-stream"


def stack_outputs(session, stack: str) -> dict[str, str]:
    described = session.client("cloudformation").describe_stacks(StackName=stack)["Stacks"][0]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in described.get("Outputs", [])}
    missing = [name for name in OUTPUTS if name not in outputs]
    if missing:
        sys.exit(f"Stack {stack} has no output(s) {', '.join(missing)}. Run sam deploy first.")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--stack", default=DEFAULT_STACK, help="CloudFormation stack name")
    parser.add_argument("--dry-run", action="store_true", help="show what would change")
    args = parser.parse_args()

    session = boto3.Session()
    if session.region_name is None:
        session = boto3.Session(region_name=DEFAULT_REGION)
    out = stack_outputs(session, args.stack)
    bucket = out["WebBucketName"]
    s3 = session.client("s3")

    files = web_files()
    uploads = [(key, path.read_bytes()) for key, path in files.items()]
    uploads.append((CONFIG, config_js(out["ApiUrl"], out["WebSocketUrl"]).encode()))
    existing = {
        obj["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket)
        for obj in page.get("Contents", [])
    }
    stale = sorted(existing - {key for key, _ in uploads})

    for key, body in uploads:
        print(f"upload  s3://{bucket}/{key}")
        if not args.dry_run:
            s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type(key))
    for key in stale:
        print(f"delete  s3://{bucket}/{key}")
        if not args.dry_run:
            s3.delete_object(Bucket=bucket, Key=key)

    if args.dry_run:
        print(f"Dry run: nothing changed. {CONFIG} would point at {out['ApiUrl']}")
        return
    session.client("cloudfront").create_invalidation(
        DistributionId=out["WebDistributionId"],
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/*"]},
            "CallerReference": f"deploy-web-{time.time_ns()}",
        },
    )
    print(f"Uploaded {len(uploads)} files. CloudFront picks them up within a few minutes.")
    print(f"Open {out['WebUrl']}/#/host")


if __name__ == "__main__":
    main()
