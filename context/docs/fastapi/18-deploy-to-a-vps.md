# Python FastAPI Tutorial (Part 18): Deploy to a VPS - Security, Nginx, SSL, and Custom Domain

## 1. Overview

- **What this lesson teaches**: This lesson teaches how to deploy a production-ready FastAPI application to a Virtual Private Server (VPS). It covers setting up a production environment from scratch, including database health check endpoints, Linux server administration, SSH key authentication, server security hardening, UFW firewall configuration, Fail2ban intrusion protection, automated security updates, Nginx reverse proxying, Let's Encrypt SSL/TLS certificates, custom domain DNS mapping, PostgreSQL database configuration, Systemd service management, and production maintenance workflows.
- **Learning objectives**:
  - Add a database connectivity health check endpoint (`GET /health`) returning standard HTTP 503 status codes on failure.
  - Provision and configure an Ubuntu 24.04 LTS server instance on a Virtual Private Server (VPS) provider.
  - Create a non-root administrative user with `sudo` privileges and disable direct root SSH logins.
  - Generate high-security ED25519 SSH key pairs and harden the SSH daemon configuration (`sshd_config`).
  - Configure system timezones (UTC), hostnames, and local host file mappings.
  - Set up an uncomplicated firewall (UFW) allowing only essential ports (`22`, `80`, `443`).
  - Deploy Fail2ban to automatically block brute-force connection attempts.
  - Configure `unattended-upgrades` to automatically install security patches.
  - Point a custom domain to the server IP address using DNS `A` records and verify propagation with `dig`.
  - Install and configure Nginx as a reverse proxy with static file handling and `www` redirection.
  - Obtain and automate renewal for free Let's Encrypt SSL/TLS certificates using Certbot.
  - Install Python 3.12, UV package manager, and PostgreSQL on the server.
  - Configure PostgreSQL database roles, permissions, and run Alembic migrations.
  - Enforce restrictive Linux directory and file permissions (`600`/`700`/`755`) for application code and environment files.
  - Create a Systemd service unit (`fastapi-blog.service`) using Uvicorn with `--proxy-headers` and an asynchronous worker count formula (\\(1 \times \text{CPU cores}\\)).
  - Execute application updates and maintenance commands (`git pull`, `uv sync`, `alembic upgrade head`, `systemctl restart`).
- **Why the topic matters**: Deploying to a bare-metal or Virtual Private Server reveals the fundamental architecture underpinning modern web application hosting. Understanding Linux process management, reverse proxies, SSL termination, and security baselines makes debugging significantly easier across all hosting environments—including managed cloud services and containerized platforms like Docker or Google Cloud Run.

---

## 2. Concepts

### Virtual Private Server (VPS) vs. Managed Cloud Services

- **What it is**: A Virtual Private Server (VPS) is an isolated virtual machine running on physical hardware where the developer has root access and complete control over the operating system, file system, network configuration, and installed software.
- **Why it is needed**: It provides full operational control, fixed predictable monthly costs, and visibility into the underlying architecture of web server deployments.
- **How it works**: Providers like Linode (Akamai), DigitalOcean, or AWS EC2 slice physical servers into virtual instances. The developer interacts with the machine over SSH to install operating systems, system services, and application runtimes.
- **Important details**: VPS hosting requires manual server setup and maintenance (security hardening, updates, system service management).
- **Examples**: A 1 GB RAM shared CPU instance on Linode costing \$5/month.

### Production Database Health Checks

- **What it is**: A lightweight API endpoint (`GET /health`) designed for load balancers, proxies, and monitoring systems to check if the application and its critical dependencies are functional.
- **Why it is needed**: If an application server loses connection to its underlying database, it cannot serve functional web traffic. Health checks allow infrastructure monitoring to automatically stop sending traffic to unhealthy instances or fire alerts.
- **How it works**: The endpoint executes a trivial database query (`SELECT 1`). If successful, it returns HTTP 200 with `{"status": "healthy"}`. If the database connection throws an exception, it returns HTTP 503 Service Unavailable.
- **Important details**: HTTP 503 is the standard status code recognized by proxies and load balancers to signal that a service is temporarily down.
- **Examples**: `SELECT 1` using SQLAlchemy's `text("SELECT 1")`.

