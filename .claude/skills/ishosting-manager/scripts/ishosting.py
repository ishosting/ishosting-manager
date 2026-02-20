#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""is*hosting API — polymorphic interface with zero-arg defaults."""

import base64
import json
import os
import ssl
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.client import IncompleteRead
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError


# TYPES
type Args = dict[str, Any]
type CmdBuilder = Callable[[Args], tuple[str, str, dict[str, Any] | None]]
type OutputFormatter = Callable[[dict[str, Any], Args], dict[str, Any]]
type Handler = tuple[CmdBuilder, OutputFormatter]

# CONSTANTS
@dataclass(frozen=True, slots=True)
class _B:
    base_url: str = "ISHOSTING_BASE_URL"
    token_env: str = "ISHOSTING_TOKEN"
    base_auth: str = "ISHOSTING_BASE_AUTH"
    language: str = "ISHOSTING_API_LANGUAGE"
    limit: int = 30
    timeout: int = 30
    encoding: str = "utf-8"
    user_agent: str = "ishosting-manager-skill"
    page: int = 1


B: Final[_B] = _B()

SCRIPT_PATH: Final[str] = "uv run .claude/skills/ishosting-manager/scripts/ishosting.py"

# Keys to exclude from body when building PATCH payloads
_EXCLUDE_KEYS: Final[frozenset[str]] = frozenset({"id", "action", "protocol", "ip", "code"})

# Valid actions for status-change commands
VALID_ACTIONS: Final[dict[str, frozenset[str]]] = {
    "vps": frozenset({"start", "stop", "reboot", "force", "cancel"}),
    "storage": frozenset({"cancel"}),
    "dedicated": frozenset({"start", "stop", "reboot", "cancel"}),
    "vpn": frozenset({"start", "stop", "reboot", "force", "cancel"}),
}


def _find_project_root(start: Path) -> Path | None:
    """Walk up from start to find project root (directory containing .git)."""
    current = start.resolve()
    for _ in range(10):  # Max 10 levels up to prevent infinite traversal
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _load_env_file() -> None:
    """Search for and load .env file from project root or user config."""
    script_dir = Path(__file__).resolve().parent

    # Determine project root via .git marker (safe anchor point)
    project_root = _find_project_root(script_dir)

    search_paths: list[Path] = []
    if project_root:
        search_paths.append(project_root)
    # Fallback: script's ancestor that should be project root (.claude/skills/ishosting-manager/scripts → 4 levels up)
    candidate_root = script_dir.parent.parent.parent.parent
    if candidate_root not in search_paths and candidate_root.exists():
        search_paths.append(candidate_root)
    # User config directory (always checked last)
    search_paths.append(Path.home() / ".config" / "ishosting")

    for path in search_paths:
        env_file = path / ".env"
        if env_file.exists() and env_file.is_file():
            try:
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            # Only set if not already in environment
                            if key not in os.environ:
                                os.environ[key] = value
                return  # Stop after first .env file found
            except PermissionError:
                print(f"[WARN] Cannot read {env_file}: permission denied", file=sys.stderr)
                continue
            except Exception as exc:
                print(f"[WARN] Failed to load {env_file}: {exc}", file=sys.stderr)
                continue

