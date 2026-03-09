"""Entry point: python -m marquee_flight_tracker"""
import argparse
import logging

from .config import load_config
from .app import FlightTrackerApp


def main():
    parser = argparse.ArgumentParser(
        description="Marquee Flight Tracker - Track overhead aircraft"
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--display",
        choices=["terminal", "web"],
        help="Override display backend from config",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config(args.config)
    if args.display:
        config.display.backend = args.display

    app = FlightTrackerApp(config)
    app.run()


if __name__ == "__main__":
    main()