### SSH Key Authentication & Hardening

- **What it is**: A cryptographic authentication method using a public/private key pair (`ED25519`) instead of text passwords.
- **Why it is needed**: Text passwords can be brute-forced by automated bots scanning public IP addresses. SSH key pairs are mathematically unguessable and resist brute-force attacks.
- **How it works**: The public key (`.pub`) is stored on the server inside `~/.ssh/authorized_keys`, while the private key remains encrypted on the local developer machine.
- **Important details**: After deploying SSH keys, password authentication (`PasswordAuthentication no`) and direct root login (`PermitRootLogin no`) must be explicitly disabled in `/etc/ssh/sshd_config`.

### Uncomplicated Firewall (UFW)

- **What it is**: A user-friendly frontend CLI tool for managing `iptables` packet filtering rules on Linux servers.
- **Why it is needed**: Secures the server by blocking all unauthorized incoming network connections by default.
- **How it works**: Establishes default policies (`deny incoming`, `allow outgoing`) and explicitly opens only essential operational ports: SSH (22), HTTP (80), and HTTPS (443).
- **Important details**: SSH access (`sudo ufw allow ssh`) must be explicitly allowed _before_ enabling UFW (`sudo ufw enable`), otherwise the developer will be instantly locked out of the server.

### Fail2ban Intrusion Prevention

- **What it is**: An automated log-parsing daemon that monitors authentication logs for repeated failure patterns and dynamically adds firewall block rules for offensive IP addresses.
- **Why it is needed**: Protects SSH endpoints against automated dictionary and brute-force attacks.
- **How it works**: Parses `/var/log/auth.log`. If an IP fails authentication 3 times within 10 minutes (`maxretry = 3`, `findtime = 10m`), Fail2ban invokes UFW (`banaction = ufw`) to drop all packets from that IP for 1 hour (`bantime = 1h`).

### Unattended Security Upgrades (`unattended-upgrades`)

- **What it is**: An official Debian/Ubuntu utility that automatically checks for, downloads, and installs security-specific OS patches in the background.
- **Why it is needed**: Ensures that operating system vulnerabilities are patched immediately without requiring manual developer intervention.
- **How it works**: Runs as a daily background cron job, targeting security update repositories while avoiding non-security package upgrades that could alter application behavior.

### Nginx Reverse Proxy & Static File Handling

- **What it is**: An industry-standard, high-performance web server that acts as a intermediary gateway between public client browsers and backend application servers.
- **Why it is needed**: Python application servers (like Uvicorn) are designed to process dynamic Python application logic, whereas Nginx is heavily optimized for SSL/TLS termination, HTTP header forwarding, rate limiting, and directly serving static assets (CSS, JS, images) with minimal CPU memory overhead.
- **How it works**: Nginx listens on public ports 80 and 443. Requests matching `/static/` are read directly from disk by Nginx. All other API and web requests are proxied internally to Uvicorn running on `http://127.0.0.1:8000`.

### Domain DNS `A` Records

- **What it is**: A Domain Name System (DNS) mapping rule that converts human-readable domain names (`myawesomeapp.com`) into numerical IPv4 server addresses.
- **Why it is needed**: Allows users to access web applications using branded domain names instead of raw IP addresses.
- **How it works**: Configured at the domain registrar (e.g., Namecheap) by adding `A` records for `@` (root domain) and `www` pointing to the VPS public IP address. Verified using command-line DNS tools (`dig myawesomeapp.com +short`).

### Let's Encrypt & Certbot (Automated SSL/TLS)

