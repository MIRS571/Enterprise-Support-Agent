import argparse
import asyncio

import httpx

from agent_service.core.config import get_settings
from agent_service.integrations.business_service import BusinessServiceClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the Python-to-Java order query integration."
    )
    parser.add_argument("--tenant-id", default="company_001")
    parser.add_argument("--user-id", default="U1001")
    parser.add_argument("--order-id", default="A1001")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = get_settings()

    async with httpx.AsyncClient(
        base_url=str(settings.business_service_base_url),
        timeout=httpx.Timeout(settings.business_service_timeout_seconds),
        trust_env=False,
    ) as http_client:
        client = BusinessServiceClient(
            http_client=http_client,
            max_retries=settings.business_service_max_retries,
        )
        order = await client.get_order(
            tenant_id=args.tenant_id,
            user_id=args.user_id,
            order_id=args.order_id,
        )

    print(order.model_dump_json(by_alias=True, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
