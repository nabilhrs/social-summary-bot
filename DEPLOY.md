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
- **Shape:** one of the Always Free-eligible shapes — either the ARM-based
  `VM.Standard.A1.Flex` (more generous allowance: up to 4 OCPU / 24GB RAM
  free) or the AMD `VM.Standard.E2.1.Micro` (smaller, but simpler and more
  reliably available — the ARM shape's free capacity is sometimes hard to
  provision in busy regions; if you hit a capacity error, either retry, try
  another region, or fall back to the AMD shape)
- **Networking:** the default VCN's security list only needs to allow
  inbound SSH (port 22, already the default) — nothing else, since the bot
  never receives inbound connections
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