COMMANDS: Final[dict[str, dict[str, str]]] = {
    # PROFILE
    "profile-view": {"desc": "Get profile info", "opts": ""},

    # SETTINGS
    "profile-settings-view": {"desc": "Get profile settings", "opts": ""},
    "profile-settings-edit": {"desc": "Edit profile settings", "opts": "--firstname STR --lastname STR --phone STR --email STR --city STR --state STR --country STR --zip STR --line_1 STR --line_2 STR"},
    "ssh-key-view": {"desc": "Get SSH keys", "opts": ""},
    "ssh-key-create": {"desc": "Add new SSH key", "opts": "--title NAME --public TEXT"},
    "ssh-key-delete": {"desc": "Delete SSH key", "opts": "--id NUM"},

    # SERVICES
    "services-stats": {"desc": "Get services statistics", "opts": ""},
    "services-list": {"desc": "List all services", "opts": ""},

    # VPS
    "vps-list": {"desc": "List VPS instances", "opts": ""},
    "vps-view": {"desc": "View VPS details", "opts": "--id NUM"},
    "vps-edit": {"desc": "Edit VPS", "opts": "--id NUM --name STR --auto_renew BOOL"},
    "vps-status": {"desc": "Get VPS status", "opts": "--id NUM"},
    "vps-status-change": {"desc": "Change VPS status (actions: start|stop|reboot|force|cancel)", "opts": "--id NUM --action STR"},
    "vps-plans": {"desc": "List VPS plans", "opts": "--locations STR"},
    "vps-plan-view": {"desc": "View VPS plan", "opts": "--code STR"},
    "vps-configs": {"desc": "Get VPS configs", "opts": "--code STR"},
    "vps-ssh": {"desc": "Set VPS SSH access", "opts": "--id NUM"},
    "vps-rdns-edit": {"desc": "Edit VPS rDNS record", "opts": "--id NUM --protocol STR --ip STR --rdns STR"},

    # STORAGE
    "storage-list": {"desc": "List storage instances", "opts": ""},
    "storage-view": {"desc": "View storage details", "opts": "--id NUM"},
    "storage-edit": {"desc": "Edit storage", "opts": "--id NUM --name STR --auto_renew BOOL"},
    "storage-status": {"desc": "Get storage status", "opts": "--id NUM"},
    "storage-status-change": {"desc": "Change storage status (actions: cancel)", "opts": "--id NUM --action STR"},
    "storage-plans": {"desc": "List storage plans", "opts": "--locations STR"},
    "storage-plan-view": {"desc": "View storage plan", "opts": "--code STR"},
    "storage-configs": {"desc": "Get storage configs", "opts": "--code STR"},
    "storage-ssh": {"desc": "Set storage SSH access", "opts": "--id NUM"},

    # DEDICATED
    "dedicated-list": {"desc": "List dedicated servers", "opts": ""},
    "dedicated-view": {"desc": "View dedicated server", "opts": "--id NUM"},
    "dedicated-edit": {"desc": "Edit dedicated server", "opts": "--id NUM --name STR --auto_renew BOOL"},
    "dedicated-status": {"desc": "Get dedicated status", "opts": "--id NUM"},
    "dedicated-status-change": {"desc": "Change dedicated status (actions: start|stop|reboot|force|cancel)", "opts": "--id NUM --action STR"},
    "dedicated-plans": {"desc": "List dedicated plans", "opts": "--locations STR --gpu STR --ddos STR"},
    "dedicated-plan-view": {"desc": "View dedicated plan", "opts": "--code STR"},
    "dedicated-configs": {"desc": "Get dedicated configs", "opts": "--code STR"},
    "dedicated-ssh": {"desc": "Set dedicated SSH access", "opts": "--id NUM"},
    "dedicated-rdns-edit": {"desc": "Edit dedicated rDNS record", "opts": "--id NUM --protocol STR --ip STR --rdns STR"},

    # LOCATIONS (composite commands — fetch plans then configs to get locations)
    "vps-locations": {"desc": "List available VPS locations", "opts": "--code STR"},
    "vpn-locations": {"desc": "List available VPN locations", "opts": "--code STR"},
    "storage-locations": {"desc": "List available storage locations", "opts": "--code STR"},
    "dedicated-locations": {"desc": "List available dedicated locations", "opts": "--code STR"},

    # VPN
    "vpn-list": {"desc": "List VPN instances", "opts": ""},
    "vpn-view": {"desc": "View VPN details", "opts": "--id NUM"},
    "vpn-edit": {"desc": "Edit VPN", "opts": "--id NUM --name STR --auto_renew BOOL"},
    "vpn-status": {"desc": "Get VPN status", "opts": "--id NUM"},
    "vpn-status-change": {"desc": "Change VPN status (actions: start|stop|reboot|force|cancel)", "opts": "--id NUM --action STR"},
    "vpn-plans": {"desc": "List VPN plans", "opts": "--locations STR"},
    "vpn-plan-view": {"desc": "View VPN plan", "opts": "--code STR"},
    "vpn-configs": {"desc": "Get VPN configs", "opts": "--code STR"},
    "vpn-rdns-edit": {"desc": "Edit VPN rDNS record", "opts": "--id NUM --protocol STR --ip STR --rdns STR"},

    # BILLING
    "billing-order-validate": {"desc": "Validate order", "opts": "--plan STR --location STR --payment STR --type STR --os STR --promo STR --ssh-keys STR --additions JSON"},
    "billing-order-create": {"desc": "Create order", "opts": "--plan STR --location STR --payment STR --type STR --os STR --promo STR --ssh-keys STR --additions JSON"},
    "billing-configs": {"desc": "Get billing configs", "opts": ""},
    "billing-promo": {"desc": "Check promo code", "opts": "--code STR"},
    "billing-invoices": {"desc": "List invoices", "opts": ""},
    "billing-invoice-view": {"desc": "View invoice", "opts": "--id NUM"},
    "billing-invoice-status": {"desc": "Get invoice status", "opts": "--id NUM"},
    "billing-invoice-pay": {"desc": "Pay invoice (balance only: --balance; method only: --method STR; partly: --balance --method STR)", "opts": "--id NUM --balance BOOL --method STR --renew BOOL --redirect STR"},
    "billing-invoice-cancel": {"desc": "Cancel invoice", "opts": "--id NUM"},
    "billing-balance-add": {"desc": "Add funds", "opts": "--amount NUM --method STR --redirect STR"},
    "billing-balance-invoices": {"desc": "List balance invoices", "opts": ""},
    "billing-balance-invoices-view": {"desc": "View balance invoice", "opts": "--id NUM"},
}

