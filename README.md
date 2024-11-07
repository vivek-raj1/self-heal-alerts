
# Self-Heal-Alert

Self-Heal-Alert is a Flask-based application that automates the handling of Kubernetes alerts, including taking heap and thread dumps from pods when necessary. It then uploads these dumps to Google Drive and sends alerts to a designated Slack channel based on specified conditions.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Usage](#usage)
- [Endpoints](#endpoints)
- [Logging](#logging)
- [Example Alert Handling](#example-alert-handling)
- [Functions](#functions)

---

## Prerequisites

- **Python**: 3.8+
- **Packages**:
  - Flask
  - Kubernetes Python client
  - Google Drive API client
- **Credentials**:
  - Google Drive API credentials
  - Slack webhook URL

---

## Setup

1. **Clone the repository**:
    ```bash
    git clone git@github.com:vivek-raj1/self-heal-alert.git
    cd self-heal-alert
    ```

2. **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3. **Set environment variables**:
    ```bash
    export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/XXXXX"
    export CHANNEL_NAME="#abc"
    ```

4. **Kubernetes Configuration**:
    - **In-cluster**: Ensure your pod has the necessary RBAC permissions.
    - **Local development**: Configure your `kubeconfig` file for accessing the Kubernetes cluster.

5. **Google Drive API setup**:
    - Place your `credentials.json` file in the designated directory.
    - Follow the [Google Drive API Python Quickstart](https://developers.google.com/drive/api/v3/quickstart/python) to authorize the API.

6. **Slack Webhook**:
    - Add your Slack webhook URL in the `alert_trigger` function in `alert.py`.

---

## Usage

1. **Run the Flask application**:
    ```bash
    python app.py
    ```

2. **Send a POST request to `/alert`** to test alert handling.

---

## Endpoints

### POST /alert

This endpoint processes incoming alerts. Send a JSON payload in the format:
```json
{
  "alerts": [
    {
      "labels": {
        "alertname": "example_alert",
        "priority": "P0",
        "pod": "example-pod",
        "namespace": "default",
        "techteam": "example-team"
      }
    }
  ]
}
```

---

## Logging

Logs are directed to the path specified by the `LOG_FILE_PATH` environment variable. The default location is `/dev/stdout`.

---

## Example Alert Handling

Self-Heal-Alert performs the following actions based on the alert's priority and conditions:

- **P1 alerts** for "p99 Pod Level Pay Accept API RT" cause the pod to be terminated.
- **P0 alerts** related to **CPU** trigger a thread dump before terminating the pod.
- **P0 alerts** related to **memory** trigger a heap dump before terminating the pod.

---

## Functions

- **`load_kube_config()`**: Loads the Kubernetes configuration for accessing the cluster.
- **`pod_exists_and_ready(namespace, pod_name)`**: Verifies if the specified pod is in a 'Running' state.
- **`terminate_pod(pod_name, namespace)`**: Terminates the specified pod in the given namespace.
- **`take_dump(dump_type, namespace, pod_name)`**: Takes a heap or thread dump from the specified pod and uploads it to Google Drive.
- **`alert_trigger(slack_alert)`**: Sends a customized Slack alert to notify relevant teams.

---

This project streamlines alert handling and increases resilience by automating responses to critical events in Kubernetes.
