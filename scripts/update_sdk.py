#!/usr/bin/env python3
"""Track and package new TI MSPM0 SDK releases for the timspm0 platform.

The MSPM0 SDK lives in the `mspm0-sdk` git submodule of the wrapper
repository https://github.com/Berkays/toolchain-timspm0-sdk, pinned to a
release tag of https://github.com/TexasInstruments/mspm0-sdk.

This script bumps the wrapper to a newer TI release, maps TI's 4-component
version to a PlatformIO semver version (2.11.00.07 -> 2.11.0+7), commits,
tags, pushes and optionally publishes the package to the PlatformIO
Registry.

Usage:
  python3 scripts/update_sdk.py                     # list TI releases
  python3 scripts/update_sdk.py --latest            # bump to the newest
  python3 scripts/update_sdk.py --tag mspm0_sdk_2_11_00_07
  python3 scripts/update_sdk.py --latest --publish  # bump + pio pkg publish

Options:
  --wrapper-dir PATH   Local clone of toolchain-timspm0-sdk
                       (default: <platform repo>/../toolchain-timspm0-sdk,
                       cloned on demand)
  --no-push            Prepare the commit and tag but do not push
  --publish            Publish to the PlatformIO Registry after pushing
                       (requires `pio account login`)
"""

import argparse
import glob
import json
import re
import subprocess
import sys
import tempfile
from os import path

TI_SDK_REPO = "https://github.com/TexasInstruments/mspm0-sdk.git"
WRAPPER_REPO = "https://github.com/Berkays/toolchain-timspm0-sdk.git"
SYSCONFIG_TOOL_REPO = (
    "https://raw.githubusercontent.com/Berkays/tool-mspm0-sysconfig"
    "/main/package.json"
)
TAG_PREFIX = "mspm0_sdk_"


def version_tuple(version):
    """'2.11.00.07' -> (2, 11, 0, 7); ignores non-numeric suffixes."""
    return tuple(
        int(p) for p in re.findall(r"\d+", version.split("+")[0])
    )