REQUIRED: Final[dict[str, tuple[str, ...]]] = {
    # PROFILE
    "profile-view": (),

    # SETTINGS
    "profile-settings-view": (),
    "profile-settings-edit": (),
    "ssh-key-view": (),
    "ssh-key-create": ("title", "public",),
    "ssh-key-delete": ("id",),

    # SERVICES
    "services-stats": (),
    "services-list": (),

    # VPS
    "vps-list": (),
    "vps-view": ("id",),
    "vps-edit": ("id",),
    "vps-status": ("id",),
    "vps-status-change": ("id", "action",),
    "vps-plans": (),
    "vps-plan-view": ("code",),
    "vps-configs": ("code",),
    "vps-ssh": ("id",),
    "vps-rdns-edit": ("id", "protocol", "ip",),

    # STORAGE
    "storage-list": (),
    "storage-view": ("id",),
    "storage-edit": ("id",),
    "storage-status": ("id",),
    "storage-status-change": ("id", "action",),
    "storage-plans": (),
    "storage-plan-view": ("code",),
    "storage-configs": ("code",),
    "storage-ssh": ("id",),

    # DEDICATED
    "dedicated-list": (),
    "dedicated-view": ("id",),
    "dedicated-edit": ("id",),
    "dedicated-status": ("id",),
    "dedicated-status-change": ("id", "action",),
    "dedicated-plans": (),
    "dedicated-plan-view": ("code",),
    "dedicated-configs": ("code",),
    "dedicated-ssh": ("id",),
    "dedicated-rdns-edit": ("id", "protocol", "ip",),

    # LOCATIONS
    "vps-locations": (),
    "vpn-locations": (),
    "storage-locations": (),
    "dedicated-locations": (),

    # VPN
    "vpn-list": (),
    "vpn-view": ("id",),
    "vpn-edit": ("id",),
    "vpn-status": ("id",),
    "vpn-status-change": ("id", "action",),
    "vpn-plans": (),
    "vpn-plan-view": ("code",),
    "vpn-configs": ("code",),
    "vpn-rdns-edit": ("id", "protocol", "ip",),

    # BILLING
    "billing-order-validate": ("plan", "location", "payment",),
    "billing-order-create": ("plan", "location", "payment",),
    "billing-configs": (),
    "billing-promo": ("code",),
    "billing-invoices": (),
    "billing-invoice-view": ("id",),
    "billing-invoice-status": ("id",),
    "billing-invoice-pay": ("id",),
    "billing-invoice-cancel": ("id",),
    "billing-balance-add": ("amount",),
    "billing-balance-invoices": (),
    "billing-balance-invoices-view": ("id",),
}

