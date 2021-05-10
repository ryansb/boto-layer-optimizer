import json
import os
import shutil
from pathlib import Path
from subprocess import check_output


def _json_files(target):
    for parent, dirs, files in os.walk(target):
        for json_file in (Path(parent) / j for j in files if j.endswith(".json")):
            yield json_file


def _replace_documentation(obj):
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "documentation":
                obj[k] = ""
            else:
                obj[k] = _replace_documentation(v)
        return obj
    elif isinstance(obj, list):
        return [_replace_documentation(i) for i in obj]
    else:
        return obj


def strip_docs(json_file):
    with open(json_file) as f:
        raw = json.load(f)
    fixed = _replace_documentation(raw)
    with open(json_file, "w") as f:
        json.dump(fixed, f, separators=(',', ':'))


def dedent_json(json_file):
    """Open a whitespaced and readable JSON file and compact to sorted-key JSON"""
    with open(json_file) as f:
        raw = json.load(f)
    with open(json_file, "w") as f:
        json.dump(raw, f, sort_keys=True, separators=(',', ':'))


def walk_boto3_data(package_dir, actor):
    for json_file in _json_files(package_dir / "boto3/data"):
        actor(json_file)


def walk_botocore_data(package_dir, actor):
    for json_file in _json_files(package_dir / "botocore/data"):
        actor(json_file)


def strip_unused_services(package_dir, only_services):
    botocore = package_dir / "botocore/data"
    boto3 = package_dir / "boto3/data"
    for pkg in (botocore, boto3):
        for dirname, dirnames, filenames in os.walk(pkg):
            here = Path(dirname)
            if str(here.relative_to(pkg)) != ".":
                continue
            for d in dirnames:
                if d not in only_services:
                    shutil.rmtree(str(here / d))


def rm_cruft(package_dir):
    for dirpath, dirnames, filenames in reversed(list(os.walk(package_dir))):
        here = Path(dirpath)
        for d in dirnames:
            if d == "__pycache__":
                shutil.rmtree(here / d)
        for f in filenames:
            if f.endswith(".pyc"):
                os.unlink(here / f)
            if f.endswith("examples-1.json"):
                os.unlink(here / f)


def size_on_disk(dirname):
    return check_output(["du", "-sh", dirname], cwd=Path(".")).decode().strip().split("\t")[0]


def install_boto3(boto3_version) -> Path:
    package_dir = Path("/tmp") / f"pkg_boto3_{boto3_version}"
    if package_dir.exists():
        return package_dir

    package_dir.mkdir(parents=True)

    pip_result = check_output(
        [
            ".venv/bin/pip",
            "install",
            "-t",
            str(package_dir),
            f"boto3=={boto3_version}" if boto3_version else "boto3",
        ],
        cwd=Path("."),
    )
    print("----")
    print(pip_result.decode())
    print("----")
    return package_dir


def build_botocore_zip(layer_name, boto3_version=None, only_services=None):
    layer_root = Path("./cdk.out/layers") / layer_name
    package_dir = layer_root / "python" / "lib" / "python3.8" / "site-packages"
    if package_dir.exists():
        shutil.rmtree(layer_root, ignore_errors=True)
    package_dir.parent.mkdir(parents=True)

    source = install_boto3(boto3_version)
    shutil.copytree(source, package_dir)
    print(f"Saved botocore and boto3. Base size {size_on_disk(layer_root)}")
    rm_cruft(package_dir)
    print(f"Removed cache/pyc. Size {size_on_disk(layer_root)}")
    if only_services:
        strip_unused_services(package_dir, only_services)
        print(f"Removed all unused services. Size {size_on_disk(layer_root)}")
    walk_botocore_data(package_dir, dedent_json)
    walk_boto3_data(package_dir, dedent_json)
    print(f"Dedented JSON files. Size {size_on_disk(layer_root)}")
    walk_botocore_data(package_dir, strip_docs)
    walk_boto3_data(package_dir, strip_docs)
    print(f"Removed documentation. Size {size_on_disk(layer_root)}")
    versions = {}
    for pkg_info in os.listdir(package_dir):
        if not (package_dir / pkg_info).is_dir():
            pass
        if not pkg_info.endswith(".dist-info"):
            continue
        with open(package_dir / pkg_info / "METADATA") as f:
            version = [l.strip().split(":")[1].strip() for l in f.readlines() if l.startswith("Version:")][0]
            versions[pkg_info.split("-")[0]] = version

    return layer_root, versions


if __name__ == "__main__":
    build_botocore_zip("python", only_services=["iam", "s3", "dynamodb", "sts"])
