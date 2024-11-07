import os
from dump import take_dump
from alert import alert_trigger
from flask import Flask, request, jsonify
from kubernetes import client, config
from prometheus_flask_exporter import PrometheusMetrics
import urllib3, logging
from prometheus_client import Counter
from concurrent.futures import ThreadPoolExecutor  # Import ThreadPoolExecutor

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Custom filter to exclude /metrics endpoint logs
class ExcludeMetricsFilter(logging.Filter):
    def filter(self, record):
        return '/metrics' not in record.getMessage()

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

log_file_path = os.getenv('LOG_FILE_PATH', '/dev/stdout')

if not logger.handlers:
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    file_handler.addFilter(ExcludeMetricsFilter())
    logger.addHandler(file_handler)

# Apply the filter to the Werkzeug logger as well
werkzeug_logger = logging.getLogger('werkzeug')
if not werkzeug_logger.handlers:
    werkzeug_logger.addFilter(ExcludeMetricsFilter())

app = Flask(__name__)

# Initialize Prometheus metrics
metrics = PrometheusMetrics(app)

# Define the counter
total_alerts = Counter(
    'selfhealing_api_alerts_total',
    'Total number of alert triggers in selfhealing API',
    ['alertname', 'pod_name']
)

def load_kube_config():
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster config")
    except config.config_exception.ConfigException:
        config.load_kube_config()
        logger.info("Loaded local kubeconfig")

def pod_exists_and_ready(namespace, pod_name):
    load_kube_config()
    v1 = client.CoreV1Api()
    try:
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        if pod.status.phase == 'Running':
            # Check if all containers are ready
            for container_status in pod.status.container_statuses:
                if not container_status.ready:
                    return False
            return True
        return False
    except client.rest.ApiException as e:
        if e.status == 404:
            logger.info(f"Pod {namespace}/{pod_name} not found.")
            return False
        else:
            logger.error(f"Error checking pod status: {e}")
            raise

@app.route('/', methods=['GET'])
@metrics.counter(
    'selfhealing_api_requests_total',
    'Total number of requests to selfhealing API',
    labels={'endpoint': '/'}
)
def welcome():
    return jsonify(message="Welcome to PG2.0 selfhealing API."), 200

@app.route('/alert', methods=['POST'])
@metrics.counter(
    'selfhealing_api_alerts_request_total',
    'Total number of alert requests in selfhealing API for /alerts',
    labels={'endpoint': '/alert'}
)
def alert():
    executor = ThreadPoolExecutor(max_workers=5)  # Define executor here
    slack_alert = []
    data = request.json
    for alert in data['alerts']:
        alert_name = alert['labels'].get('alertname')
        priority = alert['labels'].get('priority')
        pod_name = alert['labels'].get('pod_name', alert['labels'].get('pod'))
        techteam = alert['labels'].get('techteam')
        selfheal = alert['labels'].get('self_healing')
        namespace = alert['labels'].get('namespace', alert['labels'].get('kubernetes_namespace', 'prod'))  # Default to 'prod' namespace if not provided
        dummy_file_link = "https://drive.google.com/drive/u/0/folders/XXXXXXXXX"
        # Check if alert is related to pod, CPU, or memory and if priority is P0
        if priority == 'P1' and selfheal == "true" and techteam == 'payment' and alert_name == 'p99 Level Accept API RT':
            if pod_exists_and_ready(namespace, pod_name):
                # terminate pod
                terminate_pod(pod_name, namespace)
                slack_alert.append({
                    'alertname': alert_name,
                    'pod': pod_name,
                    'namespace': namespace,
                    'techteam': techteam,
                    'priority': priority,
                    'dump_type': "NA",
                    'file_link': dummy_file_link
                })
                alert_trigger(slack_alert)
                logger.info(f"Slack alert triggered for {alert_name} namespace {namespace} and pod {pod_name}.")
            else:
                logger.info(f"Pod {namespace}/{pod_name} does not exist or is not ready.")

        elif priority == 'P1' and selfheal == "true" and any(keyword in alert_name for keyword in ['pod']) and any(keyword in pod_name for keyword in ['acquiring']):
            if any(keyword in alert_name for keyword in ['cpu']):
                if pod_exists_and_ready(namespace, pod_name):
                    terminate_pod(pod_name, namespace)
                    slack_alert.append({
                        'alertname': alert_name,
                        'pod': pod_name,
                        'namespace': namespace,
                        'techteam': techteam,
                        'priority': priority,
                        'dump_type': "NA",
                        'file_link': dummy_file_link
                    })
                    alert_trigger(slack_alert)
                    logger.info(f"Slack alert triggered for {alert_name} namespace {namespace} and pod {pod_name}.")
                else:
                    logger.info(f"Pod {namespace}/{pod_name} does not exist or is not ready.")

            elif any(keyword in alert_name for keyword in ['memory']):
                if pod_exists_and_ready(namespace, pod_name):
                    terminate_pod(pod_name, namespace)
                    slack_alert.append({
                        'alertname': alert_name,
                        'pod': pod_name,
                        'namespace': namespace,
                        'techteam': techteam,
                        'priority': priority,
                        'dump_type': "NA",
                        'file_link': dummy_file_link
                    })
                    alert_trigger(slack_alert)
                    logger.info(f"Slack alert triggered for {alert_name} namespace {namespace} and pod {pod_name}.")

                else:
                    logger.info(f"Pod {namespace}/{pod_name} does not exist or is not ready.")
            else:
                logger.info(f"Alert {alert_name} and {namespace}/{pod_name} is not a CPU or Memory alert.")

        elif priority == 'P1' and selfheal == "true" and any(keyword in alert_name for keyword in ['pod']):
            if any(keyword in alert_name for keyword in ['cpu']):
                if pod_exists_and_ready(namespace, pod_name):
                    # Schedule background task for thread dump
                    executor.submit(handle_dump, 'thread', namespace, pod_name, slack_alert, alert_name, techteam, priority)
                else:
                    logger.info(f"Pod {namespace}/{pod_name} does not exist or is not ready.")
            elif any(keyword in alert_name for keyword in ['memory']):
                if pod_exists_and_ready(namespace, pod_name):
                    # Schedule background task for heap dump
                    executor.submit(handle_dump, 'heap', namespace, pod_name, slack_alert, alert_name, techteam, priority)
                else:
                    logger.info(f"Pod {namespace}/{pod_name} does not exist or is not ready.")
            else:
                logger.info(f"Alert {alert_name} and {namespace}/{pod_name} is not a CPU or Memory alert.")
    
    return jsonify(slack_alert), 200  # Return the JSON response

def handle_dump(dump_type, namespace, pod_name, slack_alert, alert_name, techteam, priority):
    file_link = take_dump(dump_type, namespace, pod_name)
    if pod_exists_and_ready(namespace, pod_name):
        terminate_pod(pod_name, namespace)
    slack_alert.append({
        'alertname': alert_name,
        'pod': pod_name,
        'namespace': namespace,
        'techteam': techteam,
        'priority': priority,
        'dump_type': dump_type,
        'file_link': file_link  # Include file_link in the response
    })
    alert_trigger(slack_alert)
    logger.info(f"Slack alert: {slack_alert}")

def terminate_pod(pod_name, namespace):
    load_kube_config()
    v1 = client.CoreV1Api()
    v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
    logger.info(f"Terminated pod {namespace}/{pod_name}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