def _request(method: str, path: str, body: dict[str, Any] | None = None, retry: int = 3) -> dict[str, Any]:
    token = os.environ.get(B.token_env, "")
    language = os.environ.get(B.language, "en")
    base_url = os.environ.get(B.base_url, "")

    # Validate HTTPS to prevent token leakage over plaintext
    if base_url and not base_url.startswith("https://"):
        return {"error": "InsecureURL", "message": "ISHOSTING_BASE_URL must use https:// to protect API credentials"}

    url = f"{base_url}{path}"
    headers = {
        "X-Api-Token": token,
        "Content-Type": "application/json",
        "User-Agent": B.user_agent,
        "Accept": "application/json",
        "Accept-Language": language,
    }
    base_auth = os.environ.get(B.base_auth, "")
    if base_auth:
        headers["Authorization"] = f"Basic {base64.b64encode(base_auth.encode()).decode()}"

    data = json.dumps(body).encode(B.encoding) if body is not None else None

    # Explicit SSL context with system CA certificates
    ssl_ctx = ssl.create_default_context()

    for attempt in range(retry):
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=B.timeout, context=ssl_ctx) as resp:
                if 200 <= resp.status < 300:
                    try:
                        response_body = resp.read().decode(B.encoding)
                        return json.loads(response_body) if response_body else {}
                    except IncompleteRead as e:
                        partial = e.partial.decode(B.encoding, errors='ignore')
                        try:
                            return json.loads(partial)
                        except json.JSONDecodeError:
                            if attempt < retry - 1:
                                time.sleep(min(2 ** attempt, 8))
                                continue
                            return {"error": "IncompleteRead", "message": f"Failed to read complete response after {retry} attempts"}
                return {}
        except HTTPError as e:
            # Sanitize: extract only safe fields, never expose raw server response body
            error_body = ""
            try:
                error_body = e.read().decode(B.encoding)
            except (OSError, UnicodeDecodeError):
                pass
            # Try to extract a clean error message from JSON response
            error_msg = e.reason
            try:
                parsed = json.loads(error_body)
                if isinstance(parsed, dict) and "message" in parsed:
                    error_msg = parsed["message"]
                elif isinstance(parsed, dict) and "error" in parsed:
                    error_msg = parsed["error"]
            except (json.JSONDecodeError, KeyError):
                pass
            return {"error": error_msg, "code": e.code}
        except IncompleteRead:
            if attempt < retry - 1:
                time.sleep(min(2 ** attempt, 8))
                continue
            return {"error": "IncompleteRead", "message": f"Connection interrupted after {retry} attempts"}
        except ssl.SSLError as e:
            return {"error": "SSLError", "message": f"TLS/SSL error: {e.reason}"}

    return {"error": "RequestFailed", "message": "All retry attempts exhausted"}


def _error(message: str, cmd: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "error",
        "error_type": "usage_error",
        "message": message,
    }

    if cmd and cmd in COMMANDS:
        payload["command"] = cmd
        payload["required"] = REQUIRED.get(cmd, ())
        payload["options"] = COMMANDS[cmd]["opts"]
    else:
        payload["available_commands"] = {
            name: {
                "description": meta["desc"],
                "required": REQUIRED.get(name, ()),
            }
            for name, meta in COMMANDS.items()
        }

    return payload


def _validate_args(cmd: str, args: Args) -> list[str]:
    return [f"--{k.replace('_', '-')}" for k in REQUIRED.get(cmd, ()) if args.get(k) is None]


# Valid protocol values for rDNS and network commands
_VALID_PROTOCOLS: Final[frozenset[str]] = frozenset({"ipv4", "ipv6"})


def _sanitize_args(cmd: str, args: Args) -> str | None:
    """Validate and sanitize argument values. Returns error message or None if OK."""
    # Validate --id is a positive integer (prevents path traversal like ../../admin)
    if "id" in args:
        id_val = str(args["id"])
        if not id_val.isdigit() or int(id_val) <= 0:
            return f"Invalid --id '{args['id']}': must be a positive integer"
        args["id"] = id_val  # Normalize to clean string

    # Validate --amount is a positive number
    if "amount" in args:
        try:
            amount = float(args["amount"])
            if amount <= 0:
                return f"Invalid --amount '{args['amount']}': must be a positive number"
        except (ValueError, TypeError):
            return f"Invalid --amount '{args['amount']}': must be a number"

    # Validate --protocol is in whitelist
    if "protocol" in args:
        proto = str(args["protocol"]).lower()
        if proto not in _VALID_PROTOCOLS:
            return f"Invalid --protocol '{args['protocol']}': must be one of {', '.join(sorted(_VALID_PROTOCOLS))}"
        args["protocol"] = proto  # Normalize to lowercase

    # Validate --code contains only safe characters (alphanumeric, hyphens, underscores, dots)
    if "code" in args:
        code_val = str(args["code"])
        if not all(c.isalnum() or c in "-_." for c in code_val):
            return f"Invalid --code '{args['code']}': contains unsafe characters"

    return None


