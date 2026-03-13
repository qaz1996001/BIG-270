"""Entry point for vibfault CLI."""

from vibfault.core.models import MachineParameters


def main() -> None:
    """Run vibfault diagnostic pipeline."""
    params = MachineParameters(sampling_rate=10000.0)
    print(f"VibFault v0.1.0 — Tier {params.tier} diagnostic ready")
    print(f"Provide more parameters to unlock higher tiers (current: Tier {params.tier})")


if __name__ == "__main__":
    main()
