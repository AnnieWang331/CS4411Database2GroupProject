"""Verify that boto3 can reach AWS with the current profile and list DynamoDB tables.

Usage: python scripts/check_aws.py [--profile NAME] [--region REGION]
"""

import argparse
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", help="AWS profile (defaults to AWS_PROFILE / default chain)")
    parser.add_argument("--region", help="AWS region (defaults to the profile's region)")
    args = parser.parse_args()

    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        identity = session.client("sts").get_caller_identity()
        print(f"Account: {identity['Account']}")
        print(f"Caller:  {identity['Arn']}")
        print(f"Region:  {session.region_name}")

        tables = session.client("dynamodb").list_tables()["TableNames"]
        print(f"DynamoDB tables: {', '.join(tables) if tables else '(none)'}")
    except (BotoCoreError, ClientError) as err:
        print(f"AWS check failed: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
