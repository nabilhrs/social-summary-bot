# Deploying to a free-tier cloud VM

The bot uses long-polling, not a webhook, so it needs no public URL, no
inbound ports, and no HTTPS certificate — just *some* machine that keeps
`python main.py` running and can reach the internet outbound. This guide
uses **Oracle Cloud Infrastructure's Always Free tier**, which (unlike AWS/
GCP's free tiers) gives genuinely perpetual free compute, not just a
12-month trial. A low-cost VPS (DigitalOcean/Linode/Hetzner, ~$4-6/month)
works identically from step 3 onward if you'd rather skip OCI's signup.

I can't create the cloud account or provision the VM myself — that part is
on you. Everything from SSH onward, I've scripted.

## 1. Create an Oracle Cloud account

Sign up at [cloud.oracle.com](https://cloud.oracle.com). Identity
verification requires a card on file, but the Always Free resources used
here incur no charge as long as you stay within the free-tier shapes below.

## 2. Launch an Always Free Compute instance

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
    instances. If neither pans out, a cheap VPS (see the intro above) sidesteps
    the capacity issue entirely.
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

## 3. SSH in and deploy

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

## 4. Run it as a persistent service

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
