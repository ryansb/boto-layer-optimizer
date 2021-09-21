import ast
import json
import os
import pickle
import shutil
import sys
import typing as t
from pathlib import Path
from subprocess import check_output

PY_VER = f"python{sys.version_info.major}.{sys.version_info.minor}"


def _json_files(target):
    for parent, _, files in os.walk(target):
        yield from (Path(parent) / j for j in files if j.endswith(".json"))


def _replace_documentation(obj):
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            obj[k] = "" if k == "documentation" else _replace_documentation(v)
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
        json.dump(fixed, f, separators=(",", ":"))


def dedent_json(json_file):
    """Open a whitespaced and readable JSON file and compact to sorted-key JSON"""
    with open(json_file) as f:
        raw = json.load(f)
    with open(json_file, "w") as f:
        json.dump(raw, f, sort_keys=True, separators=(",", ":"))


def walk_boto3_data(package_dir: Path, actor: t.Callable):
    for json_file in _json_files(package_dir / "boto3/data"):
        actor(json_file)


def walk_botocore_data(package_dir: Path, actor: t.Callable):
    for json_file in _json_files(package_dir / "botocore/data"):
        actor(json_file)


def strip_unused_services(package_dir: Path, only_services):
    botocore = package_dir / "botocore/data"
    boto3 = package_dir / "boto3/data"
    for pkg in (botocore, boto3):
        for dirname, dirnames, _ in os.walk(pkg):
            here = Path(dirname)
            if str(here.relative_to(pkg)) != ".":
                continue
            for d in dirnames:
                if d not in only_services:
                    shutil.rmtree(str(here / d))


def rm_cruft(package_dir: Path):
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


def size_on_disk(dirname: os.PathLike):
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


def _checkpoint(source: Path, dest: Path):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)


def build_botocore_zip(layer_name, boto3_version=None, only_services=None):
    layer_root = Path("./cdk.out/layers") / layer_name
    if layer_root.exists():
        shutil.rmtree(layer_root)
    package_dir = layer_root / "python" / "lib" / PY_VER / "site-packages"
    if package_dir.exists():
        shutil.rmtree(layer_root, ignore_errors=True)
    package_dir.parent.mkdir(parents=True)

    source = install_boto3(boto3_version)
    _checkpoint(source, package_dir)
    print(f"Saved botocore and boto3. Base size {size_on_disk(layer_root)}")
    rm_cruft(package_dir)
    print(f"Removed cache/pyc. Size {size_on_disk(layer_root)}")
    if only_services:
        strip_unused_services(package_dir, only_services)
        print(f"Removed all unused services. Size {size_on_disk(layer_root)}")
    _checkpoint(layer_root, Path("./cdk.out/layers") / f"{layer_name}-orig")

    with open(package_dir / "botocore" / "loaders.py", "r") as f:
        rewritten = rewrite_loaders_for_caching(f.read())
    with open(package_dir / "botocore" / "loaders.py", "w") as out:
        out.write(rewritten)

    walk_botocore_data(package_dir, dedent_json)
    walk_boto3_data(package_dir, dedent_json)
    _checkpoint(layer_root, Path("./cdk.out/layers") / f"{layer_name}-dedented")
    print(f"Dedented JSON files. Size {size_on_disk(layer_root)}")
    walk_botocore_data(package_dir, strip_docs)
    walk_boto3_data(package_dir, strip_docs)
    _checkpoint(layer_root, Path("./cdk.out/layers") / f"{layer_name}-dedented-docless")
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


def pickle_service_json(layer_root):
    new_root = Path(str(layer_root) + "-pickles")
    print("pickling", new_root)
    _checkpoint(layer_root, new_root)
    package_dir = new_root / "python" / "lib" / PY_VER / "site-packages"
    botocore_data = package_dir / "botocore" / "data"
    boto3_data = package_dir / "boto3" / "data"

    _to_pickles(botocore_data)
    _to_pickles(boto3_data)
    with open(package_dir / "botocore" / "loaders.py", "r") as f:
        rewritten = rewrite_loaders_for_pickling(f.read())
    with open(package_dir / "botocore" / "loaders.py", "w") as out:
        out.write(rewritten)


