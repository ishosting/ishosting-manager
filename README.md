# is\*hosting Manager — AI Agent Skill

Code skill that gives AI agents full control over is\*hosting infrastructure. Order servers, manage billing, configure services, and automate cloud operations through natural language.

---

## What It Does

The skill wraps the is\*hosting REST API into a clean Python CLI that AI agents (Claude Code, Cursor, OpenAI Codex) can call to manage your infrastructure end-to-end:

- **Order & provision** VPS, Dedicated, Storage, and VPN servers
- **Configure hardware** — CPU, RAM, disk, GPU, DDoS protection, RAID, extra IPs
- **Install software** — OS images, control panels, your own apps
- **Manage lifecycle** — start, stop, reboot, force-reboot, cancel services
- **Billing** — create orders, pay invoices (balance / crypto / card), top up balance, apply promo codes
- **SSH keys** — add, delete, attach to services
- **Profile & settings** — view balance, edit personal info, check active services

---

## Requirements

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) package runner
- An is\*hosting account with an API token

---

## Setup

### 1. Install or download skill

Follow the instructions in the marketplace of choice:

- https://skills.sh 
- https://skillsmp.com
- https://skillzwave.ai
- https://awesomeskill.ai
- https://www.skillhub.club
- https://skill0.io
- https://agentskills.to
- https://deepskills.ai
- https://smithery.ai

### 2. Configure credentials

To make things smoother you can optionally create .env file.

```env
ISHOSTING_TOKEN=your_api_token_here
ISHOSTING_BASE_URL=base_url_from_documentation_here
```

### 3. Open in your AI tool

**Claude Code (CLI):**
```bash
cd your-project
claude .
```

**Cursor / OpenAI Codex:** Open the project directory via File → Open.

You can now start using the skill’s abilities with natural language.

---

## Capabilities

### Services

| Service    | List | View | Edit | Status | Start/Stop/Reboot | Cancel | Plans | Configs | SSH |
|------------|------|------|------|--------|-------------------|--------|-------|---------|-----|
| VPS        | ✓    | ✓    | ✓    | ✓      | ✓                 | ✓      | ✓     | ✓       | ✓   |
| Dedicated  | ✓    | ✓    | ✓    | ✓      | ✓                 | ✓      | ✓     | ✓       | ✓   |
| Storage    | ✓    | ✓    | ✓    | ✓      | —                 | ✓      | ✓     | ✓       | ✓   |
| VPN        | ✓    | ✓    | ✓    | ✓      | ✓                 | ✓      | ✓     | ✓       | —   |

### Billing

- List and view invoices
- Pay invoices: from balance, via payment gateway, or a mix of both
- Cancel unpaid invoices
- Top up account balance
- Apply promo codes
- View balance transaction history

### Profile & Settings

- View account info, balance, active service counts
- Edit personal details and address
- Manage SSH keys (add, delete, attach to services)

---

## License

MIT License

Copyright (c) [2026] [is*hosting]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
