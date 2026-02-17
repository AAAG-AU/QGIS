"""
Deploy QGIS Plugins

Created by Australis Asset Advisory Group

Scans the repository for QGIS plugin folders (identified by the presence of
both __init__.py and metadata.txt) and copies them into the local QGIS
plugins directory.  Supports Windows, Linux, and macOS.  Detects available
QGIS profiles and lets the user choose which one to deploy to.
"""

import os
import platform
import shutil
import sys

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_PLUGIN_FILES = ("__init__.py", "metadata.txt")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_qgis_profiles_root():
    """Return the path to the QGIS3 profiles directory for this platform.

    Returns:
        str or None if the directory cannot be determined.
    """
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return os.path.join(appdata, "QGIS", "QGIS3", "profiles")
    elif system == "Linux":
        return os.path.join(
            os.path.expanduser("~"),
            ".local", "share", "QGIS", "QGIS3", "profiles",
        )
    elif system == "Darwin":
        return os.path.join(
            os.path.expanduser("~"),
            "Library", "Application Support", "QGIS", "QGIS3", "profiles",
        )
    return None


def list_profiles(profiles_root):
    """Return a sorted list of QGIS profile names found under *profiles_root*.

    Only directories are considered; files like ``profiles.ini`` are skipped.
    """
    if not os.path.isdir(profiles_root):
        return []
    return sorted(
        entry
        for entry in os.listdir(profiles_root)
        if os.path.isdir(os.path.join(profiles_root, entry))
    )


def plugins_dir_for_profile(profiles_root, profile_name):
    """Return the full path to the ``python/plugins`` folder for a profile."""
    return os.path.join(
        profiles_root, profile_name, "python", "plugins",
    )


