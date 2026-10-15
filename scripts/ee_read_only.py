"""Make an Earth Engine session unable to submit a task or change an asset.

    import ee_read_only
    ee_read_only.forbid_writes()      # after init_gee(), before anything else

Why this exists. Some tools read saved assets that must not be touched (the 14 `_repro`
folders of the demo set are evidence as well as data), and the pipeline's own code submits an
export whenever it is run with the cache on and finds something missing. Passing
`submit_exports=False` everywhere is the rule; this is the lock behind the rule. After
`forbid_writes()` every call that would start a batch task or create, copy, move, update or
delete an asset raises `EarthEngineWriteError` instead of reaching Earth Engine.

Reading is untouched: `getInfo`, `reduceRegion`, `getDownloadURL`, `listAssets`, `getAsset`.

No Earth Engine call is made by this module itself.
"""

from __future__ import annotations

from typing import Any

# Functions of `ee.data` that write. Each is replaced if the installed client has it.
_DATA_WRITES = (
    "exportImage", "exportTable", "exportVideo", "exportMap", "exportClassifier", "startProcessing",
    "startIngestion", "startTableIngestion", "startExternalImageIngestion",
    "createAsset", "createFolder", "createAssetHome", "create_assets", "copyAsset", "renameAsset",
    "deleteAsset", "updateAsset", "setAssetProperties", "setAssetAcl", "setIamPolicy",
    "updateProjectConfig", "cancelTask", "cancelOperation",
)


class EarthEngineWriteError(RuntimeError):
    """A tool that promised to be read-only tried to write to Earth Engine."""


def _refuse(name: str) -> Any:
    def refused(*_args: Any, **_kwargs: Any) -> Any:
        raise EarthEngineWriteError(
            f"{name} was called, but this run is read-only on Earth Engine: it submits no task "
            "and creates, changes or deletes no asset."
        )

    refused.__name__ = f"forbidden_{name.split('.')[-1]}"
    return refused


def forbid_writes(ee_module: Any = None) -> list[str]:
    """Replace every writing call of the Earth Engine client with one that raises.

    Returns the names it replaced, so a caller can print or record them. Calling it twice is
    harmless. `ee_module` is for tests; by default it is the installed `ee`.
    """
    if ee_module is None:
        import ee as ee_module  # noqa: N811 - the module is used as an object here

    replaced = []
    ee_module.batch.Task.start = _refuse("ee.batch.Task.start")
    replaced.append("ee.batch.Task.start")
    for name in _DATA_WRITES:
        if hasattr(ee_module.data, name):
            setattr(ee_module.data, name, _refuse(f"ee.data.{name}"))
            replaced.append(f"ee.data.{name}")
    return replaced