def _list_fmt(key: str) -> OutputFormatter:
    return lambda r, _: {key: r if isinstance(r, list) else r.get("data", r.get(key, r))}


def _item_fmt(key: str) -> OutputFormatter:
    return lambda r, a: {"id": a.get("id"), key: r} if isinstance(a, dict) else {"id": None, key: r}


def _action_fmt(action: str) -> OutputFormatter:
    return lambda r, a: {"id": a.get("id"), action: "error" not in r}


def _status_fmt() -> OutputFormatter:
    """Status formatter that strips the internal payment field."""
    def fmt(r: dict[str, Any], a: Args) -> dict[str, Any]:
        status = {k: v for k, v in r.items() if k != "payment"}
        return {"id": a.get("id"), "status": status}
    return fmt


def _payment_fmt() -> OutputFormatter:
    """Special formatter for payment responses that includes payment links."""
    def fmt(r: dict[str, Any], a: Args) -> dict[str, Any]:
        result = {"id": a.get("id"), "paid": True if "redirect" not in r else False}
        # Include payment link if available
        if "redirect" in r:
            result["payment_link"] = r["redirect"]
        # Include any other relevant payment info
        if "method" in r:
            result["method"] = r["method"]
        if "amount" in r:
            result["amount"] = r["amount"]
        return result
    return fmt


def _body(a: Args) -> dict[str, Any] | None:
    body = {k: v for k, v in a.items() if k not in _EXCLUDE_KEYS and k not in ("limit", "page")}
    return body or None


def _edit_body(a: Args) -> dict[str, Any]:
    """Build a PATCH body for service edit — auto_renew goes inside plan: {}."""
    body: dict[str, Any] = {"tags": []}
    if "name" in a:
        body["name"] = a["name"]
    if "auto_renew" in a:
        val = a["auto_renew"]
        if isinstance(val, str):
            val = val.lower() not in ("false", "0", "no")
        body["plan"] = {"auto_renew": val}
    return body


def _profile_settings_body(a: Args) -> dict[str, Any] | None:
    """Build profile settings body with proper nesting."""
    personal_fields = {"firstname", "lastname", "phone", "email"}
    address_fields = {"line_1", "line_2", "city", "state", "country", "zip"}
    body: dict[str, Any] = {}

    personal = {k: v for k, v in a.items() if k in personal_fields}
    address = {k: v for k, v in a.items() if k in address_fields}

    if personal or address:
        body["personal"] = {}
        if personal:
            body["personal"].update(personal)
        if address:
            body["personal"]["address"] = address

    return body or None


def _qs(a: Args) -> str:
    from urllib.parse import urlencode
    params = {
        "limit": a.get("limit", B.limit),
        "page": a.get("page", B.page),
    }

    # Add optional filters
    if locations := a.get("locations"):
        params["locations"] = locations
    if gpu := a.get("gpu"):
        params["gpu"] = gpu
    if ddos := a.get("ddos"):
        params["ddos"] = ddos

    return "?" + urlencode(params, doseq=True)