- **What it is**: A free, automated Certificate Authority (Let's Encrypt) and a client tool (`Certbot`) used to issue and renew SSL/TLS encryption certificates.
- **Why it is needed**: Encrypts client-server communication over HTTPS, eliminates browser security warnings, and satisfies search engine indexing requirements.
- **How it works**: Certbot verifies domain ownership via an ACME challenge, modifies Nginx configuration files automatically to enable HTTPS on port 443, sets up HTTP-to-HTTPS redirects, and registers a `systemd` timer for automated background certificate renewals.

### Systemd Service Management

- **What it is**: The standard Linux init system and service manager used to bootstrap, monitor, and control background software processes.
- **Why it is needed**: Ensures that the FastAPI application starts automatically when the server boots up, sets working directories and environment variables, and automatically restarts the application if it crashes.
- **How it works**: Managed via a unit configuration file (`/etc/systemd/system/fastapi-blog.service`) controlled by `systemctl` commands.

### Asynchronous Worker Calculation Formula

- **What it is**: The rule for determining how many Uvicorn worker processes to run for a FastAPI app managed by Systemd.
- **Why it is needed**: Optimizes CPU usage and thread scheduling without wasting memory resources.
- **How it works**:
  - **Asynchronous Formula**: \\(1 \times \text{CPU cores}\\).
  - **Synchronous Legacy Formula**: \\((2 \times \text{CPU cores}) + 1\\).
- **Important details**: Because FastAPI handles I/O asynchronously on an event loop, running 1 worker per CPU core is optimal. For a single-core VPS instance, `--workers 1` is used.

---

## 3. Step-by-Step Tutorial

### Step 1: Adding Database Health Check Endpoint (`main.py`)

- **What he does**: Imports `text` from `sqlalchemy` and adds an explicit `/health` route handler to `main.py`.
- **Why he does it**: Provides a standardized health check endpoint for monitoring infrastructure to verify database connectivity.
- **Relevant code**:

  ```python
  from fastapi import FastAPI, HTTPException, status, Depends
  from sqlalchemy import text
  from sqlalchemy.ext.asyncio import AsyncSession
  from database import get_db

  app = FastAPI()

  @app.get("/health")
  async def health_check(db: AsyncSession = Depends(get_db)):
      try:
          await db.execute(text("SELECT 1"))
          return {"status": "healthy"}
      except Exception:
          raise HTTPException(
              status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
              detail="Database connection failed"
          )
  ```

- **How the code works**: Executes `SELECT 1`, an lightweight query that verifies database connectivity. If an exception occurs, it raises HTTP 503.
- **Result**: Accessing `/health` returns `{"status": "healthy"}`.

### Step 2: Pushing Application Code to GitHub

- **What he does**: Initializes git (if uninitialized), verifies `.env` is listed in `.gitignore`, creates a GitHub repository, adds the remote origin, commits the new health check, and pushes the main branch.
- **Why he does it**: Prepares a central repository to pull production code onto the server.
- **Relevant commands**:
  ```bash
  git add .
  git commit -m "Added health check endpoint"
  git remote add origin https://github.com/username/fastapi-blog.git
  git push -u origin main
  ```
- **Result**: Code is hosted on GitHub.

### Step 3: Provisioning VPS Instance & First Root Login

- **What he does**: Creates a Linode instance running Ubuntu 24.04 LTS (Shared CPU, 1 GB RAM plan at \$5/month) in the Dallas, TX region, sets a root password (`fastAPIblog1!`), and SSHs into the public IP as `root`.
- **Why he does it**: Provisions the cloud server instance.
- **Relevant commands**:
  ```bash
  ssh root@96.126.113.103
  ```
- **Result**: Accesses the server terminal as `root`.

### Step 4: System Package Update & Non-Root User Creation

- **What he does**: Updates package lists and upgrades installed system packages, creates non-root user `coreyms`, adds `coreyms` to the `sudo` group, and verifies group membership.
- **Why he does it**: Ensures system security patches are installed and limits the blast radius of operational mistakes by avoiding direct `root` usage.
- **Relevant commands**:

  ```bash
  # Update OS packages
  apt update && apt upgrade -y

  # Create non-root user with password
  adduser coreyms

  # Grant administrative sudo privileges
  usermod -aG sudo coreyms

  # Verify group assignment
  groups coreyms
  ```

- **Result**: User `coreyms` is created with `sudo` rights.

### Step 5: Generating ED25519 SSH Keys & Copying Public Key

- **What he does**: On the local machine, generates an ED25519 SSH key pair with a comment (`coreyms-imac-2026-04-14`), uploads the public key using `ssh-copy-id`, adds the private key to the local SSH agent, verifies passwordless SSH login, and sets strict file permissions (`700`/`600`) on `~/.ssh` on the server.
- **Why he does it**: Replaces vulnerable password logins with cryptographic key authentication.
- **Relevant commands**:

  ```bash
  # Local machine: Generate ED25519 SSH key pair
  ssh-keygen -t ed25519 -C "coreyms-imac-2026-04-14" -f ~/.ssh/id_ed25519_fastapiblog_imac

  # Local machine: Copy public key to server
  ssh-copy-id -i ~/.ssh/id_ed25519_fastapiblog_imac.pub coreyms@96.126.113.103

  # Local machine: Cache private key in SSH agent
  ssh-add ~/.ssh/id_ed25519_fastapiblog_imac

  # Server terminal: Enforce strict file permissions on SSH folder
  chmod 700 ~/.ssh
  chmod 600 ~/.ssh/*
  ```

- **Result**: Key-based SSH authentication is active.

### Step 6: Hardening SSH Daemon Configuration (`/etc/ssh/sshd_config`)

- **What he does**: Edits `/etc/ssh/sshd_config` to disable root login, disable password authentication, and enable public key authentication. Restarts `ssh` and tests login in a **new terminal window** before closing the active session.
- **Why he does it**: Locks down SSH access so that only authorized SSH key holders can access the server.
- **Relevant configuration changes** (`sudo nano /etc/ssh/sshd_config`):
  ```ini
  PermitRootLogin no
  PubkeyAuthentication yes
  PasswordAuthentication no
  PermitEmptyPasswords no
  KbdInteractiveAuthentication no
  ```
- **Relevant commands**:
  ```bash
  # Restart SSH service to apply settings
  sudo systemctl restart ssh
  ```
- **Result**: Password logins and root SSH access are disabled.

### Step 7: Configuring Timezone, Hostname, and Host Mappings

- **What he does**: Sets server timezone to UTC, sets the system hostname to `fastapi-blog`, updates `/etc/hosts`, and verifies changes.
- **Why he does it**: Standardizes system log timestamps to UTC and resolves local network hostnames.
- **Relevant commands**:

  ```bash
  # Set timezone to UTC
  sudo timedatectl set-timezone UTC

  # Set hostname
  sudo hostnamectl set-hostname fastapi-blog

  # Add hostname mapping to /etc/hosts
  # Add: 96.126.113.103 fastapi-blog
  sudo nano /etc/hosts
  ```

- **Result**: System hostname is set to `fastapi-blog` with UTC logging.

### Step 8: Configuring UFW Firewall

- **What he does**: Installs UFW, sets default rules (deny incoming, allow outgoing), allows SSH (22), HTTP (80), and HTTPS (443), enables UFW, and checks status.
- **Why he does it**: Blocks all unauthorized network ports.
- **Relevant commands**:
  ```bash
  sudo apt install ufw -y
  sudo ufw default deny incoming
  sudo ufw default allow outgoing
  sudo ufw allow ssh
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw enable
  sudo ufw status verbose
  ```
- **Result**: Only ports 22, 80, and 443 accept incoming network traffic.

### Step 9: Installing & Configuring Fail2ban

- **What he does**: Installs Fail2ban, creates local config files (`fail2ban.local`, `jail.local`), configures `jail.local` (`banaction = ufw`, 3 retries in 10 minutes = 1-hour ban), starts and enables the service, and verifies status.
- **Why he does it**: Protects SSH against brute-force attacks.
- **Relevant configuration** (`sudo nano /etc/fail2ban/jail.local`):

  ```ini
  [DEFAULT]
  banaction = ufw

  [sshd]
  enabled = true
  port = ssh
  filter = sshd
  maxretry = 3
  findtime = 10m
  bantime = 1h
  ```

- **Relevant commands**:
  ```bash
  sudo apt install fail2ban -y
  sudo cp /etc/fail2ban/fail2ban.conf /etc/fail2ban/fail2ban.local
  sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
  sudo systemctl start fail2ban
  sudo systemctl enable fail2ban
  sudo fail2ban-client status sshd
  ```
- **Result**: Fail2ban dynamically blocks malicious IP addresses.

### Step 10: Enabling Automatic Security Updates

- **What he does**: Installs `unattended-upgrades`, reconfigures package defaults to `yes`, and inspects configuration files.
- **Why he does it**: Automates security patch management.
- **Relevant commands**:
  ```bash
  sudo apt install unattended-upgrades -y
  sudo dpkg-reconfigure -plow unattended-upgrades
  cat /etc/apt/apt.conf.d/20auto-upgrades
  ```
- **Result**: Automatic daily security updates are active.

### Step 11: Configuring Custom Domain DNS (`A` Records) & Installing Nginx

- **What he does**: Installs Nginx. On Namecheap, deletes existing `A`/`CNAME` records and adds `A` records for `@` and `www` pointing to `96.126.113.103`. Verifies DNS propagation using `dig +short`.
- **Why he does it**: Maps `myawesomeapp.com` to the VPS IP address.
- **Relevant commands**:

  ```bash
  # Install Nginx
  sudo apt install nginx -y
  sudo systemctl start nginx
  sudo systemctl enable nginx

  # Verify DNS propagation
  dig myawesomeapp.com +short
  dig www.myawesomeapp.com +short
  ```

- **Result**: Domain name resolves to server IP address.

### Step 12: Initial Nginx Configuration & Certbot SSL Setup

- **What he does**: Creates `/etc/nginx/sites-available/myawesomeapp.com` handling `www` redirection, symlinks it to `sites-enabled/`, removes `default` site, tests syntax, installs Certbot via snap, runs Certbot to obtain SSL certificates, and tests certificate renewal dry-run.
- **Why he does it**: Obtains free Let's Encrypt SSL/TLS certificates and enables HTTPS.
- **Relevant commands**:

  ```bash
  # Create symlink and enable site
  sudo ln -s /etc/nginx/sites-available/myawesomeapp.com /etc/nginx/sites-enabled/
  sudo rm /etc/nginx/sites-enabled/default
  sudo nginx -t
  sudo systemctl reload nginx

  # Install Certbot via Snap
  sudo apt install snapd -y
  sudo snap install core && sudo snap refresh core
  sudo snap install --classic certbot
  sudo ln -s /snap/bin/certbot /usr/bin/certbot

  # Obtain SSL Certificate
  sudo certbot --nginx -d myawesomeapp.com -d www.myawesomeapp.com

  # Test automated renewal dry-run
  sudo certbot renew --dry-run
  ```

- **Result**: HTTPS is active on `https://myawesomeapp.com`.

### Step 13: Installing Python, UV, and PostgreSQL

- **What he does**: Installs Python 3, `pip`, `venv`, `git`, UV package manager, and PostgreSQL. Creates `blog_user` and `blog` database in PostgreSQL.
- **Why he does it**: Sets up the application runtimes and relational database backend.
- **Relevant commands**:

  ```bash
  # Install Python environment & Git
  sudo apt install python3 python3-pip python3-venv git -y

  # Install UV package manager
  curl -LsSf https://astral.sh/uv/install.sh | sh
  source ~/.bashrc

  # Install PostgreSQL
  sudo apt install postgresql postgresql-contrib -y
  sudo systemctl start postgresql
  sudo systemctl enable postgresql

  # Configure PostgreSQL DB and user
  sudo -i -u postgres psql
  ```

  ```sql
  CREATE USER blog_user WITH PASSWORD 'blog_pass';
  CREATE DATABASE blog OWNER blog_user;
  GRANT ALL PRIVILEGES ON DATABASE blog TO blog_user;
  \q
  ```

- **Result**: Python 3.12, UV, and PostgreSQL database `blog` are ready.

### Step 14: Setting Up Application Directory, Permissions, and `.env`

- **What he does**: Creates `/var/www/fastapi-blog`, assigns ownership to `coreyms`, clones GitHub repo into directory, sets strict file/directory permissions (`600`/`700`/`755`), runs `uv sync`, generates production secret key, creates `.env`, and sets `600` permissions on `.env`.
- **Why he does it**: Deploys codebase and secures secret production environment settings.
- **Relevant commands**:

  ```bash
  # Create application directory and assign ownership
  sudo mkdir -p /var/www/fastapi-blog
  sudo chown -R $USER:$USER /var/www/fastapi-blog
  cd /var/www/fastapi-blog

  # Clone repository
  git clone https://github.com/username/fastapi-blog.git .

  # Set restrictive Linux permissions
  find . -type f -exec chmod 600 {} +
  find . -type d -exec chmod 700 {} +
  chmod 755 .
  chmod 755 static

  # Install Python dependencies into .venv
  uv sync

  # Generate random 32-byte production secret key
  python3 -c "import secrets; print(secrets.token_hex(32))"

  # Create production .env file
  nano .env
  chmod 600 .env
  ```

- **Result**: Code is installed and dependencies are synced inside `.venv`.

### Step 15: Executing Migrations & Manual Verification

- **What he does**: Runs `uv run alembic upgrade head` to build database tables. Temporarily opens port 8000 on UFW, launches `uv run fastapi run --host 0.0.0.0 --port 8000`, tests `/health` in browser, stops process, and deletes temporary port 8000 UFW rule.
- **Why he does it**: Verifies database migrations and application execution before attaching Systemd and Nginx.
- **Relevant commands**:

  ```bash
  # Run Alembic migrations
  uv run alembic upgrade head

  # Temporary firewall rule for manual verification
  sudo ufw allow 8000/tcp
  uv run fastapi run --host 0.0.0.0 --port 8000

  # Stop server (Ctrl+C) and delete temporary rule
  sudo ufw delete allow 8000/tcp
  ```

- **Result**: Database tables exist and application responds correctly.

### Step 16: Creating Systemd Service Unit (`fastapi-blog.service`)

- **What he does**: Creates `/etc/systemd/system/fastapi-blog.service`, reloads Systemd daemon, starts and enables service, and checks status.
- **Why he does it**: Manages FastAPI process lifecycle, auto-restarting on crashes or server reboots.
- **Relevant configuration** (`sudo nano /etc/systemd/system/fastapi-blog.service`):

  ```ini
  [Unit]
  Description=FastAPI Blog Application
  After=network.target postgresql.service
  Wants=postgresql.service

  [Service]
  User=coreyms
  Group=www-data
  WorkingDirectory=/var/www/fastapi-blog
  EnvironmentFile=/var/www/fastapi-blog/.env
  ExecStart=/var/www/fastapi-blog/.venv/bin/fastapi run --workers 1 --host 127.0.0.1 --port 8000 --proxy-headers
  Restart=always
  RestartSec=5

  [Install]
  WantedBy=multi-user.target
  ```

- **Relevant commands**:
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl start fastapi-blog
  sudo systemctl enable fastapi-blog
  sudo systemctl status fastapi-blog
  ```
- **Result**: FastAPI runs in background managed by Systemd.

### Step 17: Configuring Production Nginx Reverse Proxy

- **What he does**: Edits `/etc/nginx/sites-available/myawesomeapp.com` to replace initial boilerplate with full production reverse proxy configuration (static file handling, proxy headers, body size limits). Tests syntax and reloads Nginx.
- **Why he does it**: Routes incoming public HTTPS traffic directly to Nginx, serving static assets directly and forwarding dynamic requests to FastAPI.
- **Relevant commands**:
  ```bash
  sudo nginx -t
  sudo systemctl reload nginx
  ```
- **Result**: Nginx proxies traffic to FastAPI and serves static files directly.

### Step 18: End-to-End Production Verification

- **What he does**: Visits `https://myawesomeapp.com` in browser, tests `/health` and `/docs`, registers a user, logs in, creates a post, and uploads a profile picture to verify S3 storage.
- **Why he does it**: Confirms that authentication, database writes, static routes, and cloud storage operate on production VPS.
- **Result**: Application is fully operational in production.

---

## 4. Code Examples

### Database Health Check Route (`main.py`)

```python
from fastapi import FastAPI, HTTPException, status, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db

app = FastAPI()

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable"
        )
```

### Complete Systemd Service File (`/etc/systemd/system/fastapi-blog.service`)

```ini
[Unit]
Description=FastAPI Blog Application
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=coreyms
Group=www-data
WorkingDirectory=/var/www/fastapi-blog
EnvironmentFile=/var/www/fastapi-blog/.env
ExecStart=/var/www/fastapi-blog/.venv/bin/fastapi run --workers 1 --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Full Production Nginx Configuration (`/etc/nginx/sites-available/myawesomeapp.com`)

```nginx
# 1. Redirect www to non-www (HTTPS)
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name www.myawesomeapp.com;

    ssl_certificate /etc/letsencrypt/live/myawesomeapp.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myawesomeapp.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    return 301 https://myawesomeapp.com$request_uri;
}

