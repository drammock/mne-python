from pathlib import Path

import requests
import tomllib
from packaging.requirements import Requirement
from packaging.version import Version

with open(Path("C:/Users/Carina/mne-python/pyproject.toml"), "rb") as fid:
    toml = tomllib.load(fid)

deps = toml["project"]["dependencies"] + toml["dependency-groups"]["test"]
reqs = [Requirement(dep) for dep in deps]
pinned_reqs = [req for req in reqs if ">" in str(req.specifier)]
unpinned_reqs = list(set(reqs) - set(pinned_reqs))

# store minimal versions
minimal_pinned_reqs = []

for req in pinned_reqs:
    pkg = req.name
    specset = req.specifier

    # get package info from pypi
    url = f"https://pypi.org/pypi/{pkg}/json"
    r = requests.get(url)

    if r.status_code == 404:
        print(f"Warning: cannot find {pkg} on PyPI, leaving unpinned")
        break

    # extract data
    data = r.json()

    # could be a placeholder
    if not data["releases"]:
        print(f"{pkg}: no releases on PyPI")
        break

    # unlikely (all releases are yanked?)
    if not any(
        not file.get("yanked", False)
        for files in data["releases"].values()
        for file in files
    ):
        print(f"{pkg}: all versions are yanked on PyPI")
        break

    # if package exists and has versions that are not yanked
    valid_versions = []
    for v, info in data["releases"].items():
        # skip yanked releases
        if any(file.get("yanked", False) for file in info):
            continue
        ver = Version(v)
        # this works for version specs > as well
        if ver in specset:
            valid_versions.append(ver)

    if not valid_versions:
        print(f"Warning: no non-yanked versions satisfy {pkg}{specset}")
        break

    # get the minimum version
    min_version = min(valid_versions)

    # rewrite specifier to ==
    pinned_req = Requirement(f"{pkg}=={min_version}")

    minimal_pinned_reqs.append(pinned_req)

# recombine pinned and not-pinned and sort
all_reqs = sorted(minimal_pinned_reqs + unpinned_reqs, key=str)

outfile = Path("C:/Users/Carina/mne-python/tools/requirements-ci-old.txt")
outfile.write_text("\n".join([str(req) for req in all_reqs]))
