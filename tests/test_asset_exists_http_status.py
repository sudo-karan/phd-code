"""`asset_exists` reads the HTTP status behind a failed getAsset (round 14).

Round 13's question 42 (review C41), answer (a). earthengine-api 1.7.35, the version every
manifest records, raises its EEException inside `except HttpError` without `from`
(`ee.data._execute_cloud_call`), so the googleapiclient HttpError is the EEException's
`__context__` and its `__cause__` is None. `asset_exists` looked at `__cause__` only, so it never
read a status, and every answer came from the message: a 403 "does not exist or doesn't allow
this operation" and a 500 whose request id holds "404" read as a missing asset.

Now the HttpError is found on `__cause__` or `__context__`: a 404 is a missing asset, any other
status is raised, and only an error with no HttpError behind it is judged by its text, as before.

The errors here are real HttpErrors sent through `ee.data._execute_cloud_call` by a stand-in
request, as round 13 checked it (nothing goes over the network), with `ee.data.getAsset`
replaced by the call that raises them.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import ee
import httplib2
import pytest
from googleapiclient.errors import HttpError

from fmu.utils.caching import asset_exists, ensure_parent_folders

PATH = "projects/p/assets/fmu/a_config/masking/habitat_mask__s0123456789"


class _StandInRequest:
    """What `ee.data.getAsset` hands `_execute_cloud_call`, answering as the server did."""

    def __init__(self, error: HttpError) -> None:
        self.error = error

    def execute(self, num_retries: int | None = None):
        raise self.error


def _http_error(status: int, message: str) -> HttpError:
    resp = httplib2.Response({"status": status})
    content = json.dumps({"error": {"code": status, "message": message}}).encode()
    return HttpError(resp, content, uri=f"https://earthengine.googleapis.com/v1/{PATH}")


def _answering(status: int, message: str):
    """`ee.data.getAsset` as earthengine-api runs it, with this answer from the server."""
    error = _http_error(status, message)

    def get_asset(path: str):
        return ee.data._execute_cloud_call(_StandInRequest(error))

    return get_asset


def test_earthengine_api_puts_the_http_error_on_context_not_cause():
    """The premise: what `ee.data` raises for a failed call."""
    error = _http_error(404, "Asset 'x' not found.")
    with pytest.raises(ee.EEException) as info:
        ee.data._execute_cloud_call(_StandInRequest(error))
    assert info.value.__cause__ is None
    assert info.value.__context__ is error
    assert str(info.value) == "Asset 'x' not found."


@pytest.mark.parametrize(
    "message",
    [
        f"Asset '{PATH}' not found.",
        # None of the words the text test looks for: only the status can say it is missing.
        "Requested entity was deleted.",
    ],
    ids=["not found", "no telling words"],
)
def test_a_404_is_a_missing_asset(message):
    with patch.object(ee.data, "getAsset", side_effect=_answering(404, message)):
        assert asset_exists(PATH) is False


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (403, f"Asset '{PATH}' does not exist or doesn't allow this operation."),
        (403, "Permission denied."),
        (401, "Request had invalid authentication credentials."),
        (500, "An internal error has occurred (request id: 7b404e1c)."),
        (503, "The service is currently unavailable."),
    ],
    ids=["403 does not exist", "403 permission denied", "401", "500 with 404 in its id", "503"],
)
def test_any_other_status_is_raised(status, message):
    with patch.object(ee.data, "getAsset", side_effect=_answering(status, message)), \
         pytest.raises(ee.EEException) as info:
        asset_exists(PATH)
    assert str(info.value) == message


def test_an_http_error_on_cause_is_read_as_well():
    """A client that raises `from` the HttpError puts it on `__cause__`."""

    def chained(status: int, message: str):
        def get_asset(path: str):
            try:
                raise _http_error(status, message)
            except HttpError as e:
                raise ee.EEException(e.reason) from e

        return get_asset

    with patch.object(ee.data, "getAsset", side_effect=chained(404, "Asset 'x' is gone.")):
        assert asset_exists(PATH) is False
    with patch.object(ee.data, "getAsset", side_effect=chained(500, "Internal error 404.")), \
         pytest.raises(ee.EEException, match="Internal error 404"):
        asset_exists(PATH)


def test_the_http_error_is_found_further_down_the_chain():
    """An EEException wrapped again (as fmu.utils.gee.safe_call wraps one, with `from`) still
    has the HttpError behind it, on the inner error's `__context__`."""

    def wrapped(status: int, message: str):
        inner = _answering(status, message)

        def get_asset(path: str):
            try:
                return inner(path)
            except ee.EEException as e:
                raise ee.EEException(f"{e} [context: reading the cache]") from e

        return get_asset

    with patch.object(ee.data, "getAsset", side_effect=wrapped(404, "Requested entity was deleted.")):
        assert asset_exists(PATH) is False
    refused = f"Asset '{PATH}' does not exist or doesn't allow this operation."
    with patch.object(ee.data, "getAsset", side_effect=wrapped(403, refused)), \
         pytest.raises(ee.EEException, match="reading the cache"):
        asset_exists(PATH)


@pytest.mark.parametrize(
    ("message", "missing"),
    [
        (f"Asset '{PATH}' not found.", True),
        (f"Asset '{PATH}' does not exist.", True),
        ("Error 404 from the cache.", True),
        ("Something else went wrong.", False),
    ],
)
def test_with_no_http_error_behind_it_the_text_decides_as_before(message, missing):
    with patch.object(ee.data, "getAsset", side_effect=ee.EEException(message)):
        if missing:
            assert asset_exists(PATH) is False
        else:
            with pytest.raises(ee.EEException, match="Something else"):
                asset_exists(PATH)


def test_an_asset_that_answers_is_there():
    with patch.object(ee.data, "getAsset", return_value={"type": "IMAGE"}):
        assert asset_exists(PATH) is True


def test_a_folder_whose_check_is_refused_is_still_created():
    """ensure_parent_folders creates a folder whose check raises, as it created one whose 403
    read as missing: a new config's cache folders are made as before."""
    path = "projects/p/assets/fmu/new_config/masking/habitat_mask__s0123456789"
    created: list[str] = []
    refused = "Asset 'x' does not exist or doesn't allow this operation."
    with patch.object(ee.data, "getAsset", side_effect=_answering(403, refused)), \
         patch.object(ee.data, "createFolder", side_effect=created.append):
        ensure_parent_folders(path)
    assert created == [
        "projects/p/assets/fmu",
        "projects/p/assets/fmu/new_config",
        "projects/p/assets/fmu/new_config/masking",
    ]