# 2. Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name myawesomeapp.com www.myawesomeapp.com;
    return 301 https://myawesomeapp.com$request_uri;
}

# 3. Main HTTPS Application Server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name myawesomeapp.com;

    ssl_certificate /etc/letsencrypt/live/myawesomeapp.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myawesomeapp.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Client upload size limit (matches application profile pic limit)
    client_max_body_size 5M;

    # Serve static assets directly from disk
    location /static/ {
        alias /var/www/fastapi-blog/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Proxy dynamic requests to FastAPI / Uvicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 5. FastAPI & Python Knowledge

- **`--proxy-headers` Flag in Uvicorn/FastAPI**: Instructs Uvicorn to trust incoming `X-Forwarded-*` HTTP headers forwarded by reverse proxies like Nginx. Without `--proxy-headers`, FastAPI sees all incoming traffic as originating from `127.0.0.1` over plain HTTP, breaking client IP resolution and HTTPS URL generation.
- **Asynchronous Worker Sizing**: Asynchronous application servers handle I/O concurrency on an event loop thread without blocking. Running 1 worker per CPU core (\\(1 \times \text{CPU cores}\\)) avoids process context switching overhead.
- **`uv sync` Package Synchronization**: In production environments, `uv sync` reads `pyproject.toml` and `uv.lock` to construct an identical virtual environment (`.venv`), avoiding installation variance.
- **`text("SELECT 1")` Execution**: Converts a raw SQL string into a SQLAlchemy executable construct, avoiding table ORM scans.

---

## 6. Tips & Important Details

- **Test SSH Login Before Closing Active Sessions**: Always keep your primary root/sudo SSH terminal session open when modifying `/etc/ssh/sshd_config` or testing key logins in a secondary terminal. If the configuration contains syntax errors, you can fix them in the active window without being locked out.
- **Test UFW Allow Rules Before Enabling**: Always execute `sudo ufw allow ssh` _before_ running `sudo ufw enable`.
- **Group Assignment (`www-data`)**: Setting the group to `www-data` in Systemd unit files (`Group=www-data`) allows Nginx to traverse application folders safely.
- **Restrict File Permissions**: Apply `find . -type f -exec chmod 600 {} +` and `find . -type d -exec chmod 700 {} +` to deny access to other system users, explicitly opening `static` with `chmod 755 static`.
- **Port 587 for SMTP**: Use port 587 with STARTTLS for production email submission.

---

## 7. Errors & Pitfalls

- **Locking Yourself Out via SSH or UFW**: Enabling UFW without allowing SSH (port 22) or disabling password authentication before copying public keys locks developers out of VPS servers.
- **Missing `--proxy-headers`**: Running Uvicorn behind Nginx without `--proxy-headers` causes FastAPI to log `127.0.0.1` as client IP addresses and break HTTPS redirects.
- **Synchronous vs. Asynchronous Worker Oversizing**: Applying the legacy synchronous worker formula (\\((2 \times \text{cores}) + 1\\)) to async apps wastes server RAM.
- **Leaving Temporary Firewall Ports Open**: Leaving port 8000 open after manual verification bypasses Nginx reverse proxy controls.

---

## 8. Best Practices & Trade-offs

- **VPS Deployment vs. Containerized Cloud (Cloud Run)**:
  - _VPS (Manual Deployment)_: Full root control, fixed monthly cost (\$5/mo), transparent infrastructure learning. Trade-off: Requires manual OS patch management, firewall maintenance, and process monitoring.
  - _Containerized Cloud (Google Cloud Run)_: Fully managed infrastructure, auto-scaling to zero when idle, automated builds. Trade-off: Higher variable cost at scale, cloud platform lock-in, hides underlying system mechanics.
- **Direct Nginx Static Serving vs. App Proxying**:
  - _Best Practice_: Serve static files directly via Nginx (`location /static/`). Bypasses Python interpretation overhead entirely for static assets.

---

## 9. Resources

- **GitHub Source Code Repository**: Companion code repository for Part 18 linked in video description.
- **Corey Schafer VPS Setup Guide**: Reference guide for Linux server setup.
- **Linode (Akamai) Cloud Hosting**: VPS infrastructure provider.
- **Certbot / Let's Encrypt**: Free automated SSL certificate authority.

---

## 10. Key Takeaways

1. Deploying to a VPS provides full operational control and clear visibility into web server architecture.
2. Add a `/health` endpoint executing `SELECT 1` to return HTTP 503 if the database fails.
3. Choose an LTS operating system release (such as Ubuntu 24.04 LTS) for long-term security support.
4. Never operate continuously as `root`—create a dedicated user with `sudo` access.
5. Use ED25519 SSH key pairs (`ssh-keygen -t ed25519`) and disable password logins.
6. Test SSH key logins in a secondary terminal before closing active server sessions.
7. Configure UFW firewall to deny incoming traffic by default, allowing only ports 22, 80, and 443.
8. Install Fail2ban to automatically block IP addresses exhibiting brute-force authentication failures.
9. Enable `unattended-upgrades` to automate daily security patch management.
10. Point custom domain `A` records (`@` and `www`) to the server IP and check propagation with `dig`.
11. Use Nginx as a reverse proxy for SSL termination and static file serving.
12. Obtain automated SSL certificates using Certbot (`certbot --nginx`).
13. Install Python dependencies using `uv sync` from a repository `uv.lock` file.
14. Store secrets in `.env` with restrictive `chmod 600` permissions.
15. Manage app execution using Systemd (`fastapi-blog.service`) with `Restart=always`.
16. Calculate worker count for async apps as \\(1 \times \text{CPU cores}\\).
17. Pass `--proxy-headers` to FastAPI/Uvicorn when running behind Nginx.
18. Update code using a streamlined workflow: `git pull` \\(\rightarrow\\) `uv sync` \\(\rightarrow\\) `alembic upgrade head` \\(\rightarrow\\) `systemctl restart fastapi-blog`.

---

## 11. Quick Reference

### Command Line Cheat Sheet

```bash
# SSH & Server Hardening
ssh-keygen -t ed25519 -C "comment"
ssh-copy-id -i ~/.ssh/key.pub user@server_ip
sudo nano /etc/ssh/sshd_config
sudo systemctl restart ssh

# UFW Firewall Commands
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose

# Fail2ban Management
sudo systemctl start fail2ban
sudo fail2ban-client status sshd

# DNS Verification
dig myawesomeapp.com +short

# Nginx & Certbot
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d myawesomeapp.com -d www.myawesomeapp.com
sudo certbot renew --dry-run

# Systemd Commands
sudo systemctl daemon-reload
sudo systemctl start fastapi-blog
sudo systemctl enable fastapi-blog
sudo systemctl status fastapi-blog
sudo journalctl -u fastapi-blog -f

# Application Update Workflow
git pull
uv sync
uv run alembic upgrade head
sudo systemctl restart fastapi-blog
```

---

## 12. Mental Model

- **VPS Deployment Architecture & Request Flow**:
  1. **Public Web Request**: Client browser requests `https://myawesomeapp.com/posts`.
  2. **DNS Resolution**: DNS resolves `myawesomeapp.com` to VPS IP `96.126.113.103`.
  3. **UFW Firewall Layer**: Port 443 accepts connection (all unauthorized ports dropped).
  4. **Nginx Reverse Proxy & SSL Termination**: Nginx terminates SSL/TLS using Let's Encrypt certificates.
     - If request path is `/static/*` \\(\rightarrow\\) Nginx reads directly from `/var/www/fastapi-blog/static/`.
     - If request path is dynamic \\(\rightarrow\\) Nginx proxies request to `http://127.0.0.1:8000` with `X-Forwarded-*` headers.
  5. **Systemd Process Manager**: Systemd maintains Uvicorn process (`fastapi run --workers 1 --proxy-headers`) listening on `127.0.0.1:8000`.
  6. **FastAPI Application Execution**: Route handler runs async code \\(\rightarrow\\) Interacts with local PostgreSQL database (`blog`) or AWS S3 bucket \\(\rightarrow\\) Returns JSON response to Nginx \\(\rightarrow\\) Nginx delivers response to Client Browser over HTTPS.
