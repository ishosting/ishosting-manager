#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""is*hosting order pre-validator — catches incompatible configs before API calls."""

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Final

@dataclass(frozen=True, slots=True)
class ParsedOS:
    """Parses OS codes like 'linux/ubuntu.24.x#64' or 'windows/win2025x16std#64'."""
    family: str  # linux, windows, freebsd
    distro: str  # ubuntu, debian, alma, centos, rocky, freebsd, win...
    version: str  # 24, 12, 9, etc.
    arch: str  # 64, 32

    @classmethod
    def from_code(cls, code: str) -> "ParsedOS":
        family = "unknown"
        distro = ""
        version = ""
        arch = "64"

        # Split arch
        if "#" in code:
            code, arch = code.rsplit("#", 1)

        # Split family/rest
        if "/" in code:
            family, rest = code.split("/", 1)
        else:
            rest = code

        family = family.lower()

        # Normalize family
        if family in ("freebsd",):
            family = "freebsd"
        elif family in ("windows", "win"):
            family = "windows"
        elif family in ("linux",):
            family = "linux"

        # Parse distro and version from rest
        rest_lower = rest.lower()

        if rest_lower.startswith("ubuntu"):
            distro = "ubuntu"
            version = rest_lower.removeprefix("ubuntu").lstrip(".")
        elif rest_lower.startswith("debian"):
            distro = "debian"
            version = rest_lower.removeprefix("debian").lstrip(".")
        elif rest_lower.startswith("alma"):
            distro = "alma"
            version = rest_lower.removeprefix("alma").lstrip(".")
        elif rest_lower.startswith("centos"):
            distro = "centos"
            version = rest_lower.removeprefix("centos").lstrip(".")
        elif rest_lower.startswith("rocky"):
            distro = "rocky"
            version = rest_lower.removeprefix("rocky").lstrip(".")
        elif rest_lower.startswith("freebsd"):
            distro = "freebsd"
            version = rest_lower.removeprefix("freebsd").lstrip(".")
        elif rest_lower.startswith("mikrotik"):
            distro = "mikrotik"
            version = rest_lower.removeprefix("mikrotik").lstrip(".")
        elif rest_lower.startswith("win"):
            distro = "windows"
            version = rest_lower
        else:
            distro = rest_lower
            version = ""

        # Extract major version number
        version = version.split(".")[0].rstrip("x").rstrip(".")

        return cls(family=family, distro=distro, version=version, arch=arch)

    def matrix_key(self, server_type: str) -> str | None:
        """Return the key used in compatibility matrices, or None if OS not in matrix."""
        matrix = VPS_OS_PANEL if server_type == "vps" else DEDICATED_OS_PANEL
        # Try to find a matching key
        for key in matrix:
            key_lower = key.lower()
            if self.distro == "ubuntu" and f"ubuntu {self.version}" in key_lower:
                return key
            if self.distro == "debian" and f"debian {self.version}" in key_lower:
                return key
            if self.distro == "alma" and f"almalinux {self.version}" in key_lower:
                return key
            if self.distro == "centos" and f"centos {self.version}" in key_lower:
                return key
            if self.distro == "rocky" and f"rockylinux {self.version}" in key_lower:
                return key
            if self.distro == "freebsd" and f"freebsd {self.version}" in key_lower:
                return key
            if self.distro == "mikrotik" and "mikrotik" in key_lower:
                return key
        return None


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.valid = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def merge(self, other: "ValidationResult") -> None:
        if not other.valid:
            self.valid = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": self.errors, "warnings": self.warnings}


# Panel name list of panel code prefixes that match
PANEL_ALIASES: Final[dict[str, list[str]]] = {
    "ISP Manager v6": ["ispmanager", "isp"],
    "cPanel": ["cpanel"],
    "cPanel Premier Metal": ["cpanel"],
    "DirectAdmin": ["directadmin"],
    "HestiaCP": ["hestiacp", "hestia"],
    "aaPanel": ["aapanel"],
    "FastPanel": ["fastpanel"],
}

VPS_PANELS: Final[list[str]] = [
    "ISP Manager v6", "cPanel", "DirectAdmin", "HestiaCP", "aaPanel", "FastPanel",
]

DEDICATED_PANELS: Final[list[str]] = [
    "ISP Manager v6", "cPanel Premier Metal", "DirectAdmin", "HestiaCP", "aaPanel", "FastPanel",
]

