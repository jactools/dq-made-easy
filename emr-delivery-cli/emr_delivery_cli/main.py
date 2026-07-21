"""EMR Delivery CLI — generate and manage DeliveryIds and Data Delivery Notes.

Usage:
    emr-delivery generate-id --producer-system sap --data-object customer_master --version 1 --job-id daily-load
    emr-delivery generate-ddn --producer-system sap --data-object customer_master --version 1 --job-id daily-load
    emr-delivery parse-id sap:customer_master:1:daily-load
    emr-delivery generate-event
"""

from __future__ import annotations

import argparse
import json
import sys

from emr_delivery_sdk import (
    DeliveryId,
    DeliveryIdBuilder,
    DdnBuilder,
    generate_delivery_time_event,
)


def cmd_generate_id(args: argparse.Namespace) -> int:
    """Generate a deterministic DeliveryId."""
    try:
        delivery_id = (
            DeliveryIdBuilder()
            .producer_system(args.producer_system)
            .data_object(args.data_object)
            .version(args.version)
            .job_id(args.job_id)
            .build()
        )
        output = {
            "delivery_id": str(delivery_id),
            "producer_system": delivery_id.producer_system,
            "data_object_logical_name": delivery_id.data_object_logical_name,
            "version": delivery_id.version,
            "job_id": delivery_id.job_id,
        }
        if args.format == "json":
            print(json.dumps(output, indent=2))
        else:
            print(str(delivery_id))
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_generate_ddn(args: argparse.Namespace) -> int:
    """Generate a Data Delivery Note with DeliveryId and UUIDv7."""
    try:
        delivery_id = (
            DeliveryIdBuilder()
            .producer_system(args.producer_system)
            .data_object(args.data_object)
            .version(args.version)
            .job_id(args.job_id)
            .build()
        )

        builder = DdnBuilder(delivery_id=delivery_id)

        if args.delivery_type:
            builder.delivery_type(args.delivery_type)
        if args.storage_location:
            builder.storage_location(args.storage_location)
        if args.delivery_location:
            builder.delivery_location(args.delivery_location)
        if args.record_count:
            builder.record_count(args.record_count)
        if args.size_bytes:
            builder.size_bytes(args.size_bytes)
        if args.checksum:
            builder.checksum(args.checksum, args.checksum_algorithm)
        if args.delivered_at:
            builder.delivered_at(args.delivered_at)
        if args.delivered_by:
            builder.delivered_by(args.delivered_by)
        if args.layer:
            builder.layer(args.layer)
        if args.correction_predecessor:
            builder.correction(args.correction_predecessor, args.correction_reason or "Correction")

        ddn = builder.build()

        output = {
            "delivery_id": str(ddn.delivery_id),
            "delivery_time_event": ddn.delivery_time_event,
            "delivery_version": ddn.delivery_version,
            "delivery_type": ddn.delivery_type.value,
            "producer_system": ddn.producer_system,
            "data_object_logical_name": ddn.data_object_logical_name,
            "job_id": ddn.job_id,
            "layer": ddn.layer,
            "storage_location": ddn.storage_location,
            "delivery_location": ddn.delivery_location,
            "record_count": ddn.record_count,
            "size_bytes": ddn.size_bytes,
            "checksum": ddn.checksum,
            "checksum_algorithm": ddn.checksum_algorithm,
            "delivered_at": ddn.delivered_at,
            "delivered_by": ddn.delivered_by,
            "status": ddn.status.value,
            "predecessor_time_event": ddn.predecessor_time_event,
            "correction_reason": ddn.correction_reason,
        }

        print(json.dumps(output, indent=2))
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_parse_id(args: argparse.Namespace) -> int:
    """Parse and validate a DeliveryId string."""
    try:
        delivery_id = DeliveryId.from_string(args.delivery_id)
        output = {
            "delivery_id": str(delivery_id),
            "valid": True,
            "producer_system": delivery_id.producer_system,
            "data_object_logical_name": delivery_id.data_object_logical_name,
            "version": delivery_id.version,
            "job_id": delivery_id.job_id,
        }
        print(json.dumps(output, indent=2))
        return 0
    except ValueError as e:
        print(json.dumps({"delivery_id": args.delivery_id, "valid": False, "error": str(e)}, indent=2))
        return 1


def cmd_generate_event(args: argparse.Namespace) -> int:
    """Generate a UUIDv7 delivery time event."""
    dte = generate_delivery_time_event()
    print(dte)
    return 0


def main() -> int:
    """Entry point for emr-delivery CLI."""
    parser = argparse.ArgumentParser(
        prog="emr-delivery",
        description="EMR Delivery CLI — generate and manage DeliveryIds and Data Delivery Notes",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # generate-id
    id_parser = subparsers.add_parser("generate-id", help="Generate a deterministic DeliveryId")
    id_parser.add_argument("--producer-system", required=True, help="Producer system code (e.g., sap)")
    id_parser.add_argument("--data-object", required=True, help="Data object logical name (e.g., customer_master)")
    id_parser.add_argument("--version", type=int, required=True, help="Data object version")
    id_parser.add_argument("--job-id", required=True, help="Pipeline job ID (e.g., daily-load)")
    id_parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    id_parser.set_defaults(func=cmd_generate_id)

    # generate-ddn
    ddn_parser = subparsers.add_parser("generate-ddn", help="Generate a Data Delivery Note")
    ddn_parser.add_argument("--producer-system", required=True, help="Producer system code")
    ddn_parser.add_argument("--data-object", required=True, help="Data object logical name")
    ddn_parser.add_argument("--version", type=int, required=True, help="Data object version")
    ddn_parser.add_argument("--job-id", required=True, help="Pipeline job ID")
    ddn_parser.add_argument("--delivery-type", choices=["initial", "retry", "correction", "backfill", "deletion", "retention"], default="initial")
    ddn_parser.add_argument("--storage-location", help="Internal storage location")
    ddn_parser.add_argument("--delivery-location", help="Consumer-facing delivery location")
    ddn_parser.add_argument("--record-count", type=int, help="Record count")
    ddn_parser.add_argument("--size-bytes", type=int, help="Delivery size in bytes")
    ddn_parser.add_argument("--checksum", help="Content checksum")
    ddn_parser.add_argument("--checksum-algorithm", help="Checksum algorithm (e.g., sha256)")
    ddn_parser.add_argument("--delivered-at", help="Canonical delivery timestamp (ISO 8601)")
    ddn_parser.add_argument("--delivered-by", help="Pipeline or agent identifier")
    ddn_parser.add_argument("--layer", help="Data layer (brown, gold, silver)")
    ddn_parser.add_argument("--correction-predecessor", help="UUIDv7 of the delivery being corrected")
    ddn_parser.add_argument("--correction-reason", help="Correction reason")
    ddn_parser.set_defaults(func=cmd_generate_ddn)

    # parse-id
    parse_parser = subparsers.add_parser("parse-id", help="Parse and validate a DeliveryId")
    parse_parser.add_argument("delivery_id", help="DeliveryId string to parse")
    parse_parser.set_defaults(func=cmd_parse_id)

    # generate-event
    subparsers.add_parser("generate-event", help="Generate a UUIDv7 delivery time event")
    subparsers.choices["generate-event"].set_defaults(func=cmd_generate_event)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
