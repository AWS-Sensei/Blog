import json
import boto3
from datetime import datetime, date, timezone

ce = boto3.client("ce", region_name="us-east-1")
ssm = boto3.client("ssm", region_name="eu-central-1")


def lambda_handler(event, context):
    today = date.today()
    start = today.replace(day=1).isoformat()
    end = today.isoformat()

    if start == end:
        return {"statusCode": 200, "body": "skipped: start of month"}

    response = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    services = {}
    total = 0.0
    for group in response["ResultsByTime"][0]["Groups"]:
        service = group["Keys"][0]
        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
        if amount >= 0.0001:
            services[service] = round(amount, 4)
            total += amount

    data = {
        "total": round(total, 4),
        "currency": "USD",
        "period": {"start": start, "end": end},
        "services": services,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }

    ssm.put_parameter(
        Name="/sensei/blog/cost-data",
        Value=json.dumps(data),
        Type="String",
        Overwrite=True,
    )

    print(f"Refreshed: total={total:.4f} USD, {len(services)} services")
    return {"statusCode": 200, "body": "ok"}
