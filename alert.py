import urllib3, os, json

# Function to send alerts to Slack
http = urllib3.PoolManager()

# Get the values of environment variables
slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
channel_name = os.environ.get('CHANNEL_NAME')

def alert_trigger(slack_alert):
    for alerts in slack_alert:
        slack = []
        slack.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Pod terminated || techteam: {alerts['techteam']} || severity: info"
                }
            }
        )
        slack.append(
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": "*Pod Name:*\n" + "`" + str(alerts['pod']) + "`"
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Alertname Name:*\n"  + str(alerts['alertname'])
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Namespace:*\n"  +  str(alerts['namespace']) 
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Priority:*\n"  + str(alerts['priority'])
                        }
                    ]
                }
            )

        slack.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":technologist: *{alerts['dump_type']} dump link* :point_right:"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Download me"
                    },
                    "value": "click_me_123",
                    "url": f"{alerts['file_link']}",
                    "action_id": "button-action"
                }
            }
        )
        msg = {
            "channel": channel_name,
            "username": "Pod terminated Status",
            "icon_emoji": ":alert:",
            "blocks": slack
        }
        encoded_msg = json.dumps(msg).encode('utf-8')
        resp = http.request('POST', slack_webhook_url, body=encoded_msg)
        print(json.dumps(msg))