def _order_body(a: Args) -> dict[str, Any]:
    import uuid
    additions: list[dict[str, str]] = []

    # Location as an addition with category "country"
    if a.get("location"):
        additions.append({"code": a["location"], "category": "country"})

    # OS as an addition
    if a.get("os"):
        additions.append({"code": a["os"], "category": "os"})

    # Parse additional additions from JSON if provided
    # Format: [{"code": "GPU_NVIDIA_310", "category": "PLATFORM_GPU"}, ...]
    if a.get("additions"):
        try:
            custom_additions = json.loads(a["additions"])
            if isinstance(custom_additions, list):
                additions.extend(custom_additions)
            elif isinstance(custom_additions, dict):
                additions.append(custom_additions)
        except json.JSONDecodeError as exc:
            print(f"[WARN] Invalid JSON in --additions (ignored): {exc}", file=sys.stderr)

    item: dict[str, Any] = {
        "action": "new",
        "identity": uuid.uuid4().hex[:16],
        "type": a.get("type", "vps"),
        "plan": a["plan"],
        "quantity": int(a.get("quantity", 1)),
        "additions": additions,
    }

    # Add SSH keys if provided
    if a.get("ssh_keys"):
        ssh_keys_str = a["ssh_keys"]
        # Support comma-separated list of key IDs
        key_ids = []
        for k in ssh_keys_str.split(","):
            k = k.strip()
            if k.isdigit():
                key_ids.append(int(k))
            elif k:
                print(f"[WARN] Invalid SSH key ID ignored: '{k}' (must be a positive integer)", file=sys.stderr)
        if key_ids:
            item["options"] = {
                "ssh": {
                    "is_enabled": True,
                    "keys": key_ids
                }
            }

    body: dict[str, Any] = {"items": [item]}
    if a.get("promo"):
        body["promos"] = [a["promo"]]
    return body


def _svc_handlers(svc: str) -> dict[str, Handler]:
    h: dict[str, Handler] = {
        f"{svc}-list": (
            lambda a: ("GET", f"/{svc}/list{_qs(a)}", None),
            _list_fmt(svc),
        ),
        f"{svc}-view": (
            lambda a: ("GET", f"/{svc}/{a['id']}", None),
            _item_fmt(svc),
        ),
        f"{svc}-edit": (
            lambda a: ("PATCH", f"/{svc}/{a['id']}", _edit_body(a)),
            _action_fmt("updated"),
        ),
        f"{svc}-status": (
            lambda a: ("GET", f"/{svc}/{a['id']}/status", None),
            _status_fmt(),
        ),
        f"{svc}-status-change": (
            lambda a: ("PATCH", f"/{svc}/{a['id']}/status/{a['action']}", None),
            _action_fmt("changed"),
        ),
        f"{svc}-plans": (
            lambda a: ("GET", f"/{svc}/plans{_qs(a)}", None),
            _list_fmt("plans"),
        ),
        f"{svc}-plan-view": (
            lambda a: ("GET", f"/{svc}/plan/{a['code']}", None),
            _item_fmt("plan"),
        ),
        f"{svc}-configs": (
            lambda a: ("GET", f"/{svc}/configs/{a['code']}", None),
            _item_fmt("configs"),
        ),
        f"{svc}-ssh": (
            lambda a: ("PATCH", f"/{svc}/{a['id']}/access/ssh", _body(a)),
            _action_fmt("updated"),
        ),
    }
    return h


