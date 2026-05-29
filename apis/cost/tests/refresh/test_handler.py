import json
import sys
from datetime import date
from unittest.mock import patch

handler = sys.modules["cost_refresh_handler"]

CE_RESPONSE = {
    "ResultsByTime": [{
        "Groups": [
            {"Keys": ["AWS Lambda"],   "Metrics": {"UnblendedCost": {"Amount": "0.5000"}}},
            {"Keys": ["Amazon S3"],    "Metrics": {"UnblendedCost": {"Amount": "0.2500"}}},
            {"Keys": ["Tiny Service"], "Metrics": {"UnblendedCost": {"Amount": "0.00001"}}},
        ]
    }]
}


def test_skips_on_first_of_month():
    with patch.object(handler, "date") as mock_date:
        mock_date.today.return_value = date(2024, 6, 1)
        response = handler.lambda_handler({}, None)
    assert "skipped" in response["body"]


@patch.object(handler, "ssm")
@patch.object(handler, "ce")
def test_aggregates_costs_and_stores_in_ssm(mock_ce, mock_ssm):
    mock_ce.get_cost_and_usage.return_value = CE_RESPONSE
    with patch.object(handler, "date") as mock_date:
        mock_date.today.return_value = date(2024, 6, 15)
        handler.lambda_handler({}, None)

    stored = json.loads(mock_ssm.put_parameter.call_args[1]["Value"])
    assert stored["services"]["AWS Lambda"] == 0.5
    assert stored["services"]["Amazon S3"] == 0.25
    assert stored["currency"] == "USD"


@patch.object(handler, "ssm")
@patch.object(handler, "ce")
def test_filters_out_negligible_amounts(mock_ce, mock_ssm):
    mock_ce.get_cost_and_usage.return_value = CE_RESPONSE
    with patch.object(handler, "date") as mock_date:
        mock_date.today.return_value = date(2024, 6, 15)
        handler.lambda_handler({}, None)

    stored = json.loads(mock_ssm.put_parameter.call_args[1]["Value"])
    assert "Tiny Service" not in stored["services"]


@patch.object(handler, "ssm")
@patch.object(handler, "ce")
def test_total_is_sum_of_included_services(mock_ce, mock_ssm):
    mock_ce.get_cost_and_usage.return_value = CE_RESPONSE
    with patch.object(handler, "date") as mock_date:
        mock_date.today.return_value = date(2024, 6, 15)
        handler.lambda_handler({}, None)

    stored = json.loads(mock_ssm.put_parameter.call_args[1]["Value"])
    assert stored["total"] == round(0.5 + 0.25, 4)
