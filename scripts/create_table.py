"""Create the brainstorm board table (keys, GSI1, Streams, TTL) on DynamoDB Local or AWS.

Usage: python scripts/create_table.py [--endpoint-url URL] [--table NAME] [--provisioned]
       [--recreate]

Without --endpoint-url (or DYNAMODB_ENDPOINT_URL) the table is created in the AWS account of the
current profile. --recreate deletes an existing table first and is only allowed with an endpoint
URL, so it can't drop the AWS table by accident.
"""

import argparse
import sys
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from brainstorm import db, schema  # noqa: E402 - needs the sys.path entry above


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint-url", default=db.endpoint_url(), help="e.g. localhost:8000")
    parser.add_argument("--table", default=db.table_name(), help="table name")
    parser.add_argument(
        "--provisioned",
        action="store_true",
        help=(
            f"provisioned capacity ({schema.TABLE_UNITS} RCU/WCU table, {schema.GSI1_UNITS} GSI1) "
            "within the always-free tier, instead of on-demand"
        ),
    )
    parser.add_argument("--recreate", action="store_true", help="delete the table first (local)")
    args = parser.parse_args()

    if args.recreate and not args.endpoint_url:
        print("--recreate needs --endpoint-url; refusing to delete an AWS table", file=sys.stderr)
        return 2

    dynamodb = db.resource(args.endpoint_url)
    target = args.endpoint_url or "AWS"
    try:
        if args.recreate:
            existing = dynamodb.Table(args.table)
            try:
                existing.delete()
                existing.wait_until_not_exists()
                print(f"Deleted {args.table} on {target}")
            except ClientError as err:
                if err.response["Error"]["Code"] != "ResourceNotFoundException":
                    raise
        table = schema.create_table(dynamodb, args.table, provisioned=args.provisioned)
        billing = "provisioned" if args.provisioned else "on-demand"
        print(f"Created {table.name} on {target} ({billing}, GSI1, Streams, TTL on expires_at)")
    except ClientError as err:
        if err.response["Error"]["Code"] == "ResourceInUseException":
            print(f"{args.table} already exists on {target}", file=sys.stderr)
            return 1
        print(f"Create table failed: {err}", file=sys.stderr)
        return 1
    except BotoCoreError as err:
        print(f"Create table failed: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