# VPS OS/Panel compatibility (Table 1.1)
# Only "+" (auto-install) and "ticket" (manual) entries stored.
# Any OS/panel combo missing from the matrix is unavailable.
VPS_OS_PANEL: Final[dict[str, dict[str, str]]] = {
    "AlmaLinux 8 x64":  {"ISP Manager v6": "+", "cPanel": "ticket", "DirectAdmin": "ticket", "aaPanel": "ticket", "FastPanel": "+"},
    "AlmaLinux 9 x64":  {"ISP Manager v6": "+", "cPanel": "+", "DirectAdmin": "ticket", "aaPanel": "ticket"},
    "CentOS 9 x64":     {"aaPanel": "ticket"},
    "Debian 11 x64":    {"ISP Manager v6": "+", "DirectAdmin": "ticket", "HestiaCP": "+", "aaPanel": "ticket", "FastPanel": "+"},
    "Debian 12 x64":    {"ISP Manager v6": "+", "DirectAdmin": "ticket", "HestiaCP": "+", "aaPanel": "ticket", "FastPanel": "+"},
    "Debian 13 x64":    {"DirectAdmin": "ticket", "aaPanel": "ticket"},
    "Ubuntu 20 x64":    {"DirectAdmin": "ticket", "aaPanel": "+", "FastPanel": "+"},
    "Ubuntu 22 x64":    {"ISP Manager v6": "+", "cPanel": "+", "DirectAdmin": "ticket", "HestiaCP": "+", "aaPanel": "+", "FastPanel": "+"},
    "Ubuntu 24 x64":    {"ISP Manager v6": "+", "DirectAdmin": "ticket", "HestiaCP": "+", "aaPanel": "+", "FastPanel": "+"},
    "RockyLinux 9 x64": {"cPanel": "+", "DirectAdmin": "ticket", "aaPanel": "ticket"},
}

# Dedicated OS/Panel compatibility (Table 1.2)
# Only "+" (auto-install) and "ticket" (manual) entries stored.
# Any OS/panel combo missing from the matrix is unavailable.
DEDICATED_OS_PANEL: Final[dict[str, dict[str, str]]] = {
    "AlmaLinux 8 x64":  {"ISP Manager v6": "+", "cPanel Premier Metal": "ticket", "DirectAdmin": "ticket", "FastPanel": "+"},
    "AlmaLinux 9 x64":  {"ISP Manager v6": "+", "cPanel Premier Metal": "+", "DirectAdmin": "ticket"},
    "CentOS 9 x64":     {"aaPanel": "ticket"},
    "Debian 11 x64":    {"ISP Manager v6": "+", "DirectAdmin": "ticket", "HestiaCP": "+", "aaPanel": "ticket", "FastPanel": "+"},
    "Debian 12 x64":    {"ISP Manager v6": "+", "DirectAdmin": "ticket", "HestiaCP": "+", "aaPanel": "ticket", "FastPanel": "+"},
    "Debian 13 x64":    {"DirectAdmin": "ticket", "aaPanel": "ticket"},
    "Ubuntu 20 x64":    {"DirectAdmin": "ticket", "aaPanel": "+", "FastPanel": "+"},
    "Ubuntu 22 x64":    {"ISP Manager v6": "+", "cPanel Premier Metal": "+", "DirectAdmin": "ticket", "HestiaCP": "+", "aaPanel": "+", "FastPanel": "+"},
    "Ubuntu 24 x64":    {"ISP Manager v6": "+", "DirectAdmin": "ticket", "HestiaCP": "+", "aaPanel": "+", "FastPanel": "+"},
}

def _resolve_panel(panel: str, server_type: str) -> str | None:
    """Resolve a panel code/name to the matrix column name. Returns None for 'none'."""
    if not panel or panel.lower() == "none":
        return None

    panels = VPS_PANELS if server_type == "vps" else DEDICATED_PANELS
    panel_lower = panel.lower().replace(" ", "").replace("-", "").replace("_", "")

    for matrix_name in panels:
        # Direct name match
        if panel_lower == matrix_name.lower().replace(" ", ""):
            return matrix_name
        # Check aliases
        for alias_name, prefixes in PANEL_ALIASES.items():
            if alias_name == matrix_name:
                for prefix in prefixes:
                    if panel_lower.startswith(prefix) or prefix.startswith(panel_lower):
                        return matrix_name

    return panel  # Return as-is if not found (will fail lookup gracefully)

