# Analytiq — Demo deploy on the VPS

Runs the Analytiq **demo** behind nginx. The LLM runs on **Ollama Cloud**, so this box
only runs the lightweight app (~200–300 MB resident — fine on the 1 GB VPS + swap).
Landing page + workspace (ask questions, charts, upload docs), single-tenant, no login.

> Recommended URL: a **subdomain** `analytiq.nomoad.net` (cleanest — the app serves its
> own `/static/...` so a subdomain needs no path rewriting). Subpath notes at the end.

---

## 1. Get the app onto the box
Upload `analytiq-deploy.tar.gz`, then:
```bash
sudo mkdir -p /opt/analytiq && sudo chown "$USER" /opt/analytiq
tar -xzf analytiq-deploy.tar.gz -C /opt/analytiq --strip-components=1
cd /opt/analytiq
```

## 2. Virtualenv + lean deps (NO PyTorch)
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip   # this box was missing both
python3 -m venv .venv && . .venv/bin/activate
pip install -U pip
pip install -r requirements-demo.txt    # lean set: no torch, no sentence-transformers
```
`requirements-demo.txt` is deliberately light (the LLM is Ollama Cloud over HTTPS;
embeddings run in offline `test` mode). The full `requirements.txt` pulls torch — don't
use it on this shared box.

## 3. Configure
```bash
cp .env.demo .env
nano .env                      # paste OLLAMA_API_KEY
# confirm your model id is available + tool-capable on your tier:
curl -s https://ollama.com/v1/models -H "Authorization: Bearer $OLLAMA_API_KEY" | grep '"id"'
# set OLLAMA_CLOUD_MODEL in .env to one of those (e.g. gpt-oss:120b or qwen3-coder:480b)
```

## 4. Seed the demo database
```bash
python -m scripts.seed_demo    # writes ./demo.db (sales/returns/products/… matching the sample questions)
```

## 5. Run it as a service
Create `/etc/systemd/system/analytiq.service` (set `User=` to your VPS user):
```ini
[Unit]
Description=Analytiq demo
After=network.target

[Service]
WorkingDirectory=/opt/analytiq
EnvironmentFile=/opt/analytiq/.env
ExecStart=/opt/analytiq/.venv/bin/uvicorn api.app:app --host 127.0.0.1 --port 8008
Restart=always
User=YOUR_VPS_USER

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now analytiq
curl -s localhost:8008/health          # -> JSON: deploy_mode, data_source:"database", ...
curl -s localhost:8008/models | grep ollama-cloud
```

## 6. nginx (subdomain — recommended)
DNS: add an **A record** `analytiq.nomoad.net -> <this VPS public IP>` (same IP nomoad.net uses).
Create `/etc/nginx/sites-available/analytiq`:
```nginx
server {
    listen 80;
    server_name analytiq.nomoad.net;
    client_max_body_size 25m;                 # for the upload-docs button
    location / {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;              # cloud model can take a few seconds
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/analytiq /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d analytiq.nomoad.net   # TLS (same as nomoad.net already has)
```
Open **https://analytiq.nomoad.net** → landing page → "Open the app" → workspace.

## 7. (Optional) link the demo from the nomoad.net homepage
Add to `/var/www/html/index.html`:
```html
<a href="https://analytiq.nomoad.net">Try the Analytiq demo →</a>
```

---

## Smoke test (after deploy)
- `curl -s localhost:8008/health` → `data_source":"database"`
- In the UI, ask **"Show total revenue per month for 2024"** → a line chart + the
  "How this was answered" panel (tables used + SQL).
- Ask **"What was net revenue in Q4?"** → uses sales + returns.
- If the model errors: re-check `OLLAMA_API_KEY` and that `OLLAMA_CLOUD_MODEL` is a real,
  tool-capable id from step 3 (a non-tool model will fail the agent loop).

## Alternative: subpath `nomoad.net/analytiq` (more work)
The app uses absolute `/static/...` and `fetch("/ask")`, so a bare subpath breaks them.
To do it: run uvicorn with `--root-path /analytiq`, switch the two UI files' `/static`
and `fetch("/...")` to relative paths, and add `location /analytiq/ { proxy_pass ...; }`.
Ask me and I'll ship a subpath-ready build — but the subdomain above avoids all of it.