def run(cmd, **kwargs):
    print("  $ " + " ".join(cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def run_output(cmd):
    return subprocess.run(
        cmd, check=True, capture_output=True, text=True
    ).stdout


def fail(message):
    print("Error: %s" % message, file=sys.stderr)
    sys.exit(1)


def ti_version_from_tag(tag):
    m = re.match(r"%s(\d+)_(\d+)_(\d+)_(\d+)$" % TAG_PREFIX, tag)
    if not m:
        return None
    return ".".join(m.groups())


def ti_to_semver(ti_version):
    """Map a TI 4-component version to a PlatformIO semver version.

    2.08.00.03 -> 2.8.0+3, 2.11.00.07 -> 2.11.0+7
    """
    major, minor, patch, build = ti_version.split(".")
    return "%d.%d.%d+%d" % (
        int(major), int(minor), int(patch), int(build))


def list_ti_releases():
    """Return [(tag, ti_version, sha)] of TI SDK releases, oldest first."""
    out = run_output(
        ["git", "ls-remote", "--tags", TI_SDK_REPO, "refs/tags/%s*" % TAG_PREFIX]
    )
    releases = []
    for line in out.strip().splitlines():
        sha, ref = line.split()
        tag = ref.replace("refs/tags/", "")
        # skip annotated-tag dereferences (^{})
        if tag.endswith("^{}"):
            continue
        ti_version = ti_version_from_tag(tag)
        if ti_version:
            releases.append((tag, ti_version, sha))
    releases.sort(key=lambda r: version_tuple(r[1]))
    return releases


def get_wrapper_state(wrapper_dir):
    with open(path.join(wrapper_dir, "package.json")) as fp:
        manifest = json.load(fp)
    submodule_pin = run_output(
        ["git", "-C", wrapper_dir, "submodule", "status"]
    ).split()[0]
    # submodule status prefixes the sha with " " (in sync), "+" (different
    # commit checked out) or "-" (not initialized)
    pinned_sha = submodule_pin.lstrip(" +-")
    return manifest, pinned_sha


def ensure_wrapper_repo(wrapper_dir):
    if path.isdir(path.join(wrapper_dir, ".git")):
        run(["git", "-C", wrapper_dir, "fetch", "--tags", "origin"])
        return
    print("Cloning the wrapper repository...")
    run(["git", "clone", WRAPPER_REPO, wrapper_dir])
    run(["git", "-C", wrapper_dir, "fetch", "--tags", "origin"])


def checkout_sdk_tag(wrapper_dir, tag, sha):
    sdk_dir = path.join(wrapper_dir, "mspm0-sdk")
    if not path.isdir(path.join(sdk_dir, ".git")):
        print("Initializing the mspm0-sdk submodule (large download)...")
        run(["git", "-C", wrapper_dir, "submodule", "update", "--init"])
    run(["git", "-C", sdk_dir, "fetch", "--tags", "--force", "origin"])
    # --force discards stray local modifications inside the submodule (the
    # submodule content is fully managed by the pinned tag)
    run(["git", "-C", sdk_dir, "checkout", "--detach", "--force", sha])
    return sdk_dir


def check_sysconfig_compat(sdk_dir):
    """Warn when the SDK requires a newer SysConfig than the packaged tool."""
    with open(path.join(sdk_dir, ".metadata", "product.json")) as fp:
        product = json.load(fp)
    min_tool = product.get("minToolVersion")
    if not min_tool:
        return
    tool_version = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            subprocess.run(
                ["curl", "-fsSL", SYSCONFIG_TOOL_REPO], stdout=tmp, check=True
            )
            with open(tmp.name) as fp:
                tool_version = json.load(fp).get("version")
    except subprocess.CalledProcessError:
        pass
    if tool_version and version_tuple(tool_version) < version_tuple(min_tool):
        print(
            "WARNING: MSPM0 SDK %s requires SysConfig >= %s but the packaged "
            "tool is %s. Update the tool-timspm0-sysconfig package "
            "(https://github.com/Berkays/tool-mspm0-sysconfig) before "
            "releasing!" % (product.get("version"), min_tool, tool_version)
        )


def report_new_device_families(wrapper_dir, boards_dir):
    """Info: SDK device families that have no board in this platform."""
    sdk_startups = path.join(
        wrapper_dir, "mspm0-sdk", "source", "ti", "devices", "msp", "m0p",
        "startup_system_files", "gcc")
    if not path.isdir(sdk_startups):
        return
    sdk_families = {
        re.match(r"startup_(\w+)_gcc\.c$", path.basename(f)).group(1)
        for f in glob.glob(path.join(sdk_startups, "startup_*_gcc.c"))
    }
    board_families = set()
    for board_file in glob.glob(path.join(boards_dir, "*.json")):
        with open(board_file) as fp:
            mcu = json.load(fp)["build"]["mcu"]
        board_families.add(mcu[:-1] + "x" if mcu[-1].isdigit() else mcu)
    new = sdk_families - board_families
    if new:
        print(
            "Info: the SDK adds startup support for %s which have no board "
            "JSON in this platform yet." % ", ".join(sorted(new))
        )


def bump_wrapper(wrapper_dir, tag, ti_version, semver, no_push):
    manifest, pinned_sha = get_wrapper_state(wrapper_dir)
    print(
        "Wrapper is at package version %s (submodule %s)"
        % (manifest["version"], pinned_sha[:9])
    )

    print("Bumping to TI SDK %s (package version %s)..." % (ti_version, semver))
    _, _, sha = next(r for r in list_ti_releases() if r[0] == tag)
    sdk_dir = checkout_sdk_tag(wrapper_dir, tag, sha)

    product_json = path.join(sdk_dir, ".metadata", "product.json")
    if not path.isfile(product_json):
        fail("TI SDK tag %s has no .metadata/product.json" % tag)
    with open(product_json) as fp:
        product = json.load(fp)
    # TI occasionally tags a build (e.g. _01) whose product.json still says
    # an earlier build (.00). The first three components must match the tag;
    # product.json is authoritative for the package version.
    if product.get("version", "").split(".")[:3] != ti_version.split(".")[:3]:
        fail(
            "SDK metadata version %s does not match tag %s"
            % (product.get("version"), tag)
        )
    if product.get("version") != ti_version:
        print(
            "Note: tag says %s but SDK metadata says %s (using metadata)"
            % (ti_version, product.get("version"))
        )
        ti_version = product["version"]
        semver = ti_to_semver(ti_version)

    if manifest["version"] == semver:
        print("The wrapper already packages SDK %s. Nothing to do." % ti_version)
        return False

    check_sysconfig_compat(sdk_dir)

    manifest["version"] = semver
    with open(path.join(wrapper_dir, "package.json"), "w") as fp:
        json.dump(manifest, fp, indent=4)
        fp.write("\n")

    run(["git", "-C", wrapper_dir, "add", "mspm0-sdk", "package.json"])
    run([
        "git", "-C", wrapper_dir, "commit",
        "-m", "Bump MSPM0 SDK to %s (%s)" % (ti_version, tag),
    ])
    tag_name = "v%s" % semver
    tag_result = subprocess.run(
        ["git", "-C", wrapper_dir, "tag", tag_name],
        capture_output=True, text=True
    )
    if tag_result.returncode == 0:
        print("Created tag %s" % tag_name)

    if not no_push:
        run(["git", "-C", wrapper_dir, "push", "origin", "main", "--tags"])

    print("Wrapper repository updated: %s" % wrapper_dir)
    print(
        "Publish to the PlatformIO Registry with:\n"
        "  pio pkg publish %s" % wrapper_dir
    )
    return True


def publish_wrapper(wrapper_dir):
    # Pack first: this validates the manifest (semver version, license, ...)
    # and reports the tarball size before anything is uploaded.
    with tempfile.TemporaryDirectory() as tmp_dir:
        archive = path.join(tmp_dir, "wrapper.tar.gz")
        run(["pio", "pkg", "pack", wrapper_dir, "-o", archive])
        print("Tarball size: %.1f MB" % (path.getsize(archive) / 1024 / 1024))
    run(["pio", "pkg", "publish", wrapper_dir, "--no-interactive"])


def main():
    parser = argparse.ArgumentParser(
        description="Update the PlatformIO MSPM0 SDK package from TI's repo")
    parser.add_argument(
        "--tag", help="TI release tag to bump to (e.g. mspm0_sdk_2_11_00_07)")
    parser.add_argument(
        "--latest", action="store_true", help="Bump to the newest TI release")
    parser.add_argument(
        "--wrapper-dir",
        default=path.join(
            path.dirname(path.abspath(__file__)), "..", "..",
            "toolchain-timspm0-sdk"),
        help="Local clone of the toolchain-timspm0-sdk wrapper repository")
    parser.add_argument(
        "--no-push", action="store_true",
        help="Commit and tag locally but do not push")
    parser.add_argument(
        "--publish", action="store_true",
        help="Publish to the PlatformIO Registry after bumping "
             "(requires `pio account login`)")
    args = parser.parse_args()

    releases = list_ti_releases()
    if not releases:
        fail("No %s* tags found in %s" % (TAG_PREFIX, TI_SDK_REPO))

    if not (args.tag or args.latest or args.publish):
        # Report mode: show what TI offers vs. what is packaged
        wrapper_dir = path.abspath(args.wrapper_dir)
        if path.isdir(wrapper_dir):
            manifest, pinned_sha = get_wrapper_state(wrapper_dir)
            current = "package %s, submodule %s" % (
                manifest["version"], pinned_sha[:9])
        else:
            current = "wrapper repository not found at %s" % wrapper_dir
        print("Packaged: %s" % current)
        print("TI MSPM0 SDK releases (newest last):")
        for tag, ti_version, sha in releases:
            print("  %-24s %s  %s" % (tag, ti_version, sha[:9]))
        print(
            "\nBump with: %s --latest  or  %s --tag <tag>"
            % (sys.argv[0], sys.argv[0])
        )
        return

    tag = args.tag
    if args.latest:
        tag = releases[-1][0]
    if not tag:
        parser.error("specify --tag or --latest")

    ti_version = ti_version_from_tag(tag)
    if not ti_version:
        fail("'%s' does not look like an mspm0_sdk_* release tag" % tag)
    if not any(r[0] == tag for r in releases):
        fail("tag %s not found in %s" % (tag, TI_SDK_REPO))

    wrapper_dir = path.abspath(args.wrapper_dir)
    ensure_wrapper_repo(wrapper_dir)
    changed = bump_wrapper(
        wrapper_dir, tag, ti_version, ti_to_semver(ti_version), args.no_push)

    boards_dir = path.join(
        path.dirname(path.abspath(__file__)), "..", "boards")
    report_new_device_families(wrapper_dir, boards_dir)

    if args.publish and changed:
        publish_wrapper(wrapper_dir)


if __name__ == "__main__":
    main()