def _to_pickles(data_dir):
    for p, _, files in os.walk(data_dir):
        parent = Path(p)
        for f in files:
            if not f.endswith(".json"):
                continue
            with open(parent / f) as infile:
                with open(parent / f.replace(".json", ".pickle"), "wb") as outfile:
                    pickle.dump(json.load(infile), outfile)
            os.unlink(parent / f)


def _add_import(import_statement: str, target: ast.Module) -> None:
    first_import = next(idx for idx, statement in enumerate(target.body) if isinstance(statement, (ast.Import, ast.ImportFrom)))
    target.body.insert(first_import, ast.parse(import_statement).body)


def _find_class(name: str, target: ast.Module) -> t.Tuple[int, ast.ClassDef]:
    """Returns tuple containing index of classdef in the module and the ast.ClassDef object"""
    for idx, definition in enumerate(target.body):
        if isinstance(definition, ast.ClassDef) and definition.name == name:
            return idx, definition


def _find_function(name: str, target: t.Union[ast.Module, ast.ClassDef]) -> t.Tuple[int, ast.FunctionDef]:
    """Returns tuple containing index of classdef in the module and the ast.ClassDef object"""
    for idx, definition in enumerate(target.body):
        if isinstance(definition, ast.FunctionDef) and definition.name == name:
            return idx, definition


def rewrite_loaders_for_caching(python_code: str) -> str:
    if not hasattr(ast, "unparse"):
        raise NotImplementedError("Python 3.9+ required for AST rewriting")
    original_ast = ast.parse(python_code)

    _, _loader = _find_class("Loader", original_ast)

    _add_import("from functools import lru_cache", original_ast)

    _, available_services = _find_function("list_available_services", _loader)
    available_services.body = available_services.body[:1]

    available_services.body.extend(
        ast.parse(
            """
return sorted({
    k for (k, path)
    in services_by_path(tuple(self._potential_locations()), type_name)
    if self.file_loader.exists(path)
})
"""
        ).body
    )

    original_ast.body.extend(
        ast.parse(
            """
@lru_cache(20)
def services_by_path(locations, type_name):
    services = set()
    for possible_path in locations:
        possible_services = (d for d in os.listdir(possible_path) if os.path.isdir(os.path.join(possible_path, d)))
        for service_name in possible_services:
            full_dirname = os.path.join(possible_path, service_name)
            api_versions = os.listdir(full_dirname)
            for api_version in api_versions:
                full_load_path = os.path.join(full_dirname, api_version, type_name)
                services.add((service_name, full_load_path))
    return services"""
        ).body
    )

    return ast.unparse(original_ast)


def rewrite_loaders_for_pickling(python_code: str) -> str:
    if not hasattr(ast, "unparse"):
        raise NotImplementedError("Python 3.9+ required for AST rewriting")
    original_ast = ast.parse(python_code)
    _add_import("import pickle", original_ast)

    json_loader_index, _ = _find_class("JSONFileLoader", original_ast)

    original_ast.body.insert(
        json_loader_index,
        ast.parse(
            """
class PickleFileLoader(object):
    '''Inserted by uboto'''
    def exists(self, file_path):
        return os.path.isfile(file_path + '.pickle')
    def load_file(self, file_path):
        try:
            with open(file_path + '.pickle', 'rb') as fp:
                return pickle.load(fp)
        except (IsADirectoryError, FileNotFoundError):
            ..."""
        ).body,
    )

    _, _loader = _find_class("Loader", original_ast)
    assert "FILE_LOADER_CLASS" in [t.id for t in _loader.body[1].targets]
    _loader.body[1] = ast.parse("FILE_LOADER_CLASS = PickleFileLoader").body

    return ast.unparse(original_ast)
