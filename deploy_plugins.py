"""
Deploy QGIS Plugins

Created by Australis Asset Advisory Group

Scans the repository for QGIS plugin folders (identified by the presence of
both __init__.py and metadata.txt) and copies them into the local QGIS
plugins directory or uploads them to the official QGIS plugin repository.
Supports Windows, Linux, and macOS.  Detects available QGIS profiles and
lets the user choose which one to deploy to.
"""

import base64
import getpass
import os
import platform
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_PLUGIN_FILES = ("__init__.py", "metadata.txt")

QGIS_REPO_UPLOAD_URL = "https://plugins.qgis.org/api/v1/plugin/upload/"

UPLOAD_TIMEOUT_SECONDS = 60

# Metadata fields that must be non-empty before uploading to the repository.
# Names use the original case from metadata.txt for display purposes.
REQUIRED_METADATA_FOR_UPLOAD = (
    "name", "description", "version", "qgisMinimumVersion",
    "author", "about", "email", "homepage", "tracker", "repository",
)

# Directories and file patterns excluded from the plugin ZIP archive.
ZIP_EXCLUDE_DIRS = {
    ".git", "__pycache__", ".idea", ".vscode", "__MACOSX",
    ".mypy_cache", ".pytest_cache", "node_modules",
}
ZIP_EXCLUDE_EXTENSIONS = {".pyc", ".pyo"}

# Filenames recognised as a LICENSE file (case-insensitive check).
LICENSE_FILENAMES = {"license", "license.txt", "licence", "licence.txt"}


# ---------------------------------------------------------------------------
# Helpers — discovery and profiles
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


# ---------------------------------------------------------------------------
# Helpers — user interaction
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers — local deployment
# ---------------------------------------------------------------------------

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
# Helpers — repository upload
# ---------------------------------------------------------------------------

