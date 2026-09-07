# Deploying to a cloud VM

The bot uses long-polling, not a webhook, so it needs no public URL, no
inbound ports, and no HTTPS certificate — just *some* machine that keeps
`python main.py` running and can reach the internet outbound.

I can't create the cloud account or provision the VM myself — that part is
on you. Everything from SSH onward, I've scripted, and it's identical no
matter which host you pick.

## 1. Pick a host and launch a VM

Two providers offer **genuinely perpetual free compute** (not a 12-month
trial that starts charging you later) — both are worth trying before
paying anything. A low-cost VPS is listed last as a fallback only, in case
both free options stay stuck.

Both free providers require a card on file for identity verification, but
neither charges you as long as you stay within the free-tier limits
described below.

**Option A — Oracle Cloud's Always Free tier.** Steps below.

**Option B — Google Cloud's Always Free `e2-micro`.** A single small VM
(2 vCPU burstable, 1GB RAM), free forever, but only in one of three
regions (`us-west1`, `us-central1`, `us-east1`) and only one instance at a
time — not capacity-gated the way OCI's ARM shape is, so it's a good
option if OCI keeps returning capacity errors:

1. Sign up at [console.cloud.google.com](https://console.cloud.google.com)
   and create a project (any name).
2. Search **"Compute Engine"** in the top search bar and open it — first
   visit takes a minute to enable the API.
3. **Compute Engine → VM instances → Create Instance.**
4. **Name:** anything.
5. **Region:** must be `us-west1`, `us-central1`, or `us-east1` — Always
   Free eligibility is locked to these three. Zone within the region
   doesn't matter.
6. **Machine type:** `e2-micro` (under the E2 series).
7. **Boot disk:** click Change, pick Ubuntu 22.04 or 24.04 LTS, keep the
   disk at or under 30GB (the default 10GB is fine) to stay in the free
   tier.
8. Leave firewall/networking at their defaults — the bot only makes
   outbound connections, so nothing needs opening.
9. Click **Create**, and note the instance's external IP once it's up.
10. To connect, click the **SSH** button next to the instance in the GCP
    console — it opens a browser-based terminal with no key setup needed.
    Once connected, run `whoami` to see your actual username (it won't be
    `ubuntu`) — you'll need it for step 3 below.

Skip to [step 2](#2-ssh-in-and-deploy) if you used Option B.

**Fallback — a low-cost VPS (~$4-6/month), only if both free options are
stuck.** No free-tier capacity roulette, a VM within a minute of signing
up. Any provider works identically from step 2 onward; DigitalOcean is a
reasonable default for the simplest signup flow:

1. Sign up at [digitalocean.com](https://www.digitalocean.com) (or
   [Hetzner](https://www.hetzner.com/cloud) for the cheapest option, or
   [Linode](https://www.linode.com) — all three work the same way here).
2. **Create → Droplets** (DigitalOcean's name for a VM).
3. **Image:** Ubuntu, latest LTS (24.04).
4. **Size/Plan:** the cheapest "Basic" / shared-CPU tier — 1GB RAM is
   plenty for this bot, which is mostly waiting on network I/O, not doing
   heavy compute.
5. **Datacenter region:** whichever is closest to you; it doesn't matter
   functionally.
6. **Authentication:** add your SSH public key (recommended) or set a
   root password.
7. Create it, and note the droplet's public IP address once it's up.

### Create an Oracle Cloud account

Sign up at [cloud.oracle.com](https://cloud.oracle.com). Identity
verification requires a card on file, but the Always Free resources used
here incur no charge as long as you stay within the free-tier shapes below.

### Launch an Always Free Compute instance

From the OCI console: **Compute → Instances → Create Instance**.

- **Image:** Ubuntu (22.04 or 24.04 LTS)
- **Shape:** two options are Always Free-eligible:
  - `VM.Standard.E2.1.Micro` (AMD, x86) — smaller (1/8 OCPU, 1GB RAM), but
    reliably available and plenty for this bot, which is mostly waiting on
    network I/O, not doing heavy compute. **Start with this one.** In the
    shape picker it's easy to miss: click **"Change shape"**, and under the
    **Virtual machine** tab look inside **"Specialty and previous
    generation"** — that section is collapsed by default, and this shape
    lives there since it's an older-generation x86 shape. It won't show up
    in the default expanded list next to A1.Flex/A4.Flex/E5.Flex.
  - `VM.Standard.A1.Flex` (ARM) — a much larger free allowance (up to 4
    OCPU / 24GB RAM total across instances), but its free capacity is
    extremely popular and frequently exhausted — expect
    `Out of capacity for shape VM.Standard.A1.Flex in availability domain
    ...` on many attempts. If `E2.1.Micro` truly isn't available on your
    tenancy either (a minority of newer accounts only get A1.Flex
    Always-Free eligibility) and you want A1.Flex anyway: try a different
    Availability Domain if your region's dropdown offers more than one
    (many regions only have one, in which case this won't help), or just
    retry later — capacity fluctuates as other free-tier users release
    instances. If neither pans out, Option B (Google Cloud) above is free
    and isn't capacity-gated the same way.
- **Networking:** every Compute instance must attach to a subnet inside a
  Virtual Cloud Network (VCN) — on a brand-new account you likely don't
  have one yet, so:
  - Look for a **"Create new virtual cloud network"** option in this
    section (sometimes a radio button next to "Select existing virtual
    cloud network"). If present, pick it and accept the defaults — OCI
    auto-creates a VCN with a public subnet, an internet gateway, and a
    security list that already allows inbound SSH. Nothing further to do
    here.
  - If no auto-create option is offered, create one first: open
    **Networking → Virtual Cloud Networks → Start VCN Wizard**, choose the
    **"VCN with Internet Connectivity"** template (not "VCN Only" — that
    template skips the internet gateway you need to reach the instance at
    all), give it any name, and click Create. Then go back to instance
    creation and select that VCN's **public** subnet (named something like
    `Public Subnet-<vcn-name>`).
  - Either way, make sure **"Assign a public IPv4 address"** is checked —
    without it you have no address to SSH to.
  - No other networking changes are needed — the bot only makes outbound
    connections (long-polling Telegram), so port 22 (SSH, already open by
    default) is the only inbound rule that ever matters here.
- Add your SSH public key when prompted (or let OCI generate a keypair for
  you and download the private key)

Once running, note the instance's public IP address.

## 2. SSH in and deploy

Use the username your provider set up: `ubuntu` on an OCI or DigitalOcean
Ubuntu image, `root` on a fresh Hetzner/Linode Ubuntu image, or whatever
`whoami` printed in the GCP browser SSH terminal — unless you created a
different user during setup.

```bash
ssh ubuntu@<your-instance-ip>
git clone https://github.com/nabilhrs/social-summary-bot.git
cd social-summary-bot
bash deploy/setup.sh
```

The script installs Python/git/build tools, creates the venv, installs
`requirements.txt`, and copies `.env.example` to `.env`. Then:

```bash
nano .env
```

Fill in `TELEGRAM_BOT_TOKEN`, `AUTHORIZED_USER_IDS`, and `GEMINI_API_KEY`
(same values as your local `.env` — see the main [README](README.md#setup)
for what each one means).

## 3. Run it as a persistent service

The service file assumes user `ubuntu` and `/home/ubuntu/social-summary-bot`.
If you SSH'd in as something else — `root` on Hetzner/Linode, or your GCP
username — edit `deploy/social-summary-bot.service` first and change
`User=ubuntu` and the `/home/ubuntu/...` paths to match whatever user and
home directory you actually used (`pwd` and `whoami` will tell you).

```bash
sudo cp deploy/social-summary-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now social-summary-bot
```

`enable` makes it start automatically on every boot; `--now` starts it
immediately. `Restart=always` in the unit file means systemd relaunches it
if it ever crashes.

Check it's actually running:

```bash
journalctl -u social-summary-bot -f
```

You should see the same `Bot starting — polling for updates...` line you'd
see running it locally. `Ctrl+C` to stop watching logs (this does not stop
the bot itself).

## Updating after future code changes

```bash
cd social-summary-bot
git pull
venv/bin/pip install -r requirements.txt   # only needed if requirements.txt changed
sudo systemctl restart social-summary-bot
```

## Data

`summarizer.db` lives on the VM's own disk at
`~/social-summary-bot/summarizer.db` and persists across reboots and
service restarts — it's a real VM disk, not ephemeral container storage.
There's no automated backup; if that matters to you, periodically copy the
file off the VM (`scp ubuntu@<ip>:~/social-summary-bot/summarizer.db .`).

## Useful commands

| Command | Does |
|---|---|
| `sudo systemctl status social-summary-bot` | Is it running right now? |
| `sudo systemctl restart social-summary-bot` | Restart (e.g. after editing `.env`) |
| `sudo systemctl stop social-summary-bot` | Stop it |
| `journalctl -u social-summary-bot -f` | Follow live logs |
| `journalctl -u social-summary-bot -n 100` | Last 100 log lines |