def validate_os_panel(server_type: str, os_code: str, panel: str) -> ValidationResult:
    """OS/Panel compatibility matrix lookup. Error for N/A, warning for ticket."""
    result = ValidationResult()
    resolved_panel = _resolve_panel(panel, server_type)

    if resolved_panel is None:
        return result  # No panel selected, always valid

    parsed = ParsedOS.from_code(os_code)
    matrix_key = parsed.matrix_key(server_type)
    matrix = VPS_OS_PANEL if server_type == "vps" else DEDICATED_OS_PANEL

    # Verify panel name is known
    panels = VPS_PANELS if server_type == "vps" else DEDICATED_PANELS
    if resolved_panel not in panels:
        result.add_error(f"Panel '{panel}' not recognized for {server_type} servers")
        return result

    if matrix_key is None:
        # OS not in matrix → unavailable (new/unknown OS defaults to no panel support)
        result.add_error(f"Incompatible: OS '{os_code}' + {resolved_panel} is not supported for {server_type}")
        return result

    # Lookup: missing entry = unavailable
    compat = matrix.get(matrix_key, {}).get(resolved_panel)
    if compat is None:
        result.add_error(f"Incompatible: {matrix_key} + {resolved_panel} is not supported for {server_type}")
    elif compat == "ticket":
        result.add_warning(f"{matrix_key} + {resolved_panel} requires a support ticket for installation (not auto-installed)")

    return result


def validate_admin_panel(panel: str, admin: str) -> ValidationResult:
    """Administration requires a panel, but a panel can be used without administration."""
    result = ValidationResult()
    has_panel = bool(panel) and panel.lower() != "none"
    has_admin = bool(admin) and admin.lower() != "none"

    if has_admin and not has_panel:
        result.add_error("Administration requires a control panel — select a panel or remove administration")
    return result


def validate_disk_backup(server_type: str, disk_gb: float | None, backup: str) -> ValidationResult:
    """VPS: disk > 100GB means no backup."""
    result = ValidationResult()
    if server_type != "vps":
        return result
    if disk_gb is None or not backup or backup.lower() in ("none", "disabled", "no"):
        return result
    if disk_gb > 100:
        result.add_error(f"VPS backup is not available when disk > 100 GB (current: {disk_gb} GB). Disable backup or reduce disk size")
    return result


def validate_raid(server_type: str, drives: str | None, raid: str) -> ValidationResult:
    """Dedicated: RAID needs 2+ same-type/size drives."""
    result = ValidationResult()
    if server_type != "dedicated":
        return result
    if not raid or raid.lower() in ("none", "no"):
        return result
    if not drives:
        result.add_error("RAID requires at least 2 drives of the same type and size — no drives specified")
        return result

    # Parse drives JSON if provided
    try:
        drive_list = json.loads(drives) if isinstance(drives, str) else drives
    except (json.JSONDecodeError, TypeError):
        result.add_warning("Could not parse drives configuration — RAID compatibility not verified locally")
        return result

    if not isinstance(drive_list, list) or len(drive_list) < 2:
        result.add_error(f"RAID requires at least 2 drives of the same type and size (got {len(drive_list) if isinstance(drive_list, list) else 0})")
    return result


def validate_ddos_location(location: str, ddos: str) -> ValidationResult:
    """DDoS protection is only available in NL."""
    result = ValidationResult()
    if not ddos or ddos.lower() in ("none", "no"):
        return result
    if location and location.upper() != "NL":
        result.add_error(f"DDoS protection is only available in Netherlands (NL), not '{location.upper()}'")
    return result


def validate_os_restrictions(
    os_code: str,
    panel: str | None = None,
    admin: str | None = None,
    monitoring: str | None = None,
    server_type: str = "vps",
) -> ValidationResult:
    """Windows: no panels, no admin, no disk-monitoring. Panels/admin only for Linux+FreeBSD."""
    result = ValidationResult()
    parsed = ParsedOS.from_code(os_code)
    has_panel = panel and panel.lower() != "none"
    has_admin = admin and admin.lower() != "none"
    has_monitoring = monitoring and monitoring.lower() not in ("none", "no")

    if parsed.family == "windows":
        if has_panel:
            result.add_error(f"Control panels are not available for Windows (got panel='{panel}')")
        if has_admin:
            result.add_error("Administration is not available for Windows")
        if has_monitoring:
            result.add_error("Disk monitoring is not available for Windows")
        elif server_type == "dedicated" and (monitoring is None or monitoring == ""):
            result.add_warning(
                'Disk monitoring is auto-enabled by the API but incompatible with Windows. '
                'Add {"code":"none","category":"mondisk"} to --additions to disable it'
            )
    elif parsed.family not in ("linux", "freebsd"):
        if has_panel:
            result.add_error(f"Control panels are only available for Linux and FreeBSD (OS family: {parsed.family})")
        if has_admin:
            result.add_error(f"Administration is only available for Linux and FreeBSD (OS family: {parsed.family})")

    return result


