#!/bin/bash
# =============================================================================
# Private Deployment Variables for the IB-Trading Project
# =============================================================================
#
# USAGE:
# 1. Fill in the placeholder values below with your actual information.
# 2. Load these variables into your shell environment by running:
#    source deployment_vars.sh
# 3. Now you can run the gcloud commands from the deployment plan, and they
#    will use these variables automatically (e.g., gcloud config set project $PROJECT_ID).

# --- Core GCP Settings ---
# Your Google Cloud Project ID
export PROJECT_ID="gold-gearbox-424413-k1"

# The GCP region for your services (e.g., asia-east1, us-central1)
export GCP_REGION="asia-east1"

# The email account you use to log into GCP, for granting invoke permissions
export USER_EMAIL_ACCOUNT="xmyyj001@gmail.com"

# --- Service & Repo Naming ---
# The name for the Artifact Registry repository
export REPO_NAME="cloud-run-repo"

# The name for the Cloud Run service (and other related resources)
export SERVICE_NAME_BASE="ib-trading"

# The trading mode for this deployment (paper or live)
export TRADING_MODE="paper"

# --- IB Credentials & Secret Manager ---
# The name for the secret in Google Secret Manager
export SECRET_NAME="ib-${TRADING_MODE}-credentials"

# Your Interactive Brokers Username (for paper or live account)
export IB_USERNAME="[REPLACE_WITH_YOUR_IB_USERNAME]"

# Your Interactive Brokers Password
export IB_PASSWORD="[REPLACE_WITH_YOUR_IB_PASSWORD]"


# --- Derived Variables (usually no need to change these) ---
# Full Artifact Registry path
export DOCKER_REPO_URL="${GCP_REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"

# Full Service Account email address
export SERVICE_ACCOUNT_EMAIL="${SERVICE_NAME_BASE}@${PROJECT_ID}.iam.gserviceaccount.com"

# Full Cloud Run service name
export CLOUD_RUN_SERVICE_NAME="ib-${TRADING_MODE}"


# --- Post-Deployment Variables ---
# After deploying the service for the first time, get its URL by running:
# gcloud run services describe ${CLOUD_RUN_SERVICE_NAME} --region ${GCP_REGION} --format="value(status.url)"
# Then, you can uncomment and set the variable below for use in scheduler commands.
# export SERVICE_URL="[PASTE_THE_SERVICE_URL_HERE]"

echo "Deployment variables loaded."