handlers: dict[str, Handler] = {
    # PROFILE
    "profile-view": (
        lambda _: ("GET", "/profile", None),
        _list_fmt("profile"),
    ),

    # SETTINGS
    "profile-settings-view": (
        lambda _: ("GET", "/settings/profile", None),
        _list_fmt("profile"),
    ),
    "profile-settings-edit": (
        lambda a: ("PATCH", "/settings/profile", _profile_settings_body(a)),
        lambda r, a: {"updated": "error" not in r, "data": r},
    ),
    "ssh-key-view": (
        lambda _: ("GET", "/settings/ssh", None),
        _list_fmt("keys"),
    ),
    "ssh-key-create": (
        lambda a: ("POST", "/settings/ssh", {"title": a["title"], "public": a["public"]}),
        _action_fmt("created"),
    ),
    "ssh-key-delete": (
        lambda a: ("DELETE", f"/settings/ssh/{a['id']}", None),
        _action_fmt("deleted"),
    ),

    # SERVICES
    "services-stats": (
        lambda _: ("GET", "/services/stats", None),
        _list_fmt("stats"),
    ),
    "services-list": (
        lambda a: ("GET", f"/services/list{_qs(a)}", None),
        _list_fmt("services"),
    ),

    # VPS
    **_svc_handlers("vps"),
    "vps-rdns-edit": (
        lambda a: ("PATCH", f"/vps/{a['id']}/network/{a['protocol']}/{quote(a['ip'], safe='')}", _body(a)),
        _action_fmt("updated"),
    ),

    # STORAGE
    **_svc_handlers("storage"),

    # DEDICATED
    **_svc_handlers("dedicated"),
    "dedicated-rdns-edit": (
        lambda a: ("PATCH", f"/dedicated/{a['id']}/network/{a['protocol']}/{quote(a['ip'], safe='')}", _body(a)),
        _action_fmt("updated"),
    ),

    # VPN
    **_svc_handlers("vpn"),
    "vpn-rdns-edit": (
        lambda a: ("PATCH", f"/vpn/{a['id']}/network/{a['protocol']}/{quote(a['ip'], safe='')}", _body(a)),
        _action_fmt("updated"),
    ),

    # BILLING
    "billing-order-validate": (
        lambda a: ("POST", "/billing/order/validate", _order_body(a)),
        _list_fmt("order"),
    ),
    "billing-order-create": (
        lambda a: ("POST", "/billing/order", _order_body(a)),
        _list_fmt("order"),
    ),
    "billing-configs": (
        lambda _: ("GET", "/billing/configs", None),
        _list_fmt("configs"),
    ),
    "billing-promo": (
        lambda a: ("GET", f"/billing/promo/{a['code']}", None),
        _item_fmt("promo"),
    ),
    "billing-invoices": (
        lambda a: ("GET", f"/billing/invoices{_qs(a)}", None),
        _list_fmt("invoices"),
    ),
    "billing-invoice-view": (
        lambda a: ("GET", f"/billing/invoice/{a['id']}", None),
        _item_fmt("invoice"),
    ),
    "billing-invoice-status": (
        lambda a: ("GET", f"/billing/invoice/{a['id']}/status", None),
        _item_fmt("invoice_status"),
    ),
    "billing-invoice-pay": (
        lambda a: ("POST", f"/billing/invoice/{a['id']}/pay", {
            **({"balance": True} if a.get("balance") else {}),
            **({"method": a["method"]} if a.get("method") else {}),
            **({"redirect": a["redirect"]} if a.get("redirect") else {}),
            "renew": str(a.get("renew", "true")).lower() != "false",
        } or {"balance": True}),
        _payment_fmt(),
    ),
    "billing-invoice-cancel": (
        lambda a: ("PATCH", f"/billing/invoice/{a['id']}/cancel", None),
        _action_fmt("cancelled"),
    ),
    "billing-balance-add": (
        lambda a: ("POST", "/billing/balance/add", {"amount": float(a["amount"]), **{k: v for k, v in a.items() if k not in _EXCLUDE_KEYS and k not in ("limit", "page", "amount")}}),
        _payment_fmt(),
    ),
    "billing-balance-invoices": (
        lambda a: ("GET", f"/billing/balance/invoices{_qs(a)}", None),
        _list_fmt("invoices"),
    ),
    "billing-balance-invoices-view": (
        lambda a: ("GET", f"/billing/balance/invoice/{a['id']}", None),
        _item_fmt("invoice"),
    ),
}