def validate_order(
    server_type: str,
    os_code: str | None = None,
    panel: str | None = None,
    admin: str | None = None,
    disk_gb: float | None = None,
    backup: str | None = None,
    drives: str | None = None,
    raid: str | None = None,
    location: str | None = None,
    ddos: str | None = None,
    monitoring: str | None = None,
) -> ValidationResult:
    """Orchestrator — runs all applicable validation rules."""
    result = ValidationResult()

    if os_code and panel:
        result.merge(validate_os_panel(server_type, os_code, panel))

    if panel is not None or admin is not None:
        result.merge(validate_admin_panel(panel or "none", admin or "none"))

    if disk_gb is not None and backup is not None:
        result.merge(validate_disk_backup(server_type, disk_gb, backup))

    if raid is not None:
        result.merge(validate_raid(server_type, drives, raid))

    if location is not None and ddos is not None:
        result.merge(validate_ddos_location(location, ddos))

    if os_code:
        result.merge(validate_os_restrictions(os_code, panel, admin, monitoring, server_type))

    return result

def _parse_args(argv: list[str]) -> dict[str, str]:
    opts: dict[str, str] = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                opts[key] = argv[i + 1]
                i += 1
            else:
                opts[key] = "true"
        i += 1
    return opts


def cmd_validate_order(opts: dict[str, str]) -> dict[str, Any]:
    server_type = opts.get("type", "vps")
    disk_gb = float(opts["disk"]) if opts.get("disk") else None
    result = validate_order(
        server_type=server_type,
        os_code=opts.get("os"),
        panel=opts.get("panel"),
        admin=opts.get("administration"),
        disk_gb=disk_gb,
        backup=opts.get("backup"),
        drives=opts.get("drives"),
        raid=opts.get("raid"),
        location=opts.get("location"),
        ddos=opts.get("ddos"),
        monitoring=opts.get("disk_monitoring"),
    )
    return result.to_dict()


def cmd_validate_os_panel(opts: dict[str, str]) -> dict[str, Any]:
    server_type = opts.get("type", "vps")
    os_code = opts.get("os", "")
    panel = opts.get("panel", "none")
    result = validate_os_panel(server_type, os_code, panel)
    return result.to_dict()


def cmd_check_matrix(opts: dict[str, str]) -> dict[str, Any]:
    server_type = opts.get("type", "vps")
    matrix = VPS_OS_PANEL if server_type == "vps" else DEDICATED_OS_PANEL
    panels = VPS_PANELS if server_type == "vps" else DEDICATED_PANELS
    return {"type": server_type, "panels": panels, "matrix": matrix}


COMMANDS: Final[dict[str, Any]] = {
    "validate-order": {
        "desc": "Pre-validate a full order config",
        "opts": "--type --os --panel --administration --disk --backup --drives --raid --location --ddos --disk-monitoring",
        "handler": cmd_validate_order,
    },
    "validate-os-panel": {
        "desc": "Check OS/panel compatibility",
        "opts": "--type --os --panel",
        "handler": cmd_validate_os_panel,
    },
    "check-matrix": {
        "desc": "Show full compatibility matrix",
        "opts": "--type",
        "handler": cmd_check_matrix,
    },
}


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        cmds = "\n".join(f"  {name:25s} {meta['desc']}" for name, meta in COMMANDS.items())
        print(json.dumps({
            "status": "error",
            "message": "No command specified" if not args else "Help",
            "commands": {name: {"description": meta["desc"], "options": meta["opts"]} for name, meta in COMMANDS.items()},
        }, indent=2))
        return 0 if args else 1

    cmd = args[0]
    if cmd not in COMMANDS:
        print(json.dumps({"status": "error", "message": f"Unknown command: {cmd}", "available": list(COMMANDS.keys())}, indent=2))
        return 1

    opts = _parse_args(args[1:])
    result = COMMANDS[cmd]["handler"](opts)
    print(json.dumps(result, indent=2))

    # Exit code: 0 if valid/no errors, 1 if errors found
    if isinstance(result, dict) and "valid" in result:
        return 0 if result["valid"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
