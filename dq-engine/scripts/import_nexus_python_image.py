#!/usr/bin/env python3
"""Import the Nexus Python base image into the local Docker daemon."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def build_auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def fetch_json(url: str, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def download_file(url: str, headers: dict[str, str], destination: Path) -> None:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response, destination.open("wb") as file_handle:
        shutil.copyfileobj(response, file_handle)


def normalize_registry_url(registry_url: str) -> str:
    return registry_url.removeprefix("https://").removeprefix("http://").rstrip("/")


def select_platform_manifest(index: dict, architecture: str) -> str:
    for manifest in index.get("manifests", []):
        platform = manifest.get("platform", {})
        if platform.get("os") == "linux" and platform.get("architecture") == architecture:
            return manifest["digest"]
    raise RuntimeError(f"No linux/{architecture} manifest found")


def safe_relpath(path: str) -> Path:
    normalized = Path(path.lstrip("./"))
    if any(part == ".." for part in normalized.parts):
        raise RuntimeError(f"Refusing suspicious layer path: {path}")
    return normalized


def clear_path(target: Path) -> None:
    if target.is_symlink() or target.is_file():
        target.unlink(missing_ok=True)
    elif target.is_dir():
        shutil.rmtree(target)


def apply_layer(rootfs: Path, layer_tar: Path) -> None:
    with tarfile.open(layer_tar, mode="r:*") as archive:
        for member in archive.getmembers():
            relative_path = safe_relpath(member.name)
            if not relative_path.parts:
                continue

            basename = relative_path.name
            parent = rootfs.joinpath(*relative_path.parts[:-1])

            if basename == ".wh..wh..opq":
                if parent.exists():
                    for child in list(parent.iterdir()):
                        clear_path(child)
                continue

            if basename.startswith(".wh."):
                clear_path(parent / basename[4:])
                continue

            archive.extract(member, path=rootfs)


def tar_rootfs(rootfs: Path, tar_path: Path) -> None:
    with tarfile.open(tar_path, mode="w") as archive:
        for child in sorted(rootfs.rglob("*")):
            archive.add(child, arcname=child.relative_to(rootfs), recursive=False)


def docker_import(image_ref: str, rootfs_tar: Path, env_values: list[str], working_dir: str | None) -> None:
    command = ["docker", "import"]
    for env_value in env_values:
        command.extend(["--change", f"ENV {env_value}"])
    if working_dir:
        command.extend(["--change", f"WORKDIR {working_dir}"])
    command.extend([str(rootfs_tar), image_ref])
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-url", required=True)
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    if subprocess.run(["docker", "image", "inspect", args.image_ref], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        return 0

    registry_url = args.registry_url.rstrip("/")
    headers = {
        "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json",
    }
    if args.username and args.password:
        headers["Authorization"] = build_auth_header(args.username, args.password)

    index_url = f"{registry_url}/v2/{args.image_path}/manifests/{args.tag}"
    index = fetch_json(index_url, headers)

    host_arch = os.uname().machine
    architecture_map = {
        "arm64": "arm64",
        "aarch64": "arm64",
        "x86_64": "amd64",
        "amd64": "amd64",
    }
    architecture = architecture_map.get(host_arch, host_arch)
    manifest_digest = select_platform_manifest(index, architecture)

    manifest_headers = {
        "Accept": "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json",
    }
    if args.username and args.password:
        manifest_headers["Authorization"] = build_auth_header(args.username, args.password)

    manifest_url = f"{registry_url}/v2/{args.image_path}/manifests/{manifest_digest}"
    manifest = fetch_json(manifest_url, manifest_headers)

    config_digest = manifest["config"]["digest"]
    layer_digests = [layer["digest"] for layer in manifest.get("layers", [])]

    with tempfile.TemporaryDirectory(prefix="nexus-python-import-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        layers_dir = temp_dir / "layers"
        rootfs_dir = temp_dir / "rootfs"
        layers_dir.mkdir()
        rootfs_dir.mkdir()

        config_path = temp_dir / "config.json"
        download_file(f"{registry_url}/v2/{args.image_path}/blobs/{config_digest}", manifest_headers, config_path)
        config = json.loads(config_path.read_text())

        env_values = list(config.get("config", {}).get("Env", []))
        working_dir = config.get("config", {}).get("WorkingDir")

        for digest in layer_digests:
            layer_path = layers_dir / digest.replace(":", "_")
            download_file(f"{registry_url}/v2/{args.image_path}/blobs/{digest}", manifest_headers, layer_path)
            apply_layer(rootfs_dir, layer_path)

        rootfs_tar = temp_dir / "rootfs.tar"
        tar_rootfs(rootfs_dir, rootfs_tar)
        docker_import(args.image_ref, rootfs_tar, env_values, working_dir)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"HTTP error importing Nexus Python image: {exc}", file=sys.stderr)
        raise SystemExit(exc.code)
    except Exception as exc:  # pragma: no cover - surfaced to the shell wrapper
        print(f"Failed to import Nexus Python image: {exc}", file=sys.stderr)
        raise SystemExit(1)