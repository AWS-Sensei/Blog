import json
import sys
from unittest.mock import patch
from botocore.exceptions import ClientError

handler = sys.modules["cost_read_handler"]

COST_DATA = {"total": 1.23, "currency": "USD", "services": {"Lambda": 0.50}}


def test_options_preflight_returns_200():
    response = handler.lambda_handler({"httpMethod": "OPTIONS"}, {})
    assert response["statusCode"] == 200


@patch.object(handler, "ssm")
def test_returns_cost_data_from_ssm(mock_ssm):
    mock_ssm.get_parameter.return_value = {
        "Parameter": {"Value": json.dumps(COST_DATA)}
    }
    response = handler.lambda_handler({}, {})
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == COST_DATA


@patch.object(handler, "ssm")
def test_returns_503_when_parameter_not_found(mock_ssm):
    mock_ssm.get_parameter.side_effect = ClientError(
        {"Error": {"Code": "ParameterNotFound", "Message": "not found"}},
        "GetParameter",
    )
    response = handler.lambda_handler({}, {})
    assert response["statusCode"] == 503
    assert "not_ready" in response["body"]


@patch.object(handler, "ssm")
def test_reraises_unexpected_client_error(mock_ssm):
    mock_ssm.get_parameter.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}},
        "GetParameter",
    )
    try:
        handler.lambda_handler({}, {})
        assert False, "expected exception"
    except ClientError as e:
        assert e.response["Error"]["Code"] == "AccessDenied"
