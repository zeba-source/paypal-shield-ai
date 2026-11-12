import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.paypal_client import PayPalClient


def main() -> None:
    client = PayPalClient()
    order = client.create_order(
        "10.00",
        reference_id="PAYPAL_SMOKE_TEST",
        description="PayPal Shield AI smoke test",
    )
    approval_link = next(
        (link["href"] for link in order.get("links", []) if link.get("rel") == "approve"),
        None,
    )
    if not approval_link:
        raise RuntimeError("PayPal order did not return an approval link")
    print(approval_link)


if __name__ == "__main__":
    main()