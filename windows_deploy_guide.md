# Deploying PariMarket from Local Windows to Google Cloud

This guide focuses on deploying your local PariMarket code directly from a Windows machine to Google Cloud, without needing Docker Desktop or pulling the code from a Git repository in the cloud. We will use the Google Cloud CLI (`gcloud`) and Firebase CLI to upload your local files.

## Prerequisites

Ensure the following are installed and configured on your Windows machine:
1. **Google Cloud CLI**: [Install gcloud for Windows](https://cloud.google.com/sdk/docs/install#windows)
2. **Node.js**: [Install Node.js](https://nodejs.org/en) (Required for Firebase CLI)
3. Open **Windows PowerShell** (run as Administrator if needed).

---

## Step 1: Initial Setup

### 1.1 Log in and Set Project
Open PowerShell and authenticate your Google account:
```powershell
gcloud auth login
  gcloud config set project prediction-490907
```

### 1.2 Enable Required APIs
```powershell
gcloud services enable compute.googleapis.com secretmanager.googleapis.com firebase.googleapis.com firebasehosting.googleapis.com cloudbuild.googleapis.com run.googleapis.com
```

### 1.3 Create Secrets using Google Web Interface
It's highly recommended to use the **Google Cloud Console** to enter secrets on Windows. This avoids the messy PowerShell escaping rules and prevents your private keys from being logged in Windows activity histories.

1. Go to [Google Cloud Console > Secret Manager](https://console.cloud.google.com/security/secret-manager).
2. Click **Create Secret**.
3. Create the following exact secrets: `OWNER_PRIVATE_KEY`, `ORACLE_PRIVATE_KEY`, `TIMER_PRIVATE_KEY`, `DISTRIBUTION_PRIVATE_KEY`, `GOOGLE_API_KEY`, `COINGECKO_API_KEY`.
4. Enter their respective values in the "Secret value" box for each and save.

---

## Step 2: Deploy Frontend to Firebase Hosting

Firebase CLI reads your local Windows `frontend` folder and uploads it globally to Google's CDN.

### 2.1 Install Firebase CLI & Login
```powershell
npm install -g firebase-tools
firebase login
```

### 2.2 Initialize Firebase
Navigate to your project directory:
```powershell
cd "C:\Users\Karth\Documents\agent projects\coingecko"
firebase init hosting --project prediction-490907
```
When prompted:
* **Public directory?** Type `frontend`
* **Single-page app?** `N`
* **GitHub auto-builds?** `N`
* **Overwrite index.html?** `N`

### 2.3 Deploy
```powershell
firebase deploy --only hosting
```
*Your frontend is now live at `https://prediction-490907.web.app`!*

---

## Step 3: Deploy Agents 

You have two main options to deploy the Python agents directly from your local Windows file system without Git.

### Option A: Cloud Run Source Deploy (Easiest & Recommended)
Cloud Run can take your local Windows directory, upload it securely to Google, and build the environment automatically in the cloud. No local Docker is needed.

**1. Create a Service Account:**
```powershell
gcloud iam service-accounts create parimarket-vm-sa --display-name="PariMarket SA"
gcloud projects add-iam-policy-binding prediction-490907 --member="serviceAccount:parimarket-vm-sa@prediction-490907.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

**2. Deploy the Project Files from Windows:**
```powershell
cd "C:\Users\Karth\Documents\agent projects\coingecko"

gcloud run deploy parimarket-agents --source . --region=us-central1 --no-allow-unauthenticated --min-instances=1 --memory=512Mi --service-account=parimarket-vm-sa@prediction-490907.iam.gserviceaccount.com --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,OWNER_PRIVATE_KEY=OWNER_PRIVATE_KEY:latest,ORACLE_PRIVATE_KEY=ORACLE_PRIVATE_KEY:latest,TIMER_PRIVATE_KEY=TIMER_PRIVATE_KEY:latest,DISTRIBUTION_PRIVATE_KEY=DISTRIBUTION_PRIVATE_KEY:latest,COINGECKO_API_KEY=COINGECKO_API_KEY:latest" --set-env-vars="BASE_RPC_URL=https://node.shadownet.etherlink.com,BASE_CHAIN_ID=127823,CONTRACT_ADDRESS=0x9b47703A489107672A3C8D42Be787145cC86fE96,GEMINI_MODEL=gemini-2.5-flash,CLOSE_BEFORE_RESOLUTION_HOURS=2,RESOLUTION_HOUR_UTC=0,TICKER_INTERVAL_SECS=3600"
```

### Option B: Deploy to a Compute Engine VM via SCP
If you want a dedicated VM (always-on, cheaper instance) instead of serverless Cloud Run, you can upload your files from Windows using `gcloud compute scp`.

**1. Create the VM from PowerShell:**
```powershell
gcloud compute instances create parimarket-agents `
  --zone=us-central1-a `
  --machine-type=e2-micro `
  --image-family=debian-12 `
  --image-project=debian-cloud `
  --service-account=parimarket-vm-sa@prediction-490907.iam.gserviceaccount.com `
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

**2. Copy your local Windows code to the VM:**
```powershell
# This command recursively uploads your entire Windows project folder to the VM
gcloud compute scp --recurse "C:\Users\Karth\Documents\agent projects\coingecko" parimarket-agents:~/parimarket-code --zone=us-central1-a
```

**3. SSH via Google Cloud Web Interface to finalize setup:**
* Go to the **Google Cloud Console > Compute Engine** in your web browser.
* Click the **SSH** button next to your `parimarket-agents` instance.
* In the browser terminal, set up your project:
```bash
sudo mv ~/parimarket-code /opt/parimarket
cd /opt/parimarket

sudo apt-get update -y
sudo apt-get install -y python3.11 python3.11-venv python3-pip

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r agents/requirements.txt
```
*(From there, you can continue to create your `.env` using your secret manager values and start the `systemd` background service via SSH).*

---

## Troubleshooting Cloud Run Deployment

### Error: "container failed to start and listen on the port defined by PORT=8080"
Cloud Run expects all services to be web servers that listen for incoming traffic. Since the PariMarket Agent is a background loop, it doesn't normally listen on a port.

**The Fix:**
I have automatically added a tiny "Health Check" listener to `agents/run_orchestrator.py`. This listener starts a small background server on port 8080 (or whatever Cloud Run provides) just to say "I'm alive" to Google Cloud.

**Action:**
Simply re-run your `gcloud run deploy` command from PowerShell. It should now pass the health check and stay running.

```powershell
# Re-run this command:
gcloud run deploy parimarket-agents --source . --region=us-central1 --no-allow-unauthenticated --min-instances=1 --memory=512Mi --service-account=parimarket-vm-sa@prediction-490907.iam.gserviceaccount.com --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,OWNER_PRIVATE_KEY=OWNER_PRIVATE_KEY:latest,ORACLE_PRIVATE_KEY=ORACLE_PRIVATE_KEY:latest,TIMER_PRIVATE_KEY=TIMER_PRIVATE_KEY:latest,DISTRIBUTION_PRIVATE_KEY=DISTRIBUTION_PRIVATE_KEY:latest,COINGECKO_API_KEY=COINGECKO_API_KEY:latest" --set-env-vars="BASE_RPC_URL=https://node.shadownet.etherlink.com,BASE_CHAIN_ID=127823,CONTRACT_ADDRESS=0x9b47703A489107672A3C8D42Be787145cC86fE96,GEMINI_MODEL=gemini-2.5-flash,CLOSE_BEFORE_RESOLUTION_HOURS=2,RESOLUTION_HOUR_UTC=0,TICKER_INTERVAL_SECS=3600"
```