def discover_plugins(repo_root):
    """Scan *repo_root*/plugins/ for QGIS plugin folders.

    Plugins are expected to live under a ``plugins/`` directory at the
    repository root.  A subfolder is considered a plugin if it contains
    both ``__init__.py`` and ``metadata.txt`` at its top level.

    Returns:
        list[tuple[str, str]]: (plugin_folder_name, full_path) pairs.
    """
    plugins_dir = os.path.join(repo_root, "plugins")
    if not os.path.isdir(plugins_dir):
        return []
    plugins = []
    for entry in sorted(os.listdir(plugins_dir)):
        entry_path = os.path.join(plugins_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        if entry.startswith("."):
            continue
        if all(
            os.path.isfile(os.path.join(entry_path, req))
            for req in REQUIRED_PLUGIN_FILES
        ):
            plugins.append((entry, entry_path))
    return plugins


def read_plugin_name(metadata_path):
    """Read the ``name`` field from a QGIS metadata.txt file.

    Returns the name string, or None if it cannot be read.
    """
    try:
        with open(metadata_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.strip().lower().startswith("name="):
                    return line.strip().split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def prompt_choice(prompt_text, options, allow_all=False):
    """Prompt the user to pick one or more numbered options.

    Args:
        prompt_text: Header text printed before the numbered list.
        options:     List of display strings.
        allow_all:   If True an extra "All" option is appended.

    Returns:
        list[int]: Selected 0-based indices, or ``None`` if the user quits.
    """
    print(f"\n{prompt_text}")
    for idx, opt in enumerate(options, start=1):
        print(f"  {idx}. {opt}")
    if allow_all:
        print(f"  A. All")
    print(f"  Q. Quit")

    while True:
        try:
            raw = input("\nChoice: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if not raw:
            continue

        upper = raw.upper()
        if upper == "Q":
            return None
        if allow_all and upper == "A":
            return list(range(len(options)))

        # Accept comma-separated numbers.
        parts = [p.strip() for p in raw.split(",")]
        indices = []
        valid = True
        for part in parts:
            if not part.isdigit():
                valid = False
                break
            num = int(part) - 1
            if num < 0 or num >= len(options):
                valid = False
                break
            indices.append(num)
        if valid and indices:
            return indices

        print("Invalid selection. Enter a number, comma-separated numbers, "
              f"{'A for all, ' if allow_all else ''}or Q to quit.")


def copy_plugin(src_path, dest_path):
    """Copy a plugin folder from *src_path* to *dest_path*.

    If *dest_path* already exists the user is asked whether to overwrite.
    Handles file-lock errors by prompting the user to close the file and
    retry.

    Returns:
        True on success, False on skip/failure.
    """
    plugin_name = os.path.basename(src_path)

    if os.path.exists(dest_path):
        print(f"\n  Plugin folder already exists: {dest_path}")
        while True:
            try:
                answer = input("  Overwrite? (y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return False
            if answer in ("y", "yes"):
                break
            if answer in ("n", "no"):
                print(f"  Skipped {plugin_name}.")
                return False
            print("  Please enter y or n.")

        # Remove existing folder, retrying on lock errors.
        while True:
            try:
                shutil.rmtree(dest_path)
                break
            except PermissionError:
                print(f"\n  Cannot remove {dest_path} — a file may be locked.")
                try:
                    input("  Close any programs using it, then press Enter to "
                          "retry (or Ctrl+C to skip): ")
                except (EOFError, KeyboardInterrupt):
                    print(f"\n  Skipped {plugin_name}.")
                    return False

    # Copy the plugin folder, retrying on lock errors.
    while True:
        try:
            shutil.copytree(src_path, dest_path)
            return True
        except PermissionError:
            print(f"\n  Cannot copy to {dest_path} — a file may be locked.")
            try:
                input("  Close any programs using it, then press Enter to "
                      "retry (or Ctrl+C to skip): ")
            except (EOFError, KeyboardInterrupt):
                print(f"\n  Skipped {plugin_name}.")
                return False
        except OSError as exc:
            print(f"\n  Error copying {plugin_name}: {exc}")
            return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Entry point for the plugin deployment script."""
    print("=" * 60)
    print("  QGIS Plugin Deployer")
    print("  Australis Asset Advisory Group")
    print("=" * 60)

    # Determine repository root (directory containing this script).
    repo_root = os.path.dirname(os.path.abspath(__file__))

    # --- Discover plugins ---
    plugins = discover_plugins(repo_root)
    if not plugins:
        print("\nNo plugins found in the repository.")
        print("A valid plugin folder inside plugins/ must contain both "
              "__init__.py and metadata.txt.")
        sys.exit(0)

    # --- Locate QGIS profiles directory ---
    profiles_root = get_qgis_profiles_root()
    if profiles_root is None or not os.path.isdir(profiles_root):
        print("\nCould not locate the QGIS3 profiles directory.")
        while True:
            try:
                custom = input(
                    "Enter the full path to the QGIS3 profiles directory "
                    "(or Q to quit): "
                ).strip().strip('"').strip("'")
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                sys.exit(0)
            if custom.upper() == "Q":
                sys.exit(0)
            if os.path.isdir(custom):
                profiles_root = custom
                break
            print(f"Directory not found: {custom}")

    # --- Select profile ---
    profiles = list_profiles(profiles_root)
    if not profiles:
        print(f"\nNo profiles found under {profiles_root}.")
        sys.exit(1)

    if len(profiles) == 1:
        profile = profiles[0]
        print(f"\nUsing QGIS profile: {profile}")
    else:
        selection = prompt_choice("Select a QGIS profile:", profiles)
        if selection is None:
            print("Aborted.")
            sys.exit(0)
        profile = profiles[selection[0]]

    target_plugins_dir = plugins_dir_for_profile(profiles_root, profile)
    os.makedirs(target_plugins_dir, exist_ok=True)
    print(f"Target directory: {target_plugins_dir}")

    # --- Select plugins to deploy ---
    display = []
    for folder_name, folder_path in plugins:
        meta_path = os.path.join(folder_path, "metadata.txt")
        friendly = read_plugin_name(meta_path) or folder_name
        display.append(f"{friendly}  ({folder_name}/)")

    selection = prompt_choice(
        "Select plugins to deploy:", display, allow_all=True,
    )
    if selection is None:
        print("Aborted.")
        sys.exit(0)

    # --- Deploy ---
    deployed = 0
    for idx in selection:
        folder_name, folder_path = plugins[idx]
        dest = os.path.join(target_plugins_dir, folder_name)
        friendly = display[idx]
        print(f"\nDeploying {friendly} ...")
        if copy_plugin(folder_path, dest):
            print(f"  Installed to {dest}")
            deployed += 1

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f"  {deployed} of {len(selection)} plugin(s) deployed successfully.")
    if deployed > 0:
        print("  Restart QGIS and enable the plugin(s) via")
        print("  Plugins > Manage and Install Plugins.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(0)