def _locations_result(svc: str, args: Args) -> dict[str, Any]:
    """Fetch available locations for a service by extracting them from plans or configs."""
    # VPN has different architecture: all plans share same location in plans,
    # but actual locations are available through configs
    if svc == "vpn":
        # Get first VPN plan to fetch configs
        plans_resp = _request("GET", f"/{svc}/plans")
        if "error" in plans_resp:
            return {"status": "error", "message": plans_resp.get("error", "Failed to fetch plans"), **plans_resp}

        plans = plans_resp if isinstance(plans_resp, list) else plans_resp.get("data", plans_resp.get("plans", []))
        if not plans:
            return {"status": "error", "message": f"No {svc} plans found"}

        # Get first plan code
        first = plans[0]
        plan_code = first.get("code") or (first.get("plan", {}).get("code") if isinstance(first.get("plan"), dict) else None)
        if not plan_code:
            return {"status": "error", "message": "Could not determine plan code from plans response"}

        # Fetch configs to get locations
        configs_resp = _request("GET", f"/{svc}/configs/{plan_code}")
        if "error" in configs_resp:
            return {"status": "error", "message": configs_resp.get("error", "Failed to fetch configs"), **configs_resp}

        # Extract locations from configs
        # Raw API response structure: configs might be at root level or wrapped
        locations = []
        if "locations" in configs_resp:
            locations = configs_resp.get("locations", [])
        elif "configs" in configs_resp:
            locations = configs_resp.get("configs", {}).get("locations", [])

        return {"status": "success", "service": svc, "locations": locations}

    # For VPS, Dedicated, Storage: extract locations from plans
    plans_resp = _request("GET", f"/{svc}/plans")
    if "error" in plans_resp:
        return {"status": "error", "message": plans_resp.get("error", "Failed to fetch plans"), **plans_resp}

    # Extract plans array from response
    plans = plans_resp if isinstance(plans_resp, list) else plans_resp.get("data", plans_resp.get("plans", []))
    if not plans:
        return {"status": "error", "message": f"No {svc} plans found"}

    # Extract unique locations from plans
    locations_map: dict[str, str] = {}
    for item in plans:
        location = item.get("location", {})
        code = location.get("code")
        name = location.get("name")
        if code and name:
            locations_map[code] = name

    # Convert to list format
    locations = [{"code": code, "name": name} for code, name in sorted(locations_map.items())]

    return {"status": "success", "service": svc, "locations": locations}


def main() -> int:
    """CLI entry point — zero-arg defaults with optional args."""
    # Load .env file if available
    _load_env_file()

    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if not args:
        print(json.dumps(_error("No command specified"), indent=2))
        return 1

    cmd = args[0]
    if cmd not in COMMANDS:
        print(json.dumps(_error(f"Unknown command: {cmd}"), indent=2))
        return 1

    # Parse optional flags
    opts: Args = {}
    i = 1
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            opts[key] = (
                args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else True
            )
            i += 1 if opts[key] is not True else 0
        i += 1

    # --lang flag overrides ISHOSTING_API_LANGUAGE env var
    if "lang" in opts:
        os.environ[B.language] = opts.pop("lang")

    if missing := _validate_args(cmd, opts):
        print(json.dumps(_error(f"Missing required: {', '.join(missing)}", cmd), indent=2))
        return 1

    # Sanitize and validate argument values (type checks, whitelist, path traversal prevention)
    if sanitize_err := _sanitize_args(cmd, opts):
        print(json.dumps(_error(sanitize_err, cmd), indent=2))
        return 1

    # Validate action parameter for status-change commands
    if cmd.endswith("-status-change") and "action" in opts:
        service_type = cmd.split("-")[0]  # Extract service type (vps, storage, dedicated, vpn)
        action = opts["action"]
        if service_type in VALID_ACTIONS and action not in VALID_ACTIONS[service_type]:
            valid_actions = ", ".join(sorted(VALID_ACTIONS[service_type]))
            print(json.dumps(_error(f"Invalid action '{action}'. Valid actions: {valid_actions}", cmd), indent=2))
            return 1

    # Check for required credentials
    missing_creds = []
    if not os.environ.get(B.token_env):
        missing_creds.append(f"{B.token_env}=<your-api-token>")
    if not os.environ.get(B.base_url):
        missing_creds.append(f"{B.base_url}=<api-base-url>")
    if missing_creds:
        error_msg = (
            "STOP: Missing required environment variables. "
            "DO NOT set these yourself — ASK THE USER to provide them.\n\n"
            "Missing:\n"
            + "\n".join(f"  {cred}" for cred in missing_creds)
            + "\n\nThe user must provide these values. Do not guess or assume defaults."
        )
        print(json.dumps(_error(error_msg, cmd), indent=2))
        return 1

    # Handle composite commands that require multiple API calls
    if cmd.endswith("-locations"):
        svc = cmd.removesuffix("-locations")
        result = _locations_result(svc, opts)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "success" else 1

    builder, formatter = handlers[cmd]
    method, path, body = builder(opts)
    response = _request(method, path, body)

    success = "error" not in response
    result = (
        {"status": "success", **formatter(response, opts)}
        if success
        else {"status": "error", "message": response.get("error", "API request failed"), **response}
    )
    print(json.dumps(result, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