def read_metadata_fields(metadata_path):
    """Parse all key=value pairs from a QGIS metadata.txt file.

    Returns:
        dict: Mapping of lowercase field names to their values.
    """
    fields = {}
    try:
        with open(metadata_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("["):
                    continue
                if "=" in stripped:
                    key, _, value = stripped.partition("=")
                    fields[key.strip().lower()] = value.strip()
    except OSError:
        pass
    return fields


def validate_metadata_for_upload(metadata_path):
    """Check that all required metadata fields are present and non-empty.

    Returns:
        list[str]: List of validation error messages (empty if all valid).
    """
    fields = read_metadata_fields(metadata_path)
    errors = []
    for field in REQUIRED_METADATA_FOR_UPLOAD:
        value = fields.get(field.lower(), "")
        if not value:
            errors.append(f"  - '{field}' is missing or empty")
    return errors


def _find_license_in_dir(directory):
    """Return the path to a LICENSE file in *directory*, or None."""
    try:
        for entry in os.listdir(directory):
            if entry.lower() in LICENSE_FILENAMES:
                candidate = os.path.join(directory, entry)
                if os.path.isfile(candidate):
                    return candidate
    except OSError:
        pass
    return None


def create_plugin_zip(plugin_path, plugin_folder_name,
                      default_license=None):
    """Package a plugin directory as a ZIP file for repository upload.

    The ZIP contains a single top-level directory matching the plugin folder
    name.  Build artifacts, hidden directories, and compiled bytecode are
    excluded.

    If the plugin directory does not contain a LICENSE file and
    *default_license* is provided (path to a fallback LICENSE file), the
    fallback is automatically included in the ZIP as ``LICENSE``.

    Args:
        plugin_path: Full path to the plugin source directory.
        plugin_folder_name: Name used as the top-level directory in the ZIP.
        default_license: Optional path to a default LICENSE file to include
            when the plugin does not have its own.

    Returns:
        str: Path to the temporary ZIP file.
    """
    tmp_dir = tempfile.mkdtemp(prefix="qgis_plugin_")
    zip_path = os.path.join(tmp_dir, f"{plugin_folder_name}.zip")

    has_license = False

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(plugin_path):
            # Prune excluded directories in-place.
            dirs[:] = [
                d for d in dirs
                if d not in ZIP_EXCLUDE_DIRS and not d.startswith(".")
            ]
            for filename in files:
                _, ext = os.path.splitext(filename)
                if ext.lower() in ZIP_EXCLUDE_EXTENSIONS:
                    continue
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(
                    file_path, os.path.dirname(plugin_path),
                )
                zf.write(file_path, rel_path)
                # Track whether a LICENSE file was included.
                if (root == plugin_path
                        and filename.lower() in LICENSE_FILENAMES):
                    has_license = True

        # Inject default LICENSE if the plugin does not have one.
        if not has_license and default_license:
            if os.path.isfile(default_license):
                license_rel = os.path.join(plugin_folder_name, "LICENSE")
                zf.write(default_license, license_rel)
                print(f"  LICENSE not found in plugin — added default "
                      f"from {default_license}")

    return zip_path


def load_env_file(repo_root):
    """Load variables from a ``.env`` file into the process environment.

    Only sets variables that are not already defined so that real environment
    variables always take precedence.

    Args:
        repo_root: Repository root directory containing the ``.env`` file.
    """
    env_path = os.path.join(repo_root, ".env")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" not in stripped:
                    continue
                key, _, value = stripped.partition("=")
                key = key.strip()
                value = value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


def get_osgeo_credentials():
    """Obtain OSGeo credentials from environment variables or user prompt.

    Checks for ``OSGEO_USERNAME`` and ``OSGEO_PASSWORD`` environment
    variables (including values loaded from a ``.env`` file) first.
    Falls back to interactive prompts.

    Returns:
        tuple[str, str] or None: (username, password), or None if aborted.
    """
    username = os.environ.get("OSGEO_USERNAME", "")
    password = os.environ.get("OSGEO_PASSWORD", "")

    if username and password:
        print(f"\n  Using OSGeo credentials from environment variables "
              f"(user: {username}).")
        return username, password

    print("\n  Enter your OSGeo credentials (or press Ctrl+C to cancel).")
    if username:
        print(f"  Username from OSGEO_USERNAME: {username}")
    else:
        try:
            username = input("  OSGeo username: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not username:
            print("  Username cannot be empty.")
            return None

    try:
        password = getpass.getpass("  OSGeo password: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not password:
        print("  Password cannot be empty.")
        return None

    return username, password


def upload_plugin_to_repository(zip_path, username, password):
    """Upload a plugin ZIP to the official QGIS plugin repository.

    Uses HTTP Basic authentication with the provided OSGeo credentials.

    Args:
        zip_path: Path to the plugin ZIP file.
        username: OSGeo username.
        password: OSGeo password.

    Returns:
        tuple[bool, str]: (success, message).
    """
    filename = os.path.basename(zip_path)

    with open(zip_path, "rb") as fh:
        zip_data = fh.read()

    # Build multipart/form-data body.
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="package"; '
        f'filename="{filename}"\r\n'
        f"Content-Type: application/zip\r\n"
        f"\r\n"
    ).encode("utf-8") + zip_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    credentials = base64.b64encode(
        f"{username}:{password}".encode("utf-8"),
    ).decode("ascii")

    request = urllib.request.Request(
        QGIS_REPO_UPLOAD_URL,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Basic {credentials}",
        },
        method="POST",
    )

    try:
        response = urllib.request.urlopen(
            request, timeout=UPLOAD_TIMEOUT_SECONDS,
        )
        return True, f"HTTP {response.status} — upload accepted."
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        return False, f"HTTP {exc.code}: {exc.reason}. {detail}".strip()
    except urllib.error.URLError as exc:
        return False, f"Connection error: {exc.reason}"
    except OSError as exc:
        return False, f"Network error: {exc}"


def prepare_upload_flow(plugins, display, repo_root):
    """Prepare plugin ZIP files for first-time manual upload.

    Validates metadata, packages each selected plugin as a ZIP, and saves
    it to a ``dist/`` folder at the repository root.  The user can then
    upload the ZIP manually via https://plugins.qgis.org/plugins/add/.

    Args:
        plugins: List of (folder_name, folder_path) tuples.
        display: List of display strings for each plugin.
        repo_root: Repository root directory.
    """
    print("\n  First-time uploads must be done manually through the web")
    print("  interface.  This will create a ready-to-upload ZIP file in")
    print("  the dist/ folder at the repository root.")
    print("  Upload it at: https://plugins.qgis.org/plugins/add/")

    # --- Select plugins ---
    selection = prompt_choice(
        "Select plugins to prepare:", display, allow_all=True,
    )
    if selection is None:
        print("Aborted.")
        return

    # --- Validate metadata ---
    ready = []
    for idx in selection:
        folder_name, folder_path = plugins[idx]
        meta_path = os.path.join(folder_path, "metadata.txt")
        errors = validate_metadata_for_upload(meta_path)
        if errors:
            print(f"\n  {display[idx]}")
            print("  Missing required metadata fields:")
            for err in errors:
                print(err)
            print("  Skipping — update metadata.txt before uploading.")
        else:
            ready.append(idx)

    if not ready:
        print("\nNo plugins passed metadata validation.")
        return

    if len(ready) < len(selection):
        print(f"\n{len(ready)} of {len(selection)} plugin(s) passed "
              "metadata validation.")

    # --- Locate default LICENSE ---
    default_license = _find_license_in_dir(repo_root)

    # --- Create dist/ folder ---
    dist_dir = os.path.join(repo_root, "dist")
    os.makedirs(dist_dir, exist_ok=True)

    # --- Package ---
    prepared = 0
    for idx in ready:
        folder_name, folder_path = plugins[idx]
        print(f"\nPackaging {display[idx]} ...")
        try:
            tmp_zip = create_plugin_zip(
                folder_path, folder_name,
                default_license=default_license,
            )
        except OSError as exc:
            print(f"  Error creating ZIP: {exc}")
            continue

        dest_zip = os.path.join(dist_dir, f"{folder_name}.zip")

        # Handle existing ZIP with overwrite prompt and file-lock retry.
        if os.path.isfile(dest_zip):
            overwrite = False
            while True:
                try:
                    answer = input(
                        f"  {os.path.basename(dest_zip)} already exists in "
                        "dist/. Overwrite? (y/n): "
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if answer in ("y", "yes"):
                    overwrite = True
                    break
                if answer in ("n", "no"):
                    print(f"  Skipped {folder_name}.")
                    break
                print("  Please enter y or n.")

            if not overwrite:
                try:
                    shutil.rmtree(os.path.dirname(tmp_zip))
                except OSError:
                    pass
                continue

            while True:
                try:
                    os.remove(dest_zip)
                    break
                except PermissionError:
                    print(f"\n  Cannot overwrite {dest_zip} — file may be "
                          "locked.")
                    try:
                        input("  Close any programs using it, then press "
                              "Enter to retry (or Ctrl+C to skip): ")
                    except (EOFError, KeyboardInterrupt):
                        print(f"\n  Skipped {folder_name}.")
                        break
                except OSError as exc:
                    print(f"  Error removing existing ZIP: {exc}")
                    break

            if os.path.isfile(dest_zip):
                try:
                    shutil.rmtree(os.path.dirname(tmp_zip))
                except OSError:
                    pass
                continue

        # Move ZIP from temp to dist/.
        try:
            shutil.move(tmp_zip, dest_zip)
        except OSError as exc:
            print(f"  Error moving ZIP to dist/: {exc}")
            try:
                shutil.rmtree(os.path.dirname(tmp_zip))
            except OSError:
                pass
            continue

        # Clean up temp directory.
        try:
            shutil.rmtree(os.path.dirname(tmp_zip))
        except OSError:
            pass

        zip_size = os.path.getsize(dest_zip)
        print(f"  Created dist/{os.path.basename(dest_zip)} "
              f"({zip_size / 1024:.1f} KB)")
        prepared += 1

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f"  {prepared} of {len(ready)} plugin(s) prepared in dist/")
    if prepared > 0:
        print(f"\n  Upload your ZIP file(s) manually at:")
        print(f"  https://plugins.qgis.org/plugins/add/")
        print(f"\n  Once approved, future updates can be uploaded via")
        print(f"  the 'Upload to QGIS plugin repository' option.")
    print("=" * 60)


def upload_flow(plugins, display, repo_root):
    """Orchestrate the plugin upload to the QGIS repository.

    Validates metadata, collects credentials, packages each selected plugin
    as a ZIP, and uploads it to the official QGIS plugin repository.

    Args:
        plugins: List of (folder_name, folder_path) tuples.
        display: List of display strings for each plugin.
        repo_root: Repository root directory.
    """
    # --- Select plugins to upload ---
    selection = prompt_choice(
        "Select plugins to upload:", display, allow_all=True,
    )
    if selection is None:
        print("Aborted.")
        return

    # --- Validate metadata ---
    ready = []
    for idx in selection:
        folder_name, folder_path = plugins[idx]
        meta_path = os.path.join(folder_path, "metadata.txt")
        errors = validate_metadata_for_upload(meta_path)
        if errors:
            print(f"\n  {display[idx]}")
            print("  Missing required metadata fields:")
            for err in errors:
                print(err)
            print("  Skipping — update metadata.txt before uploading.")
        else:
            ready.append(idx)

    if not ready:
        print("\nNo plugins passed metadata validation.")
        return

    if len(ready) < len(selection):
        print(f"\n{len(ready)} of {len(selection)} plugin(s) passed "
              "metadata validation.")

    # --- Credentials ---
    creds = get_osgeo_credentials()
    if creds is None:
        print("Aborted.")
        return
    username, password = creds

    # --- Locate default LICENSE ---
    default_license = _find_license_in_dir(repo_root)

    # --- Package and upload ---
    uploaded = 0
    for idx in ready:
        folder_name, folder_path = plugins[idx]
        print(f"\nPackaging {display[idx]} ...")
        try:
            zip_path = create_plugin_zip(
                folder_path, folder_name,
                default_license=default_license,
            )
        except OSError as exc:
            print(f"  Error creating ZIP: {exc}")
            continue

        zip_size = os.path.getsize(zip_path)
        print(f"  Created {os.path.basename(zip_path)} "
              f"({zip_size / 1024:.1f} KB)")

        print(f"  Uploading to {QGIS_REPO_UPLOAD_URL} ...")
        success, message = upload_plugin_to_repository(
            zip_path, username, password,
        )

        # Clean up temp file.
        try:
            shutil.rmtree(os.path.dirname(zip_path))
        except OSError:
            pass

        if success:
            print(f"  Upload successful: {message}")
            uploaded += 1
        else:
            print(f"  Upload failed: {message}")

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f"  {uploaded} of {len(ready)} plugin(s) uploaded successfully.")
    if uploaded > 0:
        print("  New plugins will be reviewed and approved by the QGIS")
        print("  plugin approval team (typically within 1-2 business days).")
        print("  Updates to existing plugins are usually approved daily.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Helpers — local deployment flow
# ---------------------------------------------------------------------------

def deploy_local_flow(plugins, display):
    """Orchestrate local plugin deployment to a QGIS profile.

    Locates the QGIS profiles directory, lets the user select a profile,
    then copies selected plugins into that profile's plugin folder.

    Args:
        plugins: List of (folder_name, folder_path) tuples.
        display: List of display strings for each plugin.
    """
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
                return
            if custom.upper() == "Q":
                return
            if os.path.isdir(custom):
                profiles_root = custom
                break
            print(f"Directory not found: {custom}")

    # --- Select profile ---
    profiles = list_profiles(profiles_root)
    if not profiles:
        print(f"\nNo profiles found under {profiles_root}.")
        return

    if len(profiles) == 1:
        profile = profiles[0]
        print(f"\nUsing QGIS profile: {profile}")
    else:
        selection = prompt_choice("Select a QGIS profile:", profiles)
        if selection is None:
            print("Aborted.")
            return
        profile = profiles[selection[0]]

    target_plugins_dir = plugins_dir_for_profile(profiles_root, profile)
    os.makedirs(target_plugins_dir, exist_ok=True)
    print(f"Target directory: {target_plugins_dir}")

    # --- Select plugins to deploy ---
    selection = prompt_choice(
        "Select plugins to deploy:", display, allow_all=True,
    )
    if selection is None:
        print("Aborted.")
        return

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

    # Load .env file (credentials, etc.) if present.
    load_env_file(repo_root)

    # --- Discover plugins ---
    plugins = discover_plugins(repo_root)
    if not plugins:
        print("\nNo plugins found in the repository.")
        print("A valid plugin folder inside plugins/ must contain both "
              "__init__.py and metadata.txt.")
        sys.exit(0)

    # --- Build display names ---
    display = []
    for folder_name, folder_path in plugins:
        meta_path = os.path.join(folder_path, "metadata.txt")
        friendly = read_plugin_name(meta_path) or folder_name
        display.append(f"{friendly}  ({folder_name}/)")

    # --- Choose action ---
    action = prompt_choice("What would you like to do?", [
        "Deploy to local QGIS profile",
        "Upload to QGIS plugin repository (plugins.qgis.org)",
        "Prepare ZIP for first-time upload (new plugin)",
    ])
    if action is None:
        print("Aborted.")
        sys.exit(0)

    if action[0] == 0:
        deploy_local_flow(plugins, display)
    elif action[0] == 1:
        upload_flow(plugins, display, repo_root)
    else:
        prepare_upload_flow(plugins, display, repo_root)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(0)
